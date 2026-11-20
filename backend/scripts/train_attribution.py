"""Step 3: train the disturbance-cause classifier on DISFOR.

Run:  .venv\\Scripts\\python scripts\\train_attribution.py
Outputs data/models/attribution_xgb.json + attribution_meta.json (with CV metrics).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import RAW_DIR  # noqa: E402
from app.modules.forest.attribution import (  # noqa: E402
    CLASS_NAMES, EXCLUDED_LABELS, FEATURE_NAMES, LABEL_TO_CLASS, META_PATH, MODEL_PATH, PRE_DAYS, event_features,
)

D = RAW_DIR / "disfor"
RNG = np.random.default_rng(42)


def load():
    px = pd.read_parquet(D / "pixel_data.parquet", columns=["sample_id", "timestamps", "B04", "B08", "B11", "B12", "clear"])
    px = px[px["clear"]].drop(columns="clear")
    px["t"] = pd.to_datetime(px["timestamps"])
    labels = pd.read_parquet(D / "labels.parquet")
    for c in ("start", "end"):  # labels are UTC-aware, pixel timestamps are naive dates
        labels[c] = pd.to_datetime(labels[c]).dt.tz_convert(None)
    samples = pd.read_parquet(D / "samples.parquet", columns=["sample_id", "cluster_id", "confidence"])
    return px, labels, samples


def main() -> None:
    px, labels, samples = load()
    present = set(int(v) for v in labels["label"].unique())
    unmapped = present - set(LABEL_TO_CLASS) - EXCLUDED_LABELS
    print(f"[gate] labels present: {sorted(present)}")
    print(f"[gate] unmapped labels (must be empty): {sorted(unmapped)}")
    assert not unmapped, unmapped

    samples = samples[samples["confidence"] != "low"]
    labels = labels[labels["sample_id"].isin(samples["sample_id"]) & labels["label"].isin(list(LABEL_TO_CLASS))]
    series = {sid: g.sort_values("t") for sid, g in px.groupby("sample_id")}
    t_min = px["t"].min()

    rows, skipped = [], 0
    for r in labels.itertuples(index=False):
        s = series.get(r.sample_id)
        if s is None:
            skipped += 1
            continue
        start = pd.Timestamp(r.start)
        if int(r.label) == 110:
            # pseudo-event inside the undisturbed segment, with a full pre-window available
            lo = max(start, t_min + pd.Timedelta(days=PRE_DAYS))
            hi = pd.Timestamp(r.end) - pd.Timedelta(days=60)
            if hi <= lo:
                skipped += 1
                continue
            start = lo + (hi - lo) * float(RNG.random())
        f = event_features(s, start)
        if f is None:
            skipped += 1
            continue
        f.update(sample_id=int(r.sample_id), label=int(r.label), cls=LABEL_TO_CLASS[int(r.label)])
        rows.append(f)

    df = pd.DataFrame(rows).merge(samples[["sample_id", "cluster_id"]], on="sample_id")
    # cluster_id is a string; samples without a cluster form their own group
    key = df["cluster_id"].astype("object")
    key = key.where(key.notna(), "sample_" + df["sample_id"].astype(str))
    df["group"] = pd.factorize(key)[0]
    print(f"[gate] CV groups: {df['group'].nunique()}")
    print(f"[gate] events built: {len(df)}  skipped (insufficient data): {skipped}")
    print("[gate] events per class:", df["cls"].value_counts().to_dict())

    from sklearn.metrics import classification_report, confusion_matrix, f1_score
    from sklearn.model_selection import StratifiedGroupKFold
    from sklearn.utils.class_weight import compute_sample_weight
    import xgboost as xgb

    X = df[FEATURE_NAMES].to_numpy(float)
    y = df["cls"].map({c: i for i, c in enumerate(CLASS_NAMES)}).to_numpy()
    groups = df["group"].to_numpy()
    params = dict(n_estimators=400, max_depth=5, learning_rate=0.05, subsample=0.8,
                  colsample_bytree=0.8, objective="multi:softprob", eval_metric="mlogloss", n_jobs=-1)

    oof = np.zeros(len(y), int)
    for k, (tr, te) in enumerate(StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=42).split(X, y, groups)):
        m = xgb.XGBClassifier(**params)
        m.fit(X[tr], y[tr], sample_weight=compute_sample_weight("balanced", y[tr]))
        oof[te] = m.predict(X[te])
        print(f"  fold {k}: macro-F1 {f1_score(y[te], oof[te], average='macro'):.3f}")

    macro = f1_score(y, oof, average="macro")
    report = classification_report(y, oof, target_names=CLASS_NAMES, output_dict=True, zero_division=0)
    cm = confusion_matrix(y, oof)
    print(f"\n[gate] grouped 5-fold CV macro-F1 = {macro:.3f}")
    print(classification_report(y, oof, target_names=CLASS_NAMES, digits=3, zero_division=0))
    print("[gate] confusion matrix (rows=true, cols=pred):", CLASS_NAMES)
    print(pd.DataFrame(cm, index=CLASS_NAMES, columns=CLASS_NAMES))

    final = xgb.XGBClassifier(**params)
    final.fit(X, y, sample_weight=compute_sample_weight("balanced", y))
    final.save_model(MODEL_PATH)
    imp = sorted(zip(FEATURE_NAMES, final.feature_importances_.tolist()), key=lambda t: -t[1])
    META_PATH.write_text(json.dumps({
        "class_names": CLASS_NAMES, "feature_names": FEATURE_NAMES, "label_to_class": LABEL_TO_CLASS,
        "n_events": int(len(df)), "events_per_class": df["cls"].value_counts().to_dict(),
        "cv": {"scheme": "StratifiedGroupKFold(5) by DISFOR cluster_id", "macro_f1": round(macro, 4),
               "per_class": {c: {k: round(v, 4) for k, v in report[c].items()} for c in CLASS_NAMES},
               "confusion_matrix": cm.tolist()},
        "feature_importance": imp,
        "source": "DISFOR doi:10.57967/hf/7983 (EUPL-1.2)",
    }, indent=1))
    print(f"\n[gate] saved {MODEL_PATH.name} ({MODEL_PATH.stat().st_size:,} B) and {META_PATH.name}")


if __name__ == "__main__":
    main()
