"""Tile proxy for the live Earth Engine layers.

Why: the browser asked Earth Engine directly for dozens of tiles at once and got HTTP 429
(rate limit), so live layers filled in patchily. Now the browser asks this backend:
  * every tile is cached on disk (per day, per layer), so a tile is computed once
  * at most MAX_CONCURRENT requests go to Earth Engine at a time
  * 429/5xx responses are retried with backoff; an expired map id is refreshed once
  * offline (or when EE fails) the newest cached copy of the tile is served
"""
from __future__ import annotations

import datetime as dt
import random
import threading
import time

import requests
from fastapi import APIRouter, HTTPException, Response

from app.core.cache import NoDataError, cached
from app.core.config import SNAPSHOT_DIR, settings

router = APIRouter(prefix="/api/forest/tiles", tags=["forest-tiles"])

TILE_DIR = SNAPSHOT_DIR / "tiles"
LAYERS = {"health", "forest_mask", "suitability", "satellite_recent"}
MAX_CONCURRENT = 4
MAX_ATTEMPTS = 6
_sem = threading.BoundedSemaphore(MAX_CONCURRENT)
_refresh_lock = threading.Lock()
_session = requests.Session()


def _layers(force: bool = False) -> dict:
    from app.modules.forest import routes  # late import: routes owns the layer definitions

    if force:
        with _refresh_lock:
            p = SNAPSHOT_DIR / "forest_layers.json"
            if p.exists():
                p.unlink()
    return routes.layers()


def _tile_path(day: str, layer: str, z: int, x: int, y: int):
    return TILE_DIR / day / layer / str(z) / str(x) / f"{y}.png"


def _newest_cached(layer: str, z: int, x: int, y: int):
    if not TILE_DIR.exists():
        return None
    for day_dir in sorted(TILE_DIR.iterdir(), reverse=True):
        p = _tile_path(day_dir.name, layer, z, x, y)
        if p.exists():
            return p
    return None


def _png(data: bytes, stale: bool = False) -> Response:
    return Response(content=data, media_type="image/png",
                    headers={"Cache-Control": "public, max-age=3600", "X-Tile-Stale": "1" if stale else "0"})


def fetch_tile(layer: str, z: int, x: int, y: int) -> bytes:
    """Return PNG bytes for a tile (cache -> Earth Engine with throttle/retry). Raises on failure."""
    day = dt.date.today().isoformat()
    path = _tile_path(day, layer, z, x, y)
    if path.exists():
        return path.read_bytes()
    if settings.offline:
        raise NoDataError("offline")

    info = _layers()
    if info.get("_stale"):
        raise NoDataError("layer definitions are stale (Earth Engine unavailable)")
    url = info[layer]["url"]
    refreshed = False
    for attempt in range(MAX_ATTEMPTS):
        with _sem:
            try:
                r = _session.get(url.format(z=z, x=x, y=y), timeout=120)
            except requests.RequestException:
                r = None
        if r is not None and r.status_code == 200:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_bytes(r.content)
            tmp.replace(path)
            return r.content
        code = r.status_code if r is not None else 0
        if code in (400, 401, 403, 404) and not refreshed:  # map id expired -> new one
            url = _layers(force=True)[layer]["url"]
            refreshed = True
            continue
        if code in (0, 429, 500, 502, 503, 504):
            time.sleep(min(2 ** attempt, 12) + random.random())
            continue
        break
    raise RuntimeError(f"Earth Engine tile {layer}/{z}/{x}/{y} failed (HTTP {code})")


@router.get("/{layer}/{z}/{x}/{y}.png")
def tile(layer: str, z: int, x: int, y: int):
    if layer not in LAYERS or not (0 <= z <= 18) or not (0 <= x < 2 ** z) or not (0 <= y < 2 ** z):
        raise HTTPException(404)
    try:
        return _png(fetch_tile(layer, z, x, y))
    except Exception as e:  # noqa: BLE001
        old = _newest_cached(layer, z, x, y)
        if old is not None:
            return _png(old.read_bytes(), stale=True)
        raise HTTPException(503, f"tile unavailable: {str(e)[:150]}") from e
