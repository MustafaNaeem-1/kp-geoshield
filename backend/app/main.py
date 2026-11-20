"""KP GeoShield API entry point.

Run (from backend/):  .venv\\Scripts\\python -m uvicorn app.main:app --port 8000
"""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # lets routes import scripts.* helpers

from app.core.config import settings  # noqa: E402
from app.core.ee_client import ee_status, init_ee  # noqa: E402
from app.modules.forest.routes import router as forest_router  # noqa: E402

app = FastAPI(title="KP GeoShield API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(forest_router)


@app.get("/api/health")
def health() -> dict:
    init_ee()  # no-op once ready; makes the UI's live/offline badge accurate on first load
    return {
        "status": "ok",
        "offline": settings.offline,
        "ee_project_configured": bool(settings.ee_project),
        "earth_engine": ee_status(),
    }
