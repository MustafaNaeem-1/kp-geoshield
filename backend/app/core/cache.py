"""File-backed cache with TTL that doubles as the offline snapshot store.

cached(key, ttl, fn):
  * fresh snapshot (age < ttl)          -> served without calling fn
  * OFFLINE=1 or fn() raises            -> last snapshot served with "_stale": True (if one exists)
  * otherwise                           -> fn() result saved + served
"""
from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path
from typing import Any, Callable

from app.core.config import SNAPSHOT_DIR, settings

_locks: dict[str, threading.Lock] = {}
_guard = threading.Lock()


class NoDataError(RuntimeError):
    """Raised when neither live data nor a snapshot is available."""


def _path(key: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", key)
    return SNAPSHOT_DIR / f"{safe}.json"


def _lock(key: str) -> threading.Lock:
    with _guard:
        return _locks.setdefault(key, threading.Lock())


def read_snapshot(key: str) -> tuple[Any, float] | None:
    p = _path(key)
    if not p.exists():
        return None
    blob = json.loads(p.read_text(encoding="utf-8"))
    return blob["data"], blob["saved_at"]


def write_snapshot(key: str, data: Any) -> None:
    p = _path(key)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps({"saved_at": time.time(), "data": data}), encoding="utf-8")
    tmp.replace(p)


def _mark(data: Any, saved_at: float, stale: bool, error: str | None = None) -> Any:
    if isinstance(data, dict):
        data = dict(data)
        data["_cached_at"] = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(saved_at))
        data["_stale"] = stale
        if error:
            data["_error"] = error
    return data


def cached(key: str, ttl_s: float, fn: Callable[[], Any]) -> Any:
    with _lock(key):
        snap = read_snapshot(key)
        if snap and (settings.offline or time.time() - snap[1] < ttl_s):
            return _mark(snap[0], snap[1], stale=settings.offline)
        if settings.offline:
            raise NoDataError(f"OFFLINE=1 and no snapshot for '{key}'")
        try:
            data = fn()
        except Exception as exc:  # noqa: BLE001
            if snap:
                return _mark(snap[0], snap[1], stale=True, error=f"{type(exc).__name__}: {str(exc)[:200]}")
            raise NoDataError(f"live call failed and no snapshot for '{key}': {exc}") from exc
        write_snapshot(key, data)
        return _mark(data, time.time(), stale=False)
