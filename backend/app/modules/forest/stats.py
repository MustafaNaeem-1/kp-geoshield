"""F6 District dashboard numbers: forest area (PK-LULC 2020 and combined mask) and Hansen annual loss.

Also exposes get_forest_loss(region) — the hook the Flood module uses for curve-number adjustment.
"""
from __future__ import annotations

import ee

from app.core.assets import HANSEN, LULC_FOREST
from app.modules.forest.forest_mask import HANSEN_TREECOVER_MIN, forest_mask, pk_lulc

KM2 = 1e6


def district_forest_stats(districts: ee.FeatureCollection, scale: int = 90) -> list[dict]:
    area = ee.Image.pixelArea().divide(KM2)
    img = (area.updateMask(pk_lulc(2020).eq(LULC_FOREST)).rename("lulc_forest_km2")
           .addBands(area.updateMask(forest_mask()).rename("mask_forest_km2"))
           .addBands(area.rename("district_km2")))
    fc = img.reduceRegions(collection=districts, reducer=ee.Reducer.sum(), scale=scale, tileScale=4)
    return [{"district": f["properties"]["district"],
             "district_km2": round(f["properties"].get("district_km2", 0), 1),
             "lulc_forest_km2_2020": round(f["properties"].get("lulc_forest_km2", 0), 1),
             "mask_forest_km2": round(f["properties"].get("mask_forest_km2", 0), 1)}
            for f in fc.getInfo()["features"]]


def loss_by_year(region: ee.Geometry, scale: int = 30) -> dict[int, float]:
    """Hansen tree-cover loss (km², treecover2000 >= 30%) per year 2001-2025 inside region."""
    h = ee.Image(HANSEN)
    lost = ee.Image.pixelArea().divide(KM2).updateMask(h.select("loss").eq(1).And(
        h.select("treecover2000").gte(HANSEN_TREECOVER_MIN)))
    res = lost.addBands(h.select("lossyear")).reduceRegion(
        reducer=ee.Reducer.sum().group(groupField=1, groupName="year"),
        geometry=region, scale=scale, maxPixels=1e10, tileScale=4).getInfo()
    out = {2000 + int(g["year"]): round(g["sum"], 3) for g in res.get("groups", [])}
    return dict(sorted(out.items()))


def get_forest_loss(region: ee.Geometry, since_year: int = 2015) -> dict:
    """Hook for the Flood module: recent forest loss share in a basin/region."""
    by_year = loss_by_year(region)
    lost = sum(v for y, v in by_year.items() if y >= since_year)
    forest = ee.Image.pixelArea().divide(KM2).updateMask(forest_mask()).reduceRegion(
        ee.Reducer.sum(), region, 90, maxPixels=1e10, tileScale=4).getInfo().get("area", 0) or 0
    return {"forest_km2": round(forest, 2), "loss_km2_since": round(lost, 3), "since_year": since_year,
            "loss_fraction": round(lost / (forest + lost), 4) if forest + lost else 0.0}
