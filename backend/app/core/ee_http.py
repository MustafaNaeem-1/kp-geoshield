"""Shared, rate-limit-aware downloader for Earth Engine tile/thumbnail URLs.

Earth Engine's request quota is shared by everything using the project (this server, background
scripts), so a burst from one place makes others get HTTP 429. Every EE download goes through here:
  * PRIORITY requests (what a user is looking at, e.g. alert before/after images) have their own
    slots, so background tile fetching can never starve them
  * BACKGROUND requests (map tiles, warm-up scripts) share a small pool
  * 429 / 5xx / network errors are retried with exponential backoff (+ jitter), honouring
    Retry-After when Earth Engine sends it, for up to ~2 minutes in total
"""
from __future__ import annotations

import random
import threading
import time

import requests

PRIORITY, BACKGROUND = "priority", "background"
_slots = {PRIORITY: threading.BoundedSemaphore(2), BACKGROUND: threading.BoundedSemaphore(3)}
_session = requests.Session()
RETRY_CODES = {0, 429, 500, 502, 503, 504}
MAX_ATTEMPTS = 9                 # backoff 1,2,4,8,16,20,20,20 s ≈ 2 min worst case
MAX_SLEEP = 20


class EEFetchError(RuntimeError):
    def __init__(self, status: int, msg: str):
        super().__init__(msg)
        self.status = status


def _sleep_for(attempt: int, resp: requests.Response | None) -> float:
    ra = resp.headers.get("Retry-After") if resp is not None else None
    if ra and ra.isdigit():
        return min(float(ra), MAX_SLEEP) + random.random()
    return min(2 ** attempt, MAX_SLEEP) + random.random()


def ee_get(url: str, kind: str = BACKGROUND, timeout: float = 120, max_attempts: int = MAX_ATTEMPTS,
           sleep=None, session: requests.Session | None = None) -> bytes:
    """GET an Earth Engine URL with throttling + retry. Returns the body or raises EEFetchError."""
    s = session or _session
    sleep = sleep or time.sleep
    resp = None
    for attempt in range(max_attempts):
        with _slots[kind]:
            try:
                resp = s.get(url, timeout=timeout)
            except requests.RequestException:
                resp = None
        code = resp.status_code if resp is not None else 0
        if code == 200:
            return resp.content
        if code not in RETRY_CODES:
            raise EEFetchError(code, f"Earth Engine returned HTTP {code}")
        if attempt < max_attempts - 1:
            sleep(_sleep_for(attempt, resp))  # sleep outside the slot so others can proceed
    raise EEFetchError(code, f"Earth Engine still rate-limited after {max_attempts} attempts (HTTP {code})")
