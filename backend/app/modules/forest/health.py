"""F1 Canopy health: z-score of recent NDVI/NDMI vs the same calendar window in the 3 previous years.

class 1 = healthy (z > -1), 2 = stressed (-2 < z <= -1), 3 = severe (z <= -2), within the forest mask.
z = min(z_ndvi, z_ndmi) (the worse of greenness and canopy moisture). Baseline std is floored at
0.03 so near-constant pixels do not produce huge z-scores from tiny differences.
"""
from __future__ import annotations

import datetime as dt

import ee

from app.modules.forest import s2
from app.modules.forest.forest_mask import forest_mask

RECENT_DAYS = 45
BASELINE_YEARS = 3
STD_FLOOR = 0.03
HEALTH_PALETTE = ["2e7d32", "f9a825", "c62828"]


def windows(today: dt.date | None = None):
    end = today or dt.date.today()
    start = end - dt.timedelta(days=RECENT_DAYS)
    base = [(start.replace(year=start.year - k), end.replace(year=end.year - k)) for k in range(1, BASELINE_YEARS + 1)]
    return (start, end), base


def health_image(region: ee.Geometry, today: dt.date | None = None) -> ee.Image:
    (rs, re_), base = windows(today)
    recent = s2.composite(region, str(rs), str(re_)).select(["ndvi", "ndmi"])
    pooled = ee.ImageCollection([])
    for bs, be in base:
        pooled = pooled.merge(s2.collection(region, str(bs), str(be)).select(["ndvi", "ndmi"]))
    mean = pooled.mean()
    std = pooled.reduce(ee.Reducer.stdDev()).rename(["ndvi", "ndmi"]).max(STD_FLOOR)
    z = recent.subtract(mean).divide(std)
    zmin = z.select("ndvi").min(z.select("ndmi")).rename("z")
    cls = ee.Image(1).where(zmin.lte(-1), 2).where(zmin.lte(-2), 3).rename("health")
    return cls.addBands(zmin).updateMask(zmin.mask()).updateMask(forest_mask()).clip(region)


def health_tiles(region: ee.Geometry, today: dt.date | None = None) -> dict:
    img = health_image(region, today).select("health")
    m = img.getMapId({"min": 1, "max": 3, "palette": HEALTH_PALETTE})
    (rs, re_), base = windows(today)
    return {
        "url": m["tile_fetcher"].url_format,
        "legend": {"1": "Healthy", "2": "Stressed", "3": "Severe decline"},
        "palette": HEALTH_PALETTE,
        "recent_window": [str(rs), str(re_)],
        "baseline_windows": [[str(a), str(b)] for a, b in base],
    }


def district_health_stats(districts: ee.FeatureCollection, region: ee.Geometry, scale: int = 100) -> list[dict]:
    img = health_image(region).select("health")
    out = img.reduceRegions(collection=districts, reducer=ee.Reducer.frequencyHistogram(), scale=scale, tileScale=4)
    rows = []
    for f in out.getInfo()["features"]:
        hist = f["properties"].get("histogram") or {}
        tot = sum(hist.values()) or 1
        rows.append({
            "district": f["properties"]["district"],
            "pct_healthy": round(100 * hist.get("1", 0) / tot, 1),
            "pct_stressed": round(100 * hist.get("2", 0) / tot, 1),
            "pct_severe": round(100 * hist.get("3", 0) / tot, 1),
            "observed_forest_pixels": int(tot) if hist else 0,
        })
    return rows
