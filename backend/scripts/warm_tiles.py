"""Pre-fetch live map tiles over KP into the proxy's disk cache (instant demo + offline map detail).

Run (backend must be running):  .venv\\Scripts\\python scripts\\warm_tiles.py [--layers health,suitability] [--zooms 9,10]
Requests go through the running API (/api/forest/tiles/...), so all Earth Engine traffic shares the
server's single throttle and user-facing requests keep priority. Only tiles that overlap KP.
"""
from __future__ import annotations

import argparse
import math
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shapely.geometry import box  # noqa: E402

import requests  # noqa: E402

from app.core.aoi import kp_gdf  # noqa: E402

API = "http://localhost:8000"


def tile_bounds(x: int, y: int, z: int):
    n = 2 ** z
    lon = lambda i: i / n * 360 - 180  # noqa: E731
    lat = lambda j: math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * j / n))))  # noqa: E731
    return lon(x), lat(y + 1), lon(x + 1), lat(y)


def kp_tiles(z: int) -> list[tuple[int, int]]:
    kp = kp_gdf().geometry.iloc[0]
    w, s, e, n = kp.bounds
    k = 2 ** z
    x0, x1 = int((w + 180) / 360 * k), int((e + 180) / 360 * k)
    yy = lambda la: int((1 - math.asinh(math.tan(math.radians(la))) / math.pi) / 2 * k)  # noqa: E731
    y0, y1 = yy(n), yy(s)
    return [(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1) if kp.intersects(box(*tile_bounds(x, y, z)))]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--layers", default="health,suitability")
    ap.add_argument("--zooms", default="9,10")
    a = ap.parse_args()
    requests.get(f"{API}/api/health", timeout=60).raise_for_status()

    def fetch_tile(layer, z, x, y):
        r = requests.get(f"{API}/api/forest/tiles/{layer}/{z}/{x}/{y}.png", timeout=600)
        r.raise_for_status()

    jobs = [(l, z, x, y) for l in a.layers.split(",") for z in map(int, a.zooms.split(",")) for x, y in kp_tiles(z)]
    print(f"[warm] {len(jobs)} tiles ({a.layers} @ z{a.zooms})", flush=True)
    t, ok, failed = time.time(), 0, []
    with ThreadPoolExecutor(max_workers=3) as ex:
        futs = {ex.submit(fetch_tile, *j): j for j in jobs}
        for i, fu in enumerate(as_completed(futs), 1):
            try:
                fu.result()
                ok += 1
            except Exception as e:  # noqa: BLE001
                failed.append((futs[fu], str(e)[:80]))
            if i % 50 == 0:
                print(f"  {i}/{len(jobs)} done, {len(failed)} failed, {time.time()-t:.0f}s", flush=True)
    print(f"[gate] warmed {ok}/{len(jobs)} tiles in {time.time()-t:.0f}s; failed {len(failed)} {failed[:3]}", flush=True)


if __name__ == "__main__":
    main()
