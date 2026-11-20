"""Earth Engine dataset IDs — every ID here was verified to load (step 4 gate, 2026-11-20)."""

S2_SR = "COPERNICUS/S2_SR_HARMONIZED"
CLOUD_SCORE_PLUS = "GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED"
S1_GRD = "COPERNICUS/S1_GRD"
PK_LULC = "projects/sat-io/open-datasets/pk-lulc"            # images img1990..img2020, band b1
HANSEN = "UMD/hansen/global_forest_change_2025_v1_13"
WORLDCOVER = "ESA/WorldCover/v200"
DYNAMIC_WORLD = "GOOGLE/DYNAMICWORLD/V1"
FIRMS = "FIRMS"
WDPA = "WCMC/WDPA/current/polygons"
GRIP4_ROADS = "projects/sat-io/open-datasets/GRIP4/South-East-Asia"  # approved change (covers KP)
CHIRPS = "UCSB-CHG/CHIRPS/DAILY"
ERA5_LAND = "ECMWF/ERA5_LAND/DAILY_AGGR"
DEM = "COPERNICUS/DEM/GLO30_2024_1"                           # approved change (GLO30 deprecated)
SOILGRIDS = {
    "ph": "projects/soilgrids-isric/phh2o_mean",
    "clay": "projects/soilgrids-isric/clay_mean",
    "sand": "projects/soilgrids-isric/sand_mean",
    "soc": "projects/soilgrids-isric/soc_mean",
}
MERIT_HYDRO = "MERIT/Hydro/v1_0_1"

# PK-LULC class values (GEE community catalog)
LULC_FOREST = 1
LULC_CLASSES = {1: "Forest", 3: "Agriculture", 4: "Rangeland", 5: "Wetlands", 6: "Barren",
                7: "Water", 8: "Built-up", 9: "Snow/Ice"}
