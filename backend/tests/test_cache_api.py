import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.core import cache
from app.core.config import PROCESSED_DIR


@pytest.fixture
def snapdir(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "SNAPSHOT_DIR", tmp_path)
    monkeypatch.setattr(cache, "settings", SimpleNamespace(offline=False))
    return tmp_path


def test_cache_serves_fresh_snapshot_without_calling(snapdir):
    calls = []
    assert cache.cached("k", 60, lambda: calls.append(1) or {"v": 1})["v"] == 1
    out = cache.cached("k", 60, lambda: calls.append(1) or {"v": 2})
    assert out["v"] == 1 and out["_stale"] is False and len(calls) == 1


def test_cache_refreshes_after_ttl(snapdir):
    cache.cached("k", 0.01, lambda: {"v": 1})
    time.sleep(0.05)
    assert cache.cached("k", 0.01, lambda: {"v": 2})["v"] == 2


def test_cache_falls_back_to_stale_on_error(snapdir):
    cache.cached("k", 0.01, lambda: {"v": 1})
    time.sleep(0.05)

    def boom():
        raise RuntimeError("EE down")

    out = cache.cached("k", 0.01, boom)
    assert out["v"] == 1 and out["_stale"] is True and "EE down" in out["_error"]


def test_offline_mode_uses_snapshot_and_never_calls(snapdir, monkeypatch):
    cache.cached("k", 0.01, lambda: {"v": 1})
    monkeypatch.setattr(cache, "settings", SimpleNamespace(offline=True))
    out = cache.cached("k", 0.01, lambda: pytest.fail("live call in offline mode"))
    assert out["v"] == 1 and out["_stale"] is True
    with pytest.raises(cache.NoDataError):
        cache.cached("missing", 1, lambda: {"v": 0})


def test_health_endpoint():
    from app.main import app
    r = TestClient(app).get("/api/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


@pytest.mark.skipif(not (PROCESSED_DIR / "alerts_all.geojson").exists(), reason="alerts not precomputed")
def test_alerts_endpoint_filters():
    from app.main import app
    c = TestClient(app)
    allf = c.get("/api/forest/alerts").json()
    assert allf["type"] == "FeatureCollection"
    if allf["features"]:
        d = allf["features"][0]["properties"]["district"]
        sub = c.get("/api/forest/alerts", params={"district": d}).json()
        assert sub["features"] and all(f["properties"]["district"] == d for f in sub["features"])
        hi = c.get("/api/forest/alerts", params={"min_priority": 50}).json()
        assert all(f["properties"]["priority"] >= 50 for f in hi["features"])
    assert c.get("/api/forest/alerts/does-not-exist").status_code == 404
