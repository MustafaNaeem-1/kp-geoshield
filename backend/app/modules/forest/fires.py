"""F5 Active fires: NASA FIRMS. Uses the FIRMS area API (VIIRS NRT) when FIRMS_KEY is set,
otherwise the Earth Engine FIRMS collection (MODIS, ~1 day lag)."""
from __future__ import annotations

import csv
import datetime as dt
import io

import ee
import requests

from app.core.assets import FIRMS
from app.core.config import settings

KP_BBOX = (69.2, 31.0, 74.2, 37.1)  # w, s, e, n
MIN_CONFIDENCE = 30


def fires_ee(region: ee.Geometry, days: int = 7) -> list[dict]:
    end = ee.Date(dt.datetime.utcnow().isoformat())
    col = ee.ImageCollection(FIRMS).filterBounds(region).filterDate(end.advance(-days, "day"), end)

    def to_points(img):
        date = ee.Date(img.get("system:time_start")).format("YYYY-MM-dd")
        m = img.select("confidence").gte(MIN_CONFIDENCE).selfMask()
        vec = m.addBands(img.select(["T21", "confidence"])).reduceToVectors(
            geometry=region, scale=1000, geometryType="centroid",
            reducer=ee.Reducer.max().forEach(["T21", "confidence"]),
            labelProperty="fire", maxPixels=1e9, bestEffort=True)
        return vec.map(lambda f: f.set("date", date))

    fc = ee.FeatureCollection(col.map(to_points)).flatten()
    out = []
    for f in fc.limit(5000).getInfo()["features"]:
        lon, lat = f["geometry"]["coordinates"]
        out.append({"lon": round(lon, 5), "lat": round(lat, 5), "date": f["properties"]["date"],
                    "brightness_k": f["properties"].get("T21"), "confidence": f["properties"].get("confidence"),
                    "source": "MODIS (Earth Engine FIRMS)"})
    return out


def fires_api(days: int = 7) -> list[dict]:
    w, s, e, n = KP_BBOX
    url = (f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{settings.firms_key}/VIIRS_SNPP_NRT/"
           f"{w},{s},{e},{n}/{min(days, 10)}")
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    rows = list(csv.DictReader(io.StringIO(r.text)))
    return [{"lon": float(x["longitude"]), "lat": float(x["latitude"]), "date": x["acq_date"],
             "brightness_k": float(x["bright_ti4"]), "confidence": x["confidence"],
             "source": "VIIRS S-NPP NRT (FIRMS API)"} for x in rows]


def fire_near(lon: float, lat: float, date: str, km: float = 1.0, days: int = 10) -> bool:
    """True when FIRMS (Earth Engine, MODIS) saw a fire within `km` and ±`days` of `date`."""
    d = ee.Date(date)
    col = ee.ImageCollection(FIRMS).filterDate(d.advance(-days, "day"), d.advance(days + 1, "day"))
    hit = col.select("confidence").max().gte(MIN_CONFIDENCE).reduceRegion(
        ee.Reducer.anyNonZero(), ee.Geometry.Point([lon, lat]).buffer(km * 1000), 1000).get("confidence")
    return bool(ee.Algorithms.If(hit, hit, 0).getInfo())


FOREST_SHARE_MIN = 30  # % of the ~1 km fire pixel that must be forest to call it a forest fire


def annotate_land(fires: list[dict]) -> list[dict]:
    """Add land type under each fire: % forest within the ~1 km FIRMS pixel + dominant PK-LULC class.

    Lets the UI tell a forest fire from crop-stubble burning or brick kilns on farmland.
    """
    if not fires:
        return fires
    from app.core.assets import LULC_CLASSES
    from app.modules.forest.forest_mask import forest_mask, pk_lulc

    fc = ee.FeatureCollection([ee.Feature(ee.Geometry.Point([f["lon"], f["lat"]]).buffer(500), {"i": i})
                               for i, f in enumerate(fires)])
    img = forest_mask().unmask(0).multiply(100).rename("forest_pct").addBands(pk_lulc(2020).rename("lulc"))
    reducer = ee.Reducer.mean().forEach(["forest_pct"]).combine(ee.Reducer.mode().forEach(["lulc"]), sharedInputs=False)
    res = img.reduceRegions(collection=fc, reducer=reducer, scale=30).getInfo()["features"]
    for r in res:
        p = r["properties"]
        f = fires[p["i"]]
        pct = round(p.get("forest_pct") or 0, 1)
        lulc = p.get("lulc")
        f["forest_pct"] = pct
        f["land_class"] = LULC_CLASSES.get(int(lulc), "Unknown") if lulc is not None else "Unknown"
        f["in_forest"] = pct >= FOREST_SHARE_MIN
    return fires


def get_fires(region: ee.Geometry, days: int = 7) -> list[dict]:
    fires = fires_api(days) if settings.firms_key else fires_ee(region, days)
    return annotate_land(fires)
