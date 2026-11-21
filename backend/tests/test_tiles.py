import datetime as dt
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.core import ee_http
from app.main import app
from app.modules.forest import tiles

PNG = b"\x89PNG\r\n\x1a\nfake"


@pytest.fixture
def tiledir(tmp_path, monkeypatch):
    monkeypatch.setattr(tiles, "TILE_DIR", tmp_path)
    return tmp_path


def _put(tiledir, day, layer="health", z=9, x=360, y=205, data=PNG):
    p = tiledir / day / layer / str(z) / str(x) / f"{y}.png"
    p.parent.mkdir(parents=True)
    p.write_bytes(data)


def test_rejects_unknown_layer_and_out_of_range_tiles(tiledir):
    c = TestClient(app)
    assert c.get("/api/forest/tiles/nope/9/360/205.png").status_code == 404
    assert c.get("/api/forest/tiles/health/9/9999/205.png").status_code == 404


def test_cached_tile_is_served_without_calling_earth_engine(tiledir, monkeypatch):
    _put(tiledir, dt.date.today().isoformat())
    monkeypatch.setattr(tiles, "_layers", lambda force=False: pytest.fail("EE called despite cache"))
    r = TestClient(app).get("/api/forest/tiles/health/9/360/205.png")
    assert r.status_code == 200 and r.content == PNG and r.headers["content-type"] == "image/png"


def test_offline_serves_newest_older_tile_or_503(tiledir, monkeypatch):
    monkeypatch.setattr(tiles, "settings", SimpleNamespace(offline=True))
    _put(tiledir, "2026-11-19", data=b"old")
    _put(tiledir, "2026-11-20", data=b"newer")
    c = TestClient(app)
    r = c.get("/api/forest/tiles/health/9/360/205.png")
    assert r.status_code == 200 and r.content == b"newer" and r.headers["x-tile-stale"] == "1"
    assert c.get("/api/forest/tiles/health/9/361/205.png").status_code == 503


class _Resp:
    def __init__(self, code, headers=None):
        self.status_code, self.content, self.headers = code, PNG, headers or {}


def test_tile_retries_on_429_then_caches(tiledir, monkeypatch):
    calls = []

    def fake_get(url, timeout):
        calls.append(url)
        return _Resp(429 if len(calls) < 3 else 200)

    monkeypatch.setattr(tiles, "settings", SimpleNamespace(offline=False))
    monkeypatch.setattr(tiles, "_layers", lambda force=False: {"health": {"url": "https://ee/{z}/{x}/{y}"}})
    monkeypatch.setattr(ee_http._session, "get", fake_get)
    monkeypatch.setattr(ee_http.time, "sleep", lambda s: None)
    assert tiles.fetch_tile("health", 9, 360, 205) == PNG
    assert len(calls) == 3 and calls[0] == "https://ee/9/360/205"
    assert tiles.fetch_tile("health", 9, 360, 205) == PNG and len(calls) == 3  # second time: from cache


def test_ee_get_honours_retry_after_and_gives_up_cleanly():
    waits, codes = [], iter([429, 503, 200])

    class S:
        def get(self, url, timeout):
            c = next(codes)
            return _Resp(c, {"Retry-After": "7"} if c == 429 else {})

    assert ee_http.ee_get("u", kind=ee_http.PRIORITY, sleep=waits.append, session=S()) == PNG
    assert 7 <= waits[0] < 8 and len(waits) == 2

    class Always429:
        def get(self, url, timeout):
            return _Resp(429)

    with pytest.raises(ee_http.EEFetchError) as e:
        ee_http.ee_get("u", sleep=lambda s: None, session=Always429(), max_attempts=3)
    assert e.value.status == 429

    class Forbidden:
        def get(self, url, timeout):
            return _Resp(403)

    with pytest.raises(ee_http.EEFetchError) as e:  # non-retryable: fail fast, no sleeping
        ee_http.ee_get("u", sleep=lambda s: pytest.fail("slept on 403"), session=Forbidden())
    assert e.value.status == 403
