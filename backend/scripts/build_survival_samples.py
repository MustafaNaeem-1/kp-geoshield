"""Step 6a: stratified samples (covariates + establishment label) across KP -> data/processed/survival_samples.csv

Sampled district-by-district (one KP-wide request exceeds Earth Engine's interactive time limit).
"""
from __future__ import annotations

import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import PROCESSED_DIR  # noqa: E402
from app.core.ee_client import ee_status, init_ee  # noqa: E402

PER_CLASS_PER_DISTRICT = 165  # ~5,100 per class over 31 districts (plan: ~10k total)


def one(name: str) -> list[dict]:
    from app.core.aoi import district_ee
    from app.modules.forest.survival import samples

    rows = []
    for f in samples(district_ee(name), per_class=PER_CLASS_PER_DISTRICT).getInfo()["features"]:
        p = dict(f["properties"])
        p["lon"], p["lat"] = f["geometry"]["coordinates"]
        p["district"] = name
        rows.append(p)
    return rows


def main() -> None:
    assert init_ee(), ee_status()
    from app.core.aoi import district_names
    from app.modules.forest.survival import FEATURES

    t = time.time()
    rows, failed = [], []
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(one, n): n for n in district_names()}
        for fu in as_completed(futs):
            n = futs[fu]
            try:
                r = fu.result()
                rows += r
                print(f"  {n:18} {len(r):4d} samples", flush=True)
            except Exception as e:  # noqa: BLE001
                failed.append(n)
                print(f"  {n:18} FAILED {str(e)[:150]}", flush=True)
    df = pd.DataFrame(rows).drop_duplicates(subset=["lon", "lat"])
    out = PROCESSED_DIR / "survival_samples.csv"
    df.to_csv(out, index=False)
    print(f"[gate] {len(df)} samples from {31 - len(failed)}/31 districts in {time.time()-t:.0f}s -> {out.name}; failed: {failed}")
    print("[gate] per class:", df["established"].value_counts().to_dict())
    print("[gate] NaNs per feature:", {c: int(df[c].isna().sum()) for c in FEATURES if df[c].isna().any()} or "none")
    print(df[FEATURES].describe().T[["mean", "min", "max"]].round(2))


if __name__ == "__main__":
    main()
