"""F2 Logging & encroachment alerts.

Rules (plan F2):
  logging      : inside forest mask, dNDVI < -0.20 AND dNBR < -0.15 (recent 60 d vs same window last year)
  encroachment : inside forest mask, Dynamic World mode label = trees last year and crops/built/bare now
Patches are vectorised at 20 m and kept if >= 0.5 ha. Sentinel-1 VH change is attached as evidence.
Priority (0-100) = 50*size + 30*inside protected area + 20*road proximity.
"""
from __future__ import annotations

import datetime as dt
import math

import ee
import pandas as pd

from app.core.assets import DYNAMIC_WORLD, GRIP4_ROADS, HANSEN, S1_GRD, WDPA
from app.modules.forest import s2
from app.modules.forest.forest_mask import HANSEN_TREECOVER_MIN, forest_mask, pk_lulc

WINDOW_DAYS = 60
D_NDVI = -0.20
D_NBR = -0.15
D_NDVI_ENCROACH = -0.10     # approved change: encroachment needs spectral evidence too
EXCLUDE_LULC = [3, 8]       # approved change: PK-LULC agriculture, built-up
# Approved change (confidence tiers): validated vs Hansen 2024 on 5 districts, 'high' alerts overlapped
# Hansen loss 35% of the time vs 15% for all alerts.
HIGH_CONF_DNDVI = -0.30
HIGH_CONF_DNBR = -0.25


def confidence_tier(props: dict) -> str:
    dn, db = props.get("dndvi"), props.get("dnbr")
    if dn is not None and db is not None and dn < HIGH_CONF_DNDVI and db < HIGH_CONF_DNBR:
        return "high"
    return "standard"


def sort_key(props: dict) -> tuple:
    return (0 if props.get("confidence") == "high" else 1, -props["priority"])
MIN_AREA_M2 = 5000          # 0.5 ha
VECTOR_SCALE = 20
ROAD_RADIUS_M = 5000
DW_TREES = 1
DW_ENCROACH = [4, 6, 7]     # crops, built, bare
TYPE_LOGGING, TYPE_ENCROACH = 1, 2
TYPE_NAMES = {TYPE_LOGGING: "logging", TYPE_ENCROACH: "encroachment"}


def windows(today: dt.date | None = None):
    end = today or dt.date.today()
    start = end - dt.timedelta(days=WINDOW_DAYS)
    return (start, end), (start.replace(year=start.year - 1), end.replace(year=end.year - 1))


def _dw_mode(region, a, b):
    return ee.ImageCollection(DYNAMIC_WORLD).filterBounds(region).filterDate(str(a), str(b)).select("label").mode()


def change_image(region: ee.Geometry, recent, prior) -> ee.Image:
    (ra, rb), (pa, pb) = recent, prior
    now = s2.composite(region, str(ra), str(rb)).select(["ndvi", "nbr"])
    before = s2.composite(region, str(pa), str(pb)).select(["ndvi", "nbr"])
    d = now.subtract(before).rename(["dndvi", "dnbr"])
    # Approved change (step 5): drop PK-LULC 2020 farmland/built-up pixels (orchards & village edges
    # were the main false positives), and require a real greenness drop for encroachment.
    not_agri_built = pk_lulc(2020).remap(EXCLUDE_LULC, [0] * len(EXCLUDE_LULC), 1).unmask(1)
    fm = forest_mask().unmask(0).And(not_agri_built)
    logging_ = d.select("dndvi").lt(D_NDVI).And(d.select("dnbr").lt(D_NBR)).And(fm)
    dw_before, dw_now = _dw_mode(region, pa, pb), _dw_mode(region, ra, rb)
    # Approved change (step 5, KP-wide check): encroachment only inside *strict* forest
    # (PK-LULC 2020 forest or Hansen treecover2000 >= 30%); WorldCover-only "trees" were field trees/orchards.
    strict = pk_lulc(2020).eq(1).Or(ee.Image(HANSEN).select("treecover2000").gte(HANSEN_TREECOVER_MIN)).unmask(0)
    encroach = (dw_before.eq(DW_TREES).And(dw_now.remap(DW_ENCROACH, [1] * len(DW_ENCROACH), 0))
                .And(d.select("dndvi").lt(D_NDVI_ENCROACH)).And(fm).And(strict))
    typ = ee.Image(0).where(logging_, TYPE_LOGGING).where(encroach, TYPE_ENCROACH).rename("type").selfMask()
    return typ.addBands(d).clip(region)


def _s1_vh(region, a, b):
    return (ee.ImageCollection(S1_GRD).filterBounds(region).filterDate(str(a), str(b))
            .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VH"))
            .filter(ee.Filter.eq("instrumentMode", "IW")).select("VH").median())


def detect(region: ee.Geometry, district: str, today: dt.date | None = None, max_features: int = 2000) -> dict:
    recent, prior = windows(today)
    img = change_image(region, recent, prior)
    vecs = img.select(["type", "dndvi", "dnbr"]).reduceToVectors(
        geometry=region, scale=VECTOR_SCALE, geometryType="polygon", eightConnected=True,
        labelProperty="type", reducer=ee.Reducer.mean().forEach(["dndvi", "dnbr"]),
        maxPixels=1e10, tileScale=4)
    vecs = vecs.map(lambda f: f.set("area_m2", f.geometry().area(1))).filter(ee.Filter.gte("area_m2", MIN_AREA_M2))

    vh = _s1_vh(region, *recent).subtract(_s1_vh(region, *prior)).rename("s1_vh_change_db")
    pa = ee.FeatureCollection(WDPA).filterBounds(region)
    pa_img = ee.Image(0).paint(pa, 1).rename("in_protected")
    roads = ee.FeatureCollection(GRIP4_ROADS).filterBounds(region.buffer(ROAD_RADIUS_M))
    road_d = roads.distance(ROAD_RADIUS_M).unmask(ROAD_RADIUS_M).rename("road_dist_m")
    vecs = vh.reduceRegions(collection=vecs, reducer=ee.Reducer.mean().setOutputs(["s1_vh_change_db"]), scale=30, tileScale=4)
    vecs = pa_img.reduceRegions(collection=vecs, reducer=ee.Reducer.max().setOutputs(["in_protected"]), scale=30, tileScale=4)
    vecs = road_d.reduceRegions(collection=vecs, reducer=ee.Reducer.min().setOutputs(["road_dist_m"]), scale=30, tileScale=4)

    feats = vecs.limit(max_features).getInfo()["features"]
    out = []
    for i, f in enumerate(feats):
        p = f["properties"]
        area_ha = p["area_m2"] / 1e4
        c = _centroid(f["geometry"])
        road = p.get("road_dist_m")
        size_s = min(1.0, math.log10(area_ha + 1) / 2)          # 1.0 at ~99 ha
        road_s = 1 - min(road if road is not None else ROAD_RADIUS_M, ROAD_RADIUS_M) / ROAD_RADIUS_M
        prio = round(100 * (0.5 * size_s + 0.3 * (p.get("in_protected") or 0) + 0.2 * road_s), 1)
        out.append({
            "type": "Feature", "geometry": f["geometry"],
            "properties": {
                "id": f"{district.lower().replace(' ', '-')}-{recent[1]:%Y%m%d}-{i:04d}",
                "district": district, "type": TYPE_NAMES[int(p["type"])],
                "area_ha": round(area_ha, 2), "lon": round(c[0], 5), "lat": round(c[1], 5),
                "dndvi": _r(p.get("dndvi")), "dnbr": _r(p.get("dnbr")),
                "s1_vh_change_db": _r(p.get("s1_vh_change_db")),
                "in_protected_area": bool(p.get("in_protected")), "road_dist_m": _r(road, 0),
                "priority": prio,
                "recent_window": [str(recent[0]), str(recent[1])], "prior_window": [str(prior[0]), str(prior[1])],
            }})
    for f in out:
        f["properties"]["confidence"] = confidence_tier(f["properties"])
    out.sort(key=lambda f: sort_key(f["properties"]))
    return {"type": "FeatureCollection", "features": out,
            "meta": {"district": district, "recent_window": [str(r) for r in recent],
                     "prior_window": [str(p) for p in prior], "truncated": len(feats) >= max_features}}


def _r(v, nd=3):
    return None if v is None else round(float(v), nd)


def _centroid(geom: dict) -> tuple[float, float]:
    from shapely.geometry import shape

    c = shape(geom).representative_point()
    return c.x, c.y


def thumbnails(lon: float, lat: float, recent, prior, buffer_m: int = 600) -> dict:
    """Before/after Sentinel-2 RGB PNG URLs around an alert."""
    box = ee.Geometry.Point([lon, lat]).buffer(buffer_m).bounds()
    vis = s2.rgb_vis()
    out = {}
    for key, (a, b) in (("before", prior), ("after", recent)):
        img = s2.composite(box, str(a), str(b)).visualize(**vis)
        out[key] = img.getThumbURL({"region": box, "dimensions": 384, "format": "png"})
    return out


def pixel_series(lon: float, lat: float, start: str, end: str) -> pd.DataFrame:
    """Clear Sentinel-2 observations at a point (for cause attribution)."""
    pt = ee.Geometry.Point([lon, lat])
    rows = s2.collection(pt, start, end).select(["B4", "B8", "B11", "B12"]).getRegion(pt, 10).getInfo()
    df = pd.DataFrame(rows[1:], columns=rows[0]).dropna(subset=["B4", "B8", "B11", "B12"])
    df = df.rename(columns={"B4": "B04", "B8": "B08"})
    df["t"] = pd.to_datetime(df["time"], unit="ms")
    return df[["t", "B04", "B08", "B11", "B12"]].astype({"B04": float, "B08": float, "B11": float, "B12": float})


def validate_against_hansen(region: ee.Geometry, scale: int = 30) -> dict:
    """Pixel-level check of the logging rule for calendar 2024 vs Hansen lossyear == 24.

    prior = Jun-Oct 2023, recent = Jun-Oct 2024. Loss after Oct 2024 cannot be seen by these windows,
    so recall is a lower bound.
    """
    h = ee.Image("UMD/hansen/global_forest_change_2025_v1_13")
    img = change_image(region, (dt.date(2024, 6, 1), dt.date(2024, 10, 31)), (dt.date(2023, 6, 1), dt.date(2023, 10, 31)))
    det = img.select("type").eq(TYPE_LOGGING).unmask(0)
    ref = h.select("lossyear").eq(24).unmask(0)
    fm = forest_mask().unmask(0).Or(h.select("treecover2000").gte(30))
    code = det.multiply(2).add(ref).updateMask(fm).rename("c")
    hist = code.reduceRegion(ee.Reducer.frequencyHistogram(), region, scale, maxPixels=1e11, tileScale=8).getInfo()["c"]
    tn, fn, fp, tp = (int(hist.get(k, 0)) for k in ("0", "1", "2", "3"))
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "precision": round(prec, 3), "recall_lower_bound": round(rec, 3),
            "scale_m": scale, "windows": {"prior": "2023-06-01..2023-10-31", "recent": "2024-06-01..2024-10-31"}}
