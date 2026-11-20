import json

import numpy as np
import pandas as pd
import pytest

from app.modules.forest import attribution as A


def _series(drop_day: int | None, gradual: bool = False, n_days: int = 730) -> pd.DataFrame:
    t = pd.date_range("2022-01-01", periods=n_days // 5, freq="5D")
    b4 = np.full(len(t), 300.0)
    b8 = np.full(len(t), 3500.0)
    b11 = np.full(len(t), 1500.0)
    b12 = np.full(len(t), 700.0)
    if drop_day is not None:
        i = drop_day // 5
        if gradual:
            ramp = np.linspace(0, 1, i)
            b8[:i] -= 1200 * ramp
            b11[:i] += 400 * ramp
        b4[i:] = 1200.0
        b8[i:] = 2000.0
        b11[i:] = 2600.0
        b12[i:] = 2200.0
    return pd.DataFrame({"t": t, "B04": b4, "B08": b8, "B11": b11, "B12": b12})


def test_mapping_is_disjoint_and_complete_for_disfor_labels():
    assert not set(A.LABEL_TO_CLASS) & A.EXCLUDED_LABELS
    assert set(A.LABEL_TO_CLASS.values()) == set(A.CLASS_NAMES)
    disfor = {110, 120, 121, 122, 123, 200, 211, 212, 213, 220, 221, 222, 230, 231, 232, 241, 242, 243, 245}
    assert disfor <= set(A.LABEL_TO_CLASS) | A.EXCLUDED_LABELS
    assert A.LABEL_TO_CLASS[220] == "logging" and A.LABEL_TO_CLASS[230] == "disease_drought"
    assert 200 in A.EXCLUDED_LABELS


def test_indices_match_formulas():
    df = A.add_indices(pd.DataFrame({"B04": [300], "B08": [3500], "B11": [1500], "B12": [700]}))
    assert df["ndvi"][0] == pytest.approx((3500 - 300) / 3800)
    assert df["nbr"][0] == pytest.approx((3500 - 700) / 4200)
    assert df["ndmi"][0] == pytest.approx((3500 - 1500) / 5000)


def test_abrupt_drop_features():
    s = _series(drop_day=500)
    f = A.event_features(s, s["t"].iloc[100])
    assert f is not None and set(f) == set(A.FEATURE_NAMES)
    assert f["ndvi_drop"] > 0.4 and f["nbr_drop"] > 0.5
    assert abs(f["ndvi_pre_slope"]) < 1e-6  # flat before an abrupt clear-cut


def test_gradual_decline_has_negative_pre_slope():
    s = _series(drop_day=500, gradual=True)
    f = A.event_features(s, s["t"].iloc[100])
    assert f["ndvi_pre_slope"] < 0 and f["ndvi_early_late_diff"] > 0


def test_estimate_event_date_finds_abrupt_break():
    s = _series(drop_day=500)
    d = A.estimate_event_date(s, s["t"].iloc[80], s["t"].iloc[-1])
    assert d == s["t"].iloc[100]
    assert A.estimate_event_date(_series(drop_day=None), "2022-06-01", "2023-12-31") is None


def test_insufficient_data_returns_none():
    s = _series(drop_day=None, n_days=40)
    assert A.event_features(s, s["t"].iloc[3]) is None


def test_saved_model_predicts_valid_distribution():
    if not A.MODEL_PATH.exists():
        pytest.skip("model not trained")
    meta = json.loads(A.META_PATH.read_text())
    assert meta["feature_names"] == A.FEATURE_NAMES
    s = _series(drop_day=500)
    out = A.predict_cause(A.event_features(s, s["t"].iloc[100]))
    assert out["cause"] in A.CLASS_NAMES
    assert sum(out["probabilities"].values()) == pytest.approx(1.0, abs=1e-2)
