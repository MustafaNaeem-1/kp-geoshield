"""Forest disturbance cause attribution (logging vs disease/drought vs fire vs other natural).

Trained on DISFOR (European Sentinel-2 pixel time series with agent labels), applied to
KP change alerts. The same `event_features` function is used for training and inference so
the features are identical. Only information available at detection time is used
(<=60 days after the event; no recovery features).

Reflectance inputs are Sentinel-2 L2A *harmonized* DN (0-10000), as in DISFOR and
Earth Engine `COPERNICUS/S2_SR_HARMONIZED` (verified: no +1000 offset jump in DISFOR).
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from app.core.config import MODELS_DIR

# Approved mapping (plan + change log 2026-11-20). Labels not listed are excluded.
CLASS_NAMES = ["undisturbed", "logging", "disease_drought", "fire", "other_natural"]
LABEL_TO_CLASS: dict[int, str] = {
    110: "undisturbed",
    211: "logging", 212: "logging", 213: "logging", 220: "logging", 221: "logging", 222: "logging",
    230: "disease_drought", 231: "disease_drought", 232: "disease_drought", 241: "disease_drought",
    242: "fire",
    243: "other_natural", 244: "other_natural", 245: "other_natural",
}
EXCLUDED_LABELS = {100, 120, 121, 122, 123, 200}  # revegetation states + unknown-cause "Disturbed"

PRE_DAYS = 365
POST_DAYS = 60
POST_DAYS_FALLBACK = 120
MIN_PRE_OBS = 5

FEATURE_NAMES = [
    "ndvi_pre", "ndvi_post_min", "ndvi_post_med", "ndvi_drop", "ndvi_rel_drop",
    "nbr_pre", "nbr_post_min", "nbr_post_med", "nbr_drop", "nbr_rel_drop",
    "ndmi_pre", "ndmi_post_min", "ndmi_post_med", "ndmi_drop", "ndmi_rel_drop",
    "ndvi_pre_slope", "ndmi_pre_slope", "ndvi_pre_std", "ndvi_early_late_diff", "ndmi_early_late_diff",
    "swir_ratio_post", "b11_change", "doy_sin", "doy_cos",
]

MODEL_PATH = MODELS_DIR / "attribution_xgb.json"
META_PATH = MODELS_DIR / "attribution_meta.json"


def add_indices(df: pd.DataFrame) -> pd.DataFrame:
    """df needs B04, B08, B11, B12 (DN). Adds ndvi, nbr, ndmi."""
    out = df.copy()
    b4, b8, b11, b12 = (out[c].astype(float) for c in ("B04", "B08", "B11", "B12"))
    with np.errstate(divide="ignore", invalid="ignore"):
        out["ndvi"] = (b8 - b4) / (b8 + b4)
        out["nbr"] = (b8 - b12) / (b8 + b12)
        out["ndmi"] = (b8 - b11) / (b8 + b11)
    return out.replace([np.inf, -np.inf], np.nan)


def _slope_per_year(t: pd.Series, y: pd.Series) -> float:
    m = y.notna()
    if m.sum() < 3:
        return np.nan
    x = (t[m] - t[m].min()).dt.total_seconds().to_numpy() / (365.25 * 86400)
    if np.ptp(x) == 0:
        return np.nan
    return float(np.polyfit(x, y[m].to_numpy(), 1)[0])


def event_features(series: pd.DataFrame, event_date: pd.Timestamp) -> dict | None:
    """Features for one pixel around one event.

    series: clear observations only, columns t (datetime), B04, B08, B11, B12 (+ optional others).
    Returns None when there is not enough data before/after the event.
    """
    s = add_indices(series).dropna(subset=["ndvi", "nbr", "ndmi"]).sort_values("t")
    e = pd.Timestamp(event_date)
    if s["t"].dt.tz is not None and e.tz is None:
        e = e.tz_localize(s["t"].dt.tz)
    elif s["t"].dt.tz is None and e.tz is not None:
        e = e.tz_convert(None)

    pre = s[(s.t >= e - pd.Timedelta(days=PRE_DAYS)) & (s.t < e)]
    post = s[(s.t >= e) & (s.t <= e + pd.Timedelta(days=POST_DAYS))]
    if post.empty:
        post = s[(s.t >= e) & (s.t <= e + pd.Timedelta(days=POST_DAYS_FALLBACK))]
    if len(pre) < MIN_PRE_OBS or post.empty:
        return None

    f: dict[str, float] = {}
    for ix in ("ndvi", "nbr", "ndmi"):
        pre_med = float(pre[ix].median())
        post_min = float(post[ix].min())
        f[f"{ix}_pre"] = pre_med
        f[f"{ix}_post_min"] = post_min
        f[f"{ix}_post_med"] = float(post[ix].median())
        f[f"{ix}_drop"] = pre_med - post_min
        f[f"{ix}_rel_drop"] = (pre_med - post_min) / (abs(pre_med) + 1e-3)

    f["ndvi_pre_slope"] = _slope_per_year(pre["t"], pre["ndvi"])
    f["ndmi_pre_slope"] = _slope_per_year(pre["t"], pre["ndmi"])
    f["ndvi_pre_std"] = float(pre["ndvi"].std()) if len(pre) > 1 else np.nan
    early = pre[pre.t < e - pd.Timedelta(days=180)]
    late = pre[pre.t >= e - pd.Timedelta(days=90)]
    f["ndvi_early_late_diff"] = float(early["ndvi"].median() - late["ndvi"].median()) if len(early) and len(late) else np.nan
    f["ndmi_early_late_diff"] = float(early["ndmi"].median() - late["ndmi"].median()) if len(early) and len(late) else np.nan

    at_min = post.loc[post["nbr"].idxmin()]
    f["swir_ratio_post"] = float(at_min["B12"]) / (float(at_min["B11"]) + 1.0)
    f["b11_change"] = float(post["B11"].median()) / (float(pre["B11"].median()) + 1.0)
    doy = e.day_of_year
    f["doy_sin"] = float(np.sin(2 * np.pi * doy / 365.25))
    f["doy_cos"] = float(np.cos(2 * np.pi * doy / 365.25))
    return f


def estimate_event_date(series: pd.DataFrame, search_start, search_end, drop: float = 0.15) -> pd.Timestamp | None:
    """First date in [search_start, search_end] where NDVI falls `drop` below the median of the
    preceding year and stays below on the next observation (two consecutive clear obs)."""
    s = add_indices(series).dropna(subset=["ndvi"]).sort_values("t").reset_index(drop=True)
    a, b = pd.Timestamp(search_start), pd.Timestamp(search_end)
    for i in range(len(s) - 1):
        t = s.at[i, "t"]
        if t < a or t > b:
            continue
        pre = s[(s.t < t) & (s.t >= t - pd.Timedelta(days=PRE_DAYS))]["ndvi"]
        if len(pre) < MIN_PRE_OBS:
            continue
        thr = pre.median() - drop
        if s.at[i, "ndvi"] < thr and s.at[i + 1, "ndvi"] < thr:
            return t
    return None


@lru_cache(maxsize=1)
def _load_model():
    import xgboost as xgb

    if not MODEL_PATH.exists():
        raise FileNotFoundError(f"{MODEL_PATH} missing — run scripts/train_attribution.py")
    clf = xgb.XGBClassifier()
    clf.load_model(MODEL_PATH)
    meta = json.loads(META_PATH.read_text())
    return clf, meta


def predict_cause(features: dict) -> dict:
    """Return {'cause': str, 'confidence': float, 'probabilities': {class: p}}."""
    clf, meta = _load_model()
    x = np.array([[features.get(n, np.nan) for n in meta["feature_names"]]], dtype=float)
    p = clf.predict_proba(x)[0]
    names = meta["class_names"]
    k = int(np.argmax(p))
    return {
        "cause": names[k],
        "confidence": round(float(p[k]), 3),
        "probabilities": {n: round(float(v), 3) for n, v in zip(names, p)},
        "model_note": "Trained on European DISFOR labels (Sentinel-2); apply with caution in KP.",
    }
