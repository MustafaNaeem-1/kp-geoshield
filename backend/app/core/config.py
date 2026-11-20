"""Application settings loaded from backend/.env."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BACKEND_DIR / ".env")

DATA_DIR = BACKEND_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
MODELS_DIR = DATA_DIR / "models"
SNAPSHOT_DIR = DATA_DIR / "snapshots"


def _flag(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    ee_project: str = os.getenv("EE_PROJECT", "").strip()
    firms_key: str = os.getenv("FIRMS_KEY", "").strip()
    offline: bool = _flag("OFFLINE")
    cors_origins: tuple[str, ...] = tuple(
        o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()
    )


settings = Settings()

for _d in (RAW_DIR, PROCESSED_DIR, MODELS_DIR, SNAPSHOT_DIR):
    _d.mkdir(parents=True, exist_ok=True)
