"""Step 5 gate: pixel-level validation of the logging rule vs Hansen 2024 loss, per district, summed for KP.

(A single KP-wide request exceeds Earth Engine's interactive limit; the method is unchanged.)
Run:  .venv\\Scripts\\python scripts\\validate_hansen.py
"""
from __future__ import annotations

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import PROCESSED_DIR  # noqa: E402
from app.core.ee_client import ee_status, init_ee  # noqa: E402


def main() -> None:
    assert init_ee(), ee_status()
    from app.core.aoi import district_ee, district_names
    from app.modules.forest.change import validate_against_hansen

    t = time.time()
    per, failed = {}, []
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(validate_against_hansen, district_ee(n)): n for n in district_names()}
        for fu in as_completed(futs):
            n = futs[fu]
            try:
                per[n] = fu.result()
                v = per[n]
                print(f"  {n:18} tp {v['tp']:6d} fp {v['fp']:6d} fn {v['fn']:6d}", flush=True)
            except Exception as e:  # noqa: BLE001
                failed.append(n)
                print(f"  {n:18} FAILED {str(e)[:120]}", flush=True)
    tp, fp, fn = (sum(v[k] for v in per.values()) for k in ("tp", "fp", "fn"))
    out = {"tp": tp, "fp": fp, "fn": fn, "precision": round(tp / (tp + fp), 3) if tp + fp else 0.0,
           "recall_lower_bound": round(tp / (tp + fn), 3) if tp + fn else 0.0, "scale_m": 30,
           "windows": {"prior": "2023-06-01..2023-10-31", "recent": "2024-06-01..2024-10-31"},
           "reference": "Hansen GFC v1.13 lossyear == 24 (pixel level)", "districts_ok": len(per), "failed": failed,
           "per_district": per}
    (PROCESSED_DIR / "hansen_validation.json").write_text(json.dumps(out, indent=1))
    print(f"[gate] KP logging rule vs Hansen 2024 ({len(per)}/31 districts, {time.time()-t:.0f}s): "
          f"precision {out['precision']}, recall (lower bound) {out['recall_lower_bound']}  tp={tp} fp={fp} fn={fn}")


if __name__ == "__main__":
    main()
