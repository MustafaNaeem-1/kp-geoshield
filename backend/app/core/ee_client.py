"""Earth Engine initialisation (lazy, once per process)."""
from __future__ import annotations

import threading

from app.core.config import settings

_lock = threading.Lock()
_ready = False
_error: str | None = None


def init_ee() -> bool:
    """Initialise EE for settings.ee_project. Returns True when usable."""
    global _ready, _error
    if _ready:
        return True
    if settings.offline:
        _error = "OFFLINE=1"
        return False
    with _lock:
        if _ready:
            return True
        try:
            import ee

            if not settings.ee_project:
                raise RuntimeError("EE_PROJECT is not set in backend/.env")
            ee.Initialize(project=settings.ee_project)
            ee.Number(1).getInfo()  # round-trip proves credentials + project registration
            _ready, _error = True, None
        except Exception as exc:  # noqa: BLE001 — surfaced via ee_status()
            _ready, _error = False, f"{type(exc).__name__}: {exc}"
    return _ready


def ee_status() -> dict:
    return {"ready": _ready, "error": _error, "project": settings.ee_project}
