"""Step 6b: XGBoost establishment model with spatial-block CV + SHAP importance.

Run:  .venv\\Scripts\\python scripts\\train_survival.py
Outputs data/models/survival_xgb.json, survival_meta.json, survival_shap.png
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import MODELS_DIR, PROCESSED_DIR  # noqa: E402
from app.modules.forest.survival import FEATURES  # noqa: E402

BLOCK_DEG = 0.25  # ~25 km spatial blocks -> GroupKFold prevents neighbouring pixels in train & test

LABELS = {
    "elevation": "Elevation (m)", "slope": "Slope (deg)", "northness": "North-facing", "eastness": "East-facing",
    "precip_annual": "Annual rainfall (mm)", "precip_monsoon": "Monsoon rainfall (mm)",
    "t_mean": "Mean temperature (C)", "t_summer_max": "Summer max temp (C)", "soil_ph": "Soil pH",
    "soil_clay": "Soil clay (g/kg)", "soil_sand": "Soil sand (g/kg)", "soil_soc": "Soil organic carbon",
    "twi": "Topographic wetness", "dist_stream_m": "Distance to stream (m)",
}


def main() -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import shap
    import xgboost as xgb
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import GroupKFold

    df = pd.read_csv(PROCESSED_DIR / "survival_samples.csv").dropna(subset=FEATURES + ["established"])
    X, y = df[FEATURES].to_numpy(float), df["established"].astype(int).to_numpy()
    blocks = (np.floor(df["lon"] / BLOCK_DEG).astype(int).astype(str) + "_" +
              np.floor(df["lat"] / BLOCK_DEG).astype(int).astype(str)).to_numpy()
    print(f"[gate] samples {len(df)} | class balance {np.bincount(y).tolist()} | spatial blocks {len(set(blocks))}")
    params = dict(n_estimators=400, max_depth=5, learning_rate=0.05, subsample=0.8, colsample_bytree=0.8,
                  eval_metric="auc", n_jobs=-1)
    oof = np.zeros(len(y))
    aucs = []
    for k, (tr, te) in enumerate(GroupKFold(n_splits=5).split(X, y, blocks)):
        m = xgb.XGBClassifier(**params).fit(X[tr], y[tr])
        oof[te] = m.predict_proba(X[te])[:, 1]
        aucs.append(roc_auc_score(y[te], oof[te]))
        print(f"  fold {k}: AUC {aucs[-1]:.3f}")
    auc = roc_auc_score(y, oof)
    print(f"[gate] spatial-block 5-fold CV AUC = {auc:.3f} (folds {min(aucs):.3f}-{max(aucs):.3f})")

    model = xgb.XGBClassifier(**params).fit(X, y)
    model.save_model(MODELS_DIR / "survival_xgb.json")
    sv = shap.TreeExplainer(model).shap_values(X)
    imp = sorted(zip(FEATURES, np.abs(sv).mean(0).tolist()), key=lambda t: -t[1])

    fig, ax = plt.subplots(figsize=(7, 5), dpi=150)
    names = [LABELS[f] for f, _ in imp][::-1]
    ax.barh(names, [v for _, v in imp][::-1], color="#2e7d32")
    ax.set_xlabel("mean |SHAP value| (impact on establishment probability, log-odds)")
    ax.set_title(f"What drives tree establishment in KP (spatial CV AUC {auc:.2f})")
    fig.tight_layout()
    fig.savefig(MODELS_DIR / "survival_shap.png")

    (MODELS_DIR / "survival_meta.json").write_text(json.dumps({
        "features": FEATURES, "feature_labels": LABELS,
        "label_definition": "PK-LULC rangeland/barren/agriculture 2010 -> forest 2020 with S2 NDVI(Jun-Sep 2024) >= 0.4 "
                            "(established) vs stayed non-forest (not established). Proxy for survival, not field data.",
        "n_samples": int(len(df)), "class_counts": np.bincount(y).tolist(),
        "cv": {"scheme": f"GroupKFold(5) on {BLOCK_DEG} deg spatial blocks", "auc": round(auc, 4),
               "fold_aucs": [round(a, 4) for a in aucs]},
        "shap_importance": [{"feature": f, "label": LABELS[f], "mean_abs_shap": round(v, 4)} for f, v in imp],
    }, indent=1))
    print("[gate] SHAP importance:", [(f, round(v, 3)) for f, v in imp])
    print("[gate] saved survival_xgb.json, survival_meta.json, survival_shap.png")


if __name__ == "__main__":
    main()
