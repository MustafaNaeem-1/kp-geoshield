"""Step 5: run change detection for every KP district, attribute the top alerts, validate vs Hansen 2024.

Run:  .venv\\Scripts\\python scripts\\precompute_alerts.py [--districts Swat,Haripur] [--top 5] [--skip-validation]
Writes data/processed/alerts/<district>.geojson, alerts_all.geojson, alerts_summary.json, hansen_validation.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import PROCESSED_DIR  # noqa: E402
from app.core.ee_client import ee_status, init_ee  # noqa: E402

OUT = PROCESSED_DIR / "alerts"


def attribute(props: dict) -> dict:
    from app.modules.forest.attribution import estimate_event_date, event_features, predict_cause
    from app.modules.forest.change import pixel_series
    from app.modules.forest.fires import fire_near

    rs = dt.date.fromisoformat(props["recent_window"][1])
    pe = dt.date.fromisoformat(props["prior_window"][1])
    s = pixel_series(props["lon"], props["lat"], str(rs - dt.timedelta(days=760)), str(rs))
    ev = estimate_event_date(s, pe, rs)
    if ev is None:
        return {"cause": "unknown", "confidence": None, "note": "no sustained NDVI break found at the alert centroid"}
    feats = event_features(s, ev)
    if feats is None:
        return {"cause": "unknown", "confidence": None, "note": "not enough clear observations"}
    out = predict_cause(feats)
    out["event_date"] = str(ev.date())
    if fire_near(props["lon"], props["lat"], out["event_date"]):
        out.update(cause="fire", fire_override=True)
    return out


def run_district(name: str, top: int) -> dict:
    from app.core.aoi import district_ee
    from app.modules.forest.change import detect

    t = time.time()
    fc = detect(district_ee(name), name)
    feats = fc["features"]
    with ThreadPoolExecutor(max_workers=5) as ex:
        futs = {ex.submit(attribute, f["properties"]): f for f in feats[:top]}
        for fu in as_completed(futs):
            try:
                futs[fu]["properties"]["attribution"] = fu.result()
            except Exception as e:  # noqa: BLE001
                futs[fu]["properties"]["attribution"] = {"cause": "unknown", "error": str(e)[:200]}
    (OUT / f"{name}.geojson").write_text(json.dumps(fc))
    types = {}
    for f in feats:
        types[f["properties"]["type"]] = types.get(f["properties"]["type"], 0) + 1
    return {"district": name, "alerts": len(feats), "area_ha": round(sum(f["properties"]["area_ha"] for f in feats), 1),
            "by_type": types, "truncated": fc["meta"]["truncated"], "seconds": round(time.time() - t, 1),
            "recent_window": fc["meta"]["recent_window"], "prior_window": fc["meta"]["prior_window"]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--districts", default="")
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--skip-validation", action="store_true")
    a = ap.parse_args()
    assert init_ee(), ee_status()
    from app.core.aoi import district_names, kp_ee

    OUT.mkdir(parents=True, exist_ok=True)
    names = [d.strip() for d in a.districts.split(",") if d.strip()] or district_names()
    print(f"[run] {len(names)} districts, top {a.top} attributed each", flush=True)
    summary, failed = [], []
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = {ex.submit(run_district, n, a.top): n for n in names}
        for fu in as_completed(futs):
            n = futs[fu]
            try:
                r = fu.result()
                summary.append(r)
                print(f"  {n:18} {r['alerts']:5d} alerts {r['area_ha']:8.1f} ha {r['by_type']} "
                      f"{'TRUNCATED ' if r['truncated'] else ''}({r['seconds']}s)", flush=True)
            except Exception as e:  # noqa: BLE001
                failed.append({"district": n, "error": str(e)[:300]})
                print(f"  {n:18} FAILED: {str(e)[:200]}", flush=True)

    summary.sort(key=lambda r: r["district"])
    allf = []
    for r in summary:
        allf += json.loads((OUT / f"{r['district']}.geojson").read_text())["features"]
    from app.modules.forest.change import sort_key
    allf.sort(key=lambda f: sort_key(f["properties"]))
    (PROCESSED_DIR / "alerts_all.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": allf}))
    (PROCESSED_DIR / "alerts_summary.json").write_text(json.dumps(
        {"generated": dt.datetime.now().isoformat(timespec="seconds"), "districts": summary, "failed": failed}, indent=1))
    print(f"[gate] districts ok {len(summary)}/{len(names)}, failed {len(failed)}; total alerts {len(allf)}, "
          f"total area {sum(f['properties']['area_ha'] for f in allf):.1f} ha", flush=True)
    attributed = [f["properties"]["attribution"] for f in allf if "attribution" in f["properties"]]
    causes = {}
    for x in attributed:
        causes[x["cause"]] = causes.get(x["cause"], 0) + 1
    print(f"[gate] attributed {len(attributed)}: {causes}", flush=True)

    if not a.skip_validation:
        from app.modules.forest.change import validate_against_hansen

        t = time.time()
        v = validate_against_hansen(kp_ee())
        (PROCESSED_DIR / "hansen_validation.json").write_text(json.dumps(v, indent=1))
        print(f"[gate] Hansen-2024 validation (KP, pixel level, {time.time()-t:.0f}s): {v}", flush=True)


if __name__ == "__main__":
    main()
