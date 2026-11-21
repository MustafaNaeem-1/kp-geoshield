"""Pre-fetch before/after images + AI cause for the alerts a demo will open (backend must be running).

Picks every high-confidence alert in the top --top by priority plus the top --per-district alerts of
each district, and opens each one through the API, which caches images and attribution on disk.
Run:  .venv\\Scripts\\python scripts\\warm_alert_images.py [--top 60] [--per-district 2]
"""
from __future__ import annotations

import argparse
import sys
import time

import requests

API = "http://localhost:8000"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=60)
    ap.add_argument("--per-district", type=int, default=2)
    a = ap.parse_args()
    feats = requests.get(f"{API}/api/forest/alerts", timeout=60).json()["features"]
    picked, seen = [], set()
    for f in feats[: a.top]:  # already sorted: high-confidence first, then priority
        picked.append(f["properties"]["id"])
    per = {}
    for f in feats:
        d = f["properties"]["district"]
        if per.get(d, 0) < a.per_district:
            per[d] = per.get(d, 0) + 1
            picked.append(f["properties"]["id"])
    picked = [i for i in picked if not (i in seen or seen.add(i))]
    print(f"[warm] {len(picked)} alerts", flush=True)
    t, ok, failed = time.time(), 0, []
    for n, aid in enumerate(picked, 1):  # sequential on purpose: gentle on the shared quota
        p = requests.get(f"{API}/api/forest/alerts/{aid}", timeout=600).json()["properties"]
        if p.get("images", {}).get("before") and p.get("images", {}).get("after"):
            ok += 1
        else:
            failed.append((aid, p.get("images", {}).get("error")))
        if n % 10 == 0:
            print(f"  {n}/{len(picked)}  ok {ok}  failed {len(failed)}  {time.time()-t:.0f}s", flush=True)
    print(f"[gate] images cached for {ok}/{len(picked)} alerts in {time.time()-t:.0f}s; failed: {failed[:5]}", flush=True)
    sys.exit(0 if not failed else 1)


if __name__ == "__main__":
    main()
