"""F4 Plantation establishment / planting suitability + live drought stress.

Label (self-derived from Pakistan's own land-cover maps, PK-LULC):
  established (1)     : rangeland/barren/agriculture in 2010 -> forest in 2020, and S2 NDVI (Jun-Sep 2024) >= 0.4
  not established (0) : rangeland/barren/agriculture in 2010 -> still one of those classes in 2020
This measures where tree cover *became and stayed* established, a proxy for seedling survival —
not field-verified plantation survival.
"""
from __future__ import annotations

import datetime as dt
import math

import ee
import requests

from app.core.assets import CHIRPS, DEM, ERA5_LAND, MERIT_HYDRO, SOILGRIDS
from app.modules.forest import s2
from app.modules.forest.forest_mask import pk_lulc

FROM_CLASSES = [3, 4, 6]
NDVI_MIN = 0.4
SAMPLE_SCALE = 90
SEED = 42
PER_CLASS = 5000
# soil_ph and soil_soc are still computed in covariates() but NOT used (approved change, step 6):
# SoilGrids pH/SOC are partly predicted from vegetation, which made the model circular.
FEATURES = ["elevation", "slope", "northness", "eastness", "precip_annual", "precip_monsoon",
            "t_mean", "t_summer_max", "soil_clay", "soil_sand", "twi", "dist_stream_m"]
SAMPLES_CSV = "survival_samples.csv"
RF_SAMPLES = 4000
SUIT_PALETTE = ["d73027", "fc8d59", "fee08b", "91cf60", "1a9850"]


def covariates() -> ee.Image:
    dem = ee.ImageCollection(DEM).select("DEM").mosaic().setDefaultProjection("EPSG:4326", None, 30)
    terrain = ee.Terrain.products(dem)
    asp = terrain.select("aspect").multiply(math.pi / 180)
    years = ee.List.sequence(2001, 2020)
    chirps = ee.ImageCollection(CHIRPS)
    annual = ee.ImageCollection(years.map(lambda y: chirps.filter(ee.Filter.calendarRange(y, y, "year")).sum())).mean()
    monsoon = ee.ImageCollection(years.map(lambda y: chirps.filter(ee.Filter.calendarRange(y, y, "year"))
                                           .filter(ee.Filter.calendarRange(7, 9, "month")).sum())).mean()
    era = ee.ImageCollection(ERA5_LAND).filterDate("2011-01-01", "2021-01-01")
    t_mean = era.select("temperature_2m").mean().subtract(273.15)
    t_summer = era.filter(ee.Filter.calendarRange(6, 8, "month")).select("temperature_2m_max").mean().subtract(273.15)
    soil = [ee.Image(SOILGRIDS[k]).select(0) for k in ("ph", "clay", "sand", "soc")]
    merit = ee.Image(MERIT_HYDRO)
    upa_m2 = merit.select("upa").multiply(1e6)
    slope_rad = terrain.select("slope").multiply(math.pi / 180).max(0.001)
    twi = upa_m2.divide(90).divide(slope_rad.tan()).log()
    streams = merit.select("upa").gt(10)
    dist = streams.fastDistanceTransform(256).sqrt().multiply(ee.Image.pixelArea().sqrt())
    return ee.Image.cat([
        dem.rename("elevation"), terrain.select("slope").rename("slope"),
        asp.cos().rename("northness"), asp.sin().rename("eastness"),
        annual.rename("precip_annual"), monsoon.rename("precip_monsoon"),
        t_mean.rename("t_mean"), t_summer.rename("t_summer_max"),
        soil[0].divide(10).rename("soil_ph"), soil[1].rename("soil_clay"), soil[2].rename("soil_sand"),
        soil[3].rename("soil_soc"), twi.rename("twi"), dist.rename("dist_stream_m"),
    ]).float()


def label_image(region: ee.Geometry) -> ee.Image:
    a, b = pk_lulc(2010), pk_lulc(2020)
    from_ok = a.remap(FROM_CLASSES, [1] * len(FROM_CLASSES), 0)
    ndvi24 = s2.composite(region, "2024-06-01", "2024-09-30").select("ndvi")
    pos = from_ok.And(b.eq(1)).And(ndvi24.gte(NDVI_MIN))
    neg = from_ok.And(b.remap(FROM_CLASSES, [1] * len(FROM_CLASSES), 0))
    return ee.Image(0).where(neg, 1).where(pos, 2).subtract(1).rename("established").updateMask(pos.Or(neg))


def samples(region: ee.Geometry, per_class: int = PER_CLASS) -> ee.FeatureCollection:
    img = covariates().addBands(label_image(region).toInt())
    return img.stratifiedSample(numPoints=per_class, classBand="established", region=region, scale=SAMPLE_SCALE,
                                seed=SEED, geometries=True, dropNulls=True, tileScale=8)


def _uploaded_samples() -> ee.FeatureCollection:
    """The verified KP samples (scripts/build_survival_samples.py), balanced subsample, as an in-request FC."""
    import pandas as pd

    from app.core.config import PROCESSED_DIR

    df = pd.read_csv(PROCESSED_DIR / SAMPLES_CSV).dropna(subset=FEATURES + ["established"])
    n = min(RF_SAMPLES // 2, df["established"].value_counts().min())
    df = df.groupby("established", group_keys=False).sample(n=n, random_state=SEED)
    feats = [ee.Feature(None, {**{f: float(r[f]) for f in FEATURES}, "established": int(r["established"])})
             for _, r in df.iterrows()]
    return ee.FeatureCollection(feats)


def suitability_tiles(region: ee.Geometry) -> dict:
    """GEE random forest (probability) trained on the same samples -> suitability on rangeland/barren land."""
    fc = _uploaded_samples()
    rf = ee.Classifier.smileRandomForest(numberOfTrees=100, seed=SEED).setOutputMode("PROBABILITY").train(
        features=fc, classProperty="established", inputProperties=FEATURES)
    plantable = pk_lulc(2020).remap([4, 6], [1, 1], 0).selfMask()
    prob = covariates().classify(rf).rename("suitability").updateMask(plantable).clip(region)
    m = prob.getMapId({"min": 0, "max": 1, "palette": SUIT_PALETTE})
    return {"url": m["tile_fetcher"].url_format, "palette": SUIT_PALETTE, "range": [0, 1],
            "applies_to": "PK-LULC 2020 rangeland & barren land (plantable)"}


# ---- live drought stress for young plantations (Open-Meteo, no key) ----
OPEN_METEO = "https://api.open-meteo.com/v1/forecast"


def drought_stress(points: list[dict], days: int = 16) -> list[dict]:
    """points: [{'district','lat','lon'}]. Water deficit = sum(ET0) - sum(precip) over the forecast."""
    r = requests.get(OPEN_METEO, timeout=60, params={
        "latitude": ",".join(f"{p['lat']:.4f}" for p in points),
        "longitude": ",".join(f"{p['lon']:.4f}" for p in points),
        "daily": "precipitation_sum,temperature_2m_max,et0_fao_evapotranspiration",
        "forecast_days": days, "timezone": "Asia/Karachi"})
    r.raise_for_status()
    data = r.json()
    data = data if isinstance(data, list) else [data]
    out = []
    for p, d in zip(points, data):
        dd = d["daily"]
        rain = sum(x or 0 for x in dd["precipitation_sum"])
        et0 = sum(x or 0 for x in dd["et0_fao_evapotranspiration"])
        hot = sum(1 for x in dd["temperature_2m_max"] if x is not None and x >= 35)
        deficit = et0 - rain
        level = "high" if deficit > 60 or hot >= 5 else "moderate" if deficit > 30 or hot >= 2 else "low"
        out.append({"district": p["district"], "lat": p["lat"], "lon": p["lon"],
                    "forecast_from": dd["time"][0], "forecast_to": dd["time"][-1],
                    "rain_mm": round(rain, 1), "et0_mm": round(et0, 1), "water_deficit_mm": round(deficit, 1),
                    "hot_days_ge35c": hot, "stress": level})
    order = {"high": 0, "moderate": 1, "low": 2}
    return sorted(out, key=lambda x: (order[x["stress"]], -x["water_deficit_mm"]))
