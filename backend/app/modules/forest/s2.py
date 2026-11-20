"""Sentinel-2 L2A (harmonized) with Cloud Score+ masking, snow masking and spectral indices."""
from __future__ import annotations

import ee

from app.core.assets import CLOUD_SCORE_PLUS, S2_SR

CS_THRESHOLD = 0.6          # Cloud Score+ cs_cdf: keep pixels >= 0.6 (Google's recommended default)
NDSI_SNOW = 0.4
BANDS = ["B2", "B3", "B4", "B8", "B11", "B12"]


def _prep(img: ee.Image) -> ee.Image:
    clear = img.select("cs_cdf").gte(CS_THRESHOLD)
    scl = img.select("SCL")
    ndsi = img.normalizedDifference(["B3", "B11"])
    not_snow = scl.neq(11).And(ndsi.lt(NDSI_SNOW))
    not_bad = scl.neq(3).And(scl.neq(8)).And(scl.neq(9)).And(scl.neq(10))  # shadow / clouds / cirrus
    refl = img.select(BANDS)
    out = refl.addBands([
        img.normalizedDifference(["B8", "B4"]).rename("ndvi"),
        img.normalizedDifference(["B8", "B12"]).rename("nbr"),
        img.normalizedDifference(["B8", "B11"]).rename("ndmi"),
    ])
    return out.updateMask(clear.And(not_snow).And(not_bad)).copyProperties(img, ["system:time_start"])


def collection(region: ee.Geometry, start: str | ee.Date, end: str | ee.Date) -> ee.ImageCollection:
    s2 = ee.ImageCollection(S2_SR).filterBounds(region).filterDate(start, end)
    cs = ee.ImageCollection(CLOUD_SCORE_PLUS)
    return s2.linkCollection(cs, ["cs_cdf"]).map(_prep)


def composite(region: ee.Geometry, start, end) -> ee.Image:
    return collection(region, start, end).median()


def rgb_vis() -> dict:
    return {"bands": ["B4", "B3", "B2"], "min": 0, "max": 2500, "gamma": 1.2}
