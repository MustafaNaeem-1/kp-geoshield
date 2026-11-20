"""/api/forest/* endpoints (plan: API table)."""
from __future__ import annotations

import datetime as dt
import json
import threading
import time
from pathlib import Path

import requests
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from app.core import aoi
from app.core.cache import NoDataError, cached, read_snapshot, write_snapshot
from app.core.config import MODELS_DIR, PROCESSED_DIR, SNAPSHOT_DIR, settings
from app.core.ee_client import ee_status, init_ee

router = APIRouter(prefix="/api/forest", tags=["forest"])
ALERTS_ALL = PROCESSED_DIR / "alerts_all.geojson"
ALERTS_DIR = PROCESSED_DIR / "alerts"
THUMBS = SNAPSHOT_DIR / "thumbs"
THUMBS.mkdir(parents=True, exist_ok=True)
_alerts_lock = threading.Lock()

H = 3600


def _ee():
    if not init_ee():
        raise RuntimeError(f"Earth Engine unavailable: {ee_status()['error']}")


def _serve(key: str, ttl: float, fn):
    try:
        return cached(key, ttl, fn)
    except NoDataError as e:
        raise HTTPException(503, str(e)) from e


# ---------------- layers ----------------
@router.get("/layers")
def layers():
    def live():
        _ee()
        import ee

        from app.modules.forest import s2
        from app.modules.forest.forest_mask import forest_mask
        from app.modules.forest.health import health_tiles
        from app.modules.forest.survival import suitability_tiles

        kp = aoi.kp_ee()
        end = dt.date.today()
        rgb = s2.composite(kp, str(end - dt.timedelta(days=60)), str(end)).getMapId(s2.rgb_vis())
        fm = forest_mask().clip(kp).getMapId({"palette": ["1b5e20"]})
        return {
            "health": health_tiles(kp),
            "forest_mask": {"url": fm["tile_fetcher"].url_format, "palette": ["1b5e20"]},
            "suitability": suitability_tiles(kp),
            "satellite_recent": {"url": rgb["tile_fetcher"].url_format,
                                 "window": [str(end - dt.timedelta(days=60)), str(end)]},
        }
    return _serve("forest_layers", 2 * H, live)


OVERLAYS = SNAPSHOT_DIR / "overlays"


@router.get("/overlays")
def overlays():
    p = OVERLAYS / "overlays.json"
    if not p.exists():
        return {"layers": {}}
    return json.loads(p.read_text())


@router.get("/overlays/{name}")
def overlay_png(name: str):
    path = OVERLAYS / Path(name).name
    if path.suffix != ".png" or not path.exists():
        raise HTTPException(404)
    return FileResponse(path, media_type="image/png")


# ---------------- alerts ----------------
def _load_alerts() -> dict:
    if not ALERTS_ALL.exists():
        raise HTTPException(503, "alerts not precomputed — run scripts/precompute_alerts.py")
    return json.loads(ALERTS_ALL.read_text())


@router.get("/alerts")
def alerts(district: str | None = None, type: str | None = None, min_priority: float = 0, limit: int = 2000,
           confidence: str | None = None):
    fc = _load_alerts()
    fs = [f for f in fc["features"]
          if (not district or f["properties"]["district"].lower() == district.lower())
          and (not type or f["properties"]["type"] == type)
          and (not confidence or f["properties"].get("confidence") == confidence)
          and f["properties"]["priority"] >= min_priority]
    return {"type": "FeatureCollection", "features": fs[:limit], "total": len(fs)}


def _find_alert(alert_id: str) -> dict:
    for f in _load_alerts()["features"]:
        if f["properties"]["id"] == alert_id:
            return f
    raise HTTPException(404, f"alert {alert_id} not found")


@router.get("/alerts/{alert_id}")
def alert_detail(alert_id: str):
    f = _find_alert(alert_id)
    p = dict(f["properties"])
    if "attribution" not in p:
        def live_attr():
            _ee()
            from scripts.precompute_alerts import attribute
            return attribute(p)
        try:
            p["attribution"] = cached(f"attr_{alert_id}", 30 * 24 * H, live_attr)
        except NoDataError as e:
            p["attribution"] = {"cause": "unknown", "error": str(e)[:200]}
    p["images"] = _thumbs(p)
    return {"type": "Feature", "geometry": f["geometry"], "properties": p}


def _thumbs(p: dict) -> dict:
    out = {}
    names = {k: THUMBS / f"{p['id']}_{k}.png" for k in ("before", "after")}
    if not all(n.exists() for n in names.values()) and not settings.offline:
        try:
            _ee()
            from app.modules.forest.change import thumbnails
            rec = tuple(dt.date.fromisoformat(x) for x in p["recent_window"])
            pri = tuple(dt.date.fromisoformat(x) for x in p["prior_window"])
            urls = thumbnails(p["lon"], p["lat"], rec, pri)
            for k, path in names.items():
                # EE answers 429 when the map is also pulling tiles; back off and retry
                for attempt in range(4):
                    r = requests.get(urls[k], timeout=120)
                    if r.status_code != 429:
                        break
                    time.sleep(2 * (attempt + 1))
                r.raise_for_status()
                path.write_bytes(r.content)
        except Exception as e:  # noqa: BLE001
            return {"error": f"{type(e).__name__}: {str(e)[:150]}"}
    for k, path in names.items():
        if path.exists():
            out[k] = f"/api/forest/thumbs/{path.name}"
    return out


@router.get("/thumbs/{name}")
def thumb(name: str):
    path = (THUMBS / Path(name).name)
    if not path.exists():
        raise HTTPException(404)
    return FileResponse(path, media_type="image/png")


@router.post("/alerts/refresh")
def refresh_alerts(district: str = Query(...)):
    if district.lower() not in {d.lower() for d in aoi.district_names()}:
        raise HTTPException(404, f"unknown district {district}")
    try:
        _ee()
    except RuntimeError as e:
        raise HTTPException(503, str(e)) from e
    from scripts.precompute_alerts import run_district

    name = next(d for d in aoi.district_names() if d.lower() == district.lower())
    summary = run_district(name, top=5)
    with _alerts_lock:
        fc = _load_alerts()
        keep = [f for f in fc["features"] if f["properties"]["district"] != name]
        new = json.loads((ALERTS_DIR / f"{name}.geojson").read_text())["features"]
        from app.modules.forest.change import sort_key
        allf = sorted(keep + new, key=lambda f: sort_key(f["properties"]))
        ALERTS_ALL.write_text(json.dumps({"type": "FeatureCollection", "features": allf}))
    return summary


# ---------------- districts ----------------
def _district_stats() -> dict:
    def live():
        _ee()
        from app.modules.forest.health import district_health_stats
        from app.modules.forest.stats import district_forest_stats
        dfc = aoi.districts_ee()
        forest = {r["district"]: r for r in district_forest_stats(dfc)}
        health = {r["district"]: r for r in district_health_stats(dfc, aoi.kp_ee())}
        return {"forest": forest, "health": health}
    return _serve("district_stats", 6 * H, live)


@router.get("/districts")
def districts():
    stats = _district_stats()
    fires = _fires(7)["fires"]
    alerts_by = {}
    if ALERTS_ALL.exists():
        for f in _load_alerts()["features"]:
            d = f["properties"]["district"]
            a = alerts_by.setdefault(d, {"alerts": 0, "alert_area_ha": 0.0})
            a["alerts"] += 1
            a["alert_area_ha"] = round(a["alert_area_ha"] + f["properties"]["area_ha"], 2)
    gj = aoi.districts_geojson(simplify_m=150)
    import geopandas as gpd
    from shapely.geometry import Point
    dg = aoi.districts_gdf()
    fire_d = {}
    for fz in fires:
        hit = dg[dg.contains(Point(fz["lon"], fz["lat"]))]
        if not hit.empty:
            n = hit.iloc[0]["district"]
            fire_d[n] = fire_d.get(n, 0) + 1
    for f in gj["features"]:
        n = f["properties"]["district"]
        f["properties"].update(stats["forest"].get(n, {}))
        f["properties"].update({k: v for k, v in stats["health"].get(n, {}).items() if k != "district"})
        f["properties"].update(alerts_by.get(n, {"alerts": 0, "alert_area_ha": 0.0}))
        f["properties"]["fires_7d"] = fire_d.get(n, 0)
    gj["_cached_at"], gj["_stale"] = stats.get("_cached_at"), stats.get("_stale")
    return gj


@router.get("/districts/{name}")
def district_detail(name: str):
    names = {d.lower(): d for d in aoi.district_names()}
    if name.lower() not in names:
        raise HTTPException(404, f"unknown district {name}")
    n = names[name.lower()]

    def live():
        _ee()
        from app.modules.forest.stats import loss_by_year
        return {"district": n, "hansen_loss_km2_by_year": loss_by_year(aoi.district_ee(n))}
    out = _serve(f"district_{n}", 24 * H, live)
    stats = _district_stats()
    out["forest"] = stats["forest"].get(n)
    out["health"] = stats["health"].get(n)
    return out


@router.get("/summary")
def summary():
    stats = _district_stats()
    f = list(stats["forest"].values())
    h = list(stats["health"].values())
    tot_obs = sum(x["observed_forest_pixels"] for x in h) or 1
    al = _load_alerts()["features"] if ALERTS_ALL.exists() else []
    gen = json.loads((PROCESSED_DIR / "alerts_summary.json").read_text()) if (PROCESSED_DIR / "alerts_summary.json").exists() else {}
    val = json.loads((PROCESSED_DIR / "hansen_validation.json").read_text()) if (PROCESSED_DIR / "hansen_validation.json").exists() else None
    return {
        "province": "Khyber Pakhtunkhwa", "districts": len(f),
        "area_km2": round(sum(x["district_km2"] for x in f)),
        "forest_km2_mask": round(sum(x["mask_forest_km2"] for x in f)),
        "forest_km2_pk_lulc_2020": round(sum(x["lulc_forest_km2_2020"] for x in f)),
        "pct_stressed": round(100 * sum(x["pct_stressed"] * x["observed_forest_pixels"] for x in h) / 100 / tot_obs, 1),
        "pct_severe": round(100 * sum(x["pct_severe"] * x["observed_forest_pixels"] for x in h) / 100 / tot_obs, 1),
        "alerts": len(al), "alert_area_ha": round(sum(x["properties"]["area_ha"] for x in al), 1),
        "alerts_generated": gen.get("generated"), "hansen_validation": val,
        "_cached_at": stats.get("_cached_at"), "_stale": stats.get("_stale"),
    }


# ---------------- fires ----------------
def _fires(days: int) -> dict:
    def live():
        _ee()
        from app.modules.forest.fires import get_fires
        return {"days": days, "fires": get_fires(aoi.kp_ee(), days)}
    return _serve(f"fires_{days}", H, live)


@router.get("/fires")
def fires(days: int = Query(7, ge=1, le=10)):
    return _fires(days)


# ---------------- survival / plantations ----------------
@router.get("/survival/explain")
def survival_explain():
    out = {}
    for key, fname in (("survival", "survival_meta.json"), ("attribution", "attribution_meta.json")):
        p = MODELS_DIR / fname
        if p.exists():
            m = json.loads(p.read_text())
            m.pop("label_to_class", None)
            out[key] = m
    if not out:
        raise HTTPException(503, "models not trained yet")
    out["shap_chart"] = "/api/forest/survival/shap.png" if (MODELS_DIR / "survival_shap.png").exists() else None
    return out


@router.get("/survival/shap.png")
def survival_shap():
    p = MODELS_DIR / "survival_shap.png"
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p, media_type="image/png")


@router.get("/survival/drought-stress")
def survival_drought():
    def live():
        from app.modules.forest.survival import drought_stress
        dg = aoi.districts_gdf()
        pts = dg.representative_point()
        points = [{"district": d, "lat": p.y, "lon": p.x} for d, p in zip(dg["district"], pts)]
        return {"districts": drought_stress(points)}
    return _serve("drought_stress", 3 * H, live)
