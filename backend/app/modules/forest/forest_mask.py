"""Forest mask = PK-LULC 2020 forest ∪ (Hansen treecover2000 ≥ 30% and no loss) ∪ WorldCover 2021 trees."""
from __future__ import annotations

import ee

from app.core.assets import HANSEN, LULC_FOREST, PK_LULC, WORLDCOVER

HANSEN_TREECOVER_MIN = 30


def pk_lulc(year: int) -> ee.Image:
    return ee.ImageCollection(PK_LULC).filter(ee.Filter.eq("system:index", f"img{year}")).first().select("b1")


def forest_mask() -> ee.Image:
    lulc = pk_lulc(2020).eq(LULC_FOREST).unmask(0)
    h = ee.Image(HANSEN)
    hansen = h.select("treecover2000").gte(HANSEN_TREECOVER_MIN).And(h.select("loss").eq(0)).unmask(0)
    wc = ee.ImageCollection(WORLDCOVER).first().select("Map").eq(10).unmask(0)
    return lulc.Or(hansen).Or(wc).selfMask().rename("forest")
