"""Offline fallback: stitch KP-wide PNG overlays from the live EE map tiles (plan: offline fallback).

A single province-wide getThumbURL request fails (HTTP 400), so we fetch the same XYZ tiles the app
uses at zoom 8 and mosaic them. Web-Mercator tiles stitched edge-to-edge align exactly when placed as
a MapLibre image source by their corner coordinates.

Run:  .venv\\Scripts\\python scripts\\make_overlays.py [--zoom 8]
Writes data/snapshots/overlays/<layer>.png + overlays.json
"""
from __future__ import annotations

import argparse
import io
import json
import math
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import SNAPSHOT_DIR  # noqa: E402
from app.core.ee_client import ee_status, init_ee  # noqa: E402

OUT = SNAPSHOT_DIR / "overlays"
W, S, E, N = 69.2, 31.0, 74.2, 37.1


def tile_xy(lon: float, lat: float, z: int) -> tuple[int, int]:
    n = 2 ** z
    return int((lon + 180) / 360 * n), int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)


def tile_lon(x: int, z: int) -> float:
    return x / 2 ** z * 360 - 180


def tile_lat(y: int, z: int) -> float:
    return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / 2 ** z))))


def stitch(url_fmt: str, z: int) -> tuple[Image.Image, list[list[float]]]:
    x0, y0 = tile_xy(W, N, z)
    x1, y1 = tile_xy(E, S, z)
    canvas = Image.new("RGBA", ((x1 - x0 + 1) * 256, (y1 - y0 + 1) * 256), (0, 0, 0, 0))

    def get(xy):
        x, y = xy
        for attempt in range(3):
            r = requests.get(url_fmt.format(x=x, y=y, z=z), timeout=180)
            if r.ok:
                return xy, Image.open(io.BytesIO(r.content)).convert("RGBA")
            time.sleep(2 * (attempt + 1))
        raise RuntimeError(f"tile {z}/{x}/{y}: HTTP {r.status_code} {r.text[:120]}")

    jobs = [(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)]
    with ThreadPoolExecutor(max_workers=12) as ex:
        for (x, y), im in ex.map(get, jobs):
            canvas.paste(im, ((x - x0) * 256, (y - y0) * 256))
    w, e = tile_lon(x0, z), tile_lon(x1 + 1, z)
    n, s = tile_lat(y0, z), tile_lat(y1 + 1, z)
    return canvas, [[w, n], [e, n], [e, s], [w, s]]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--zoom", type=int, default=8)
    a = ap.parse_args()
    assert init_ee(), ee_status()
    from app.core.aoi import kp_ee
    from app.modules.forest.forest_mask import forest_mask
    from app.modules.forest.health import health_tiles
    from app.modules.forest.survival import suitability_tiles

    OUT.mkdir(parents=True, exist_ok=True)
    kp = kp_ee()
    makers = {
        "health": lambda: health_tiles(kp)["url"],
        "forest_mask": lambda: forest_mask().clip(kp).getMapId({"palette": ["1b5e20"]})["tile_fetcher"].url_format,
        "suitability": lambda: suitability_tiles(kp)["url"],
    }
    meta = {"zoom": a.zoom, "generated": time.strftime("%Y-%m-%dT%H:%M:%S"), "layers": {}}
    for name, make in makers.items():
        t = time.time()
        try:
            img, corners = stitch(make(), a.zoom)
        except Exception as e:  # noqa: BLE001
            print(f"[gate] {name}: FAILED {e}", flush=True)
            continue
        p = OUT / f"{name}.png"
        img.save(p, optimize=True)
        meta["layers"][name] = {"url": f"/api/forest/overlays/{name}.png", "coordinates": corners}
        opaque = sum(1 for px in img.getdata() if px[3] > 0) / (img.width * img.height)
        print(f"[gate] {name}.png {img.width}x{img.height}, {p.stat().st_size:,} B, {100*opaque:.1f}% non-empty, {time.time()-t:.0f}s", flush=True)
    (OUT / "overlays.json").write_text(json.dumps(meta, indent=1))


if __name__ == "__main__":
    main()
