"""KP province and district boundaries (geoBoundaries gbOpen PAK, public domain, 2019 edition)."""
from __future__ import annotations

import json
from functools import lru_cache

import geopandas as gpd

from app.core.config import RAW_DIR

PROVINCE = "Khyber Pakhtunkhwa"
ADM1 = RAW_DIR / "geoBoundaries-PAK-ADM1.geojson"
ADM2 = RAW_DIR / "geoBoundaries-PAK-ADM2.geojson"


@lru_cache(maxsize=1)
def kp_gdf() -> gpd.GeoDataFrame:
    a1 = gpd.read_file(ADM1)
    return a1[a1["shapeName"] == PROVINCE][["shapeName", "geometry"]].reset_index(drop=True)


@lru_cache(maxsize=1)
def districts_gdf() -> gpd.GeoDataFrame:
    """The 31 districts whose representative point lies inside KP."""
    a2 = gpd.read_file(ADM2)
    pts = a2.copy()
    pts["geometry"] = a2.representative_point()
    inside = gpd.sjoin(pts, kp_gdf()[["geometry"]], predicate="within").index
    d = a2.loc[inside, ["shapeName", "geometry"]].rename(columns={"shapeName": "district"})
    return d.sort_values("district").reset_index(drop=True)


def district_names() -> list[str]:
    return districts_gdf()["district"].tolist()


def districts_geojson(simplify_m: float = 0.0) -> dict:
    d = districts_gdf()
    if simplify_m:
        d = d.copy()
        d["geometry"] = d.to_crs(32643).simplify(simplify_m).to_crs(4326)
    return json.loads(d.to_json())


def kp_ee():
    import ee

    g = kp_gdf().to_crs(32643).simplify(100).to_crs(4326).geometry.iloc[0]
    return ee.Geometry(g.__geo_interface__)


def districts_ee():
    import ee

    gj = districts_geojson(simplify_m=100)
    return ee.FeatureCollection(gj)


def district_ee(name: str):
    import ee

    d = districts_gdf()
    row = d[d["district"].str.lower() == name.lower()]
    if row.empty:
        raise KeyError(f"Unknown district: {name}")
    g = row.to_crs(32643).simplify(50).to_crs(4326).geometry.iloc[0]
    return ee.Geometry(g.__geo_interface__)
