# Forest & Plantation Module: Dataset Catalog (exact file links)

Researched 2026-11-20. ✅ = file link verified on the source page · ⚠️ = partially verified / needs a check · ❌ = no public file found.

## Key finding
There is **no public, ready-made dataset of KP Billion Tree plantation sites with survival labels.**
- Code for Pakistan (2021) could map only ~12.6% of BTAP trees.
- The SERVIR/ICIMOD geospatial platform and WWF's 2025 dashboard are view-only.
- The Mehmood et al. 2025 BTAP paper publishes no data, only a supplementary .docx.

**Strategy:** open layers + labels we derive ourselves. Global labeled sets are used for pre-training and validation only.

---

## 1. Pakistan LULC + Carbon 1990–2020, 30 m ✅ (Pakistan-specific, most important)
- Paper: Waleed et al. 2024, *Env. Impact Assessment Review*, doi:10.1016/j.eiar.2023.107396 · License **CC BY 4.0**
- Record: https://zenodo.org/records/13982339 (2.7 GB total)

| File | Size | Direct download |
|---|---|---|
| lulc1990.tif | 100.1 MB | https://zenodo.org/records/13982339/files/lulc1990.tif?download=1 |
| lulc2000.tif | 98.3 MB | https://zenodo.org/records/13982339/files/lulc2000.tif?download=1 |
| lulc2010.tif | 94.4 MB | https://zenodo.org/records/13982339/files/lulc2010.tif?download=1 |
| lulc2020.tif | 102.5 MB | https://zenodo.org/records/13982339/files/lulc2020.tif?download=1 |
| total_carbon_1990.tif | 187.1 MB | https://zenodo.org/records/13982339/files/total_carbon_1990.tif?download=1 |
| total_carbon_2000.tif | 185.0 MB | https://zenodo.org/records/13982339/files/total_carbon_2000.tif?download=1 |
| total_carbon_2010.tif | 178.5 MB | https://zenodo.org/records/13982339/files/total_carbon_2010.tif?download=1 |
| total_carbon_2020.tif | 191.9 MB | https://zenodo.org/records/13982339/files/total_carbon_2020.tif?download=1 |
| Carbon_Pools_All.zip | 1.6 GB | https://zenodo.org/records/13982339/files/Carbon_Pools_All.zip?download=1 |

- **Earth Engine (no download needed):** `ee.ImageCollection("projects/sat-io/open-datasets/pk-lulc")`, `ee.ImageCollection("projects/sat-io/open-datasets/pk-carbon-stock")`. The author's repo uses `projects/pak-var/assets/lulc_pk/img1990…img2020`.
- **Class values:** 1 Forest · 3 Agriculture · 4 Rangeland · 5 Wetlands · 6 Barren · 7 Water · 8 Built-up · 9 Snow/Ice. The paper says 9 classes but the table shows 8; value 2 is unlisted.
- **Use:** KP forest mask. Pixels that are non-forest in 2010 and forest (1) in 2020 are **candidate afforestation sites**, which gives survival labels.

## 2. Hansen Global Forest Change v1.13 (2000–2025) ✅
- Earth Engine: `UMD/hansen/global_forest_change_2025_v1_13` · CC BY 4.0 · Hansen et al. 2013 *Science*
- Download page: https://storage.googleapis.com/earthenginepartners-hansen/GFC-2025-v1.13/download.html
- **KP tiles** (top-left corner naming; KP falls in `40N_060E` and `40N_070E`):

| Layer | 40N_060E | 40N_070E |
|---|---|---|
| treecover2000 | https://storage.googleapis.com/earthenginepartners-hansen/GFC-2025-v1.13/Hansen_GFC-2025-v1.13_treecover2000_40N_060E.tif | https://storage.googleapis.com/earthenginepartners-hansen/GFC-2025-v1.13/Hansen_GFC-2025-v1.13_treecover2000_40N_070E.tif |
| lossyear | https://storage.googleapis.com/earthenginepartners-hansen/GFC-2025-v1.13/Hansen_GFC-2025-v1.13_lossyear_40N_060E.tif | https://storage.googleapis.com/earthenginepartners-hansen/GFC-2025-v1.13/Hansen_GFC-2025-v1.13_lossyear_40N_070E.tif |
| gain | https://storage.googleapis.com/earthenginepartners-hansen/GFC-2025-v1.13/Hansen_GFC-2025-v1.13_gain_40N_060E.tif | https://storage.googleapis.com/earthenginepartners-hansen/GFC-2025-v1.13/Hansen_GFC-2025-v1.13_gain_40N_070E.tif |
| datamask | https://storage.googleapis.com/earthenginepartners-hansen/GFC-2025-v1.13/Hansen_GFC-2025-v1.13_datamask_40N_060E.tif | https://storage.googleapis.com/earthenginepartners-hansen/GFC-2025-v1.13/Hansen_GFC-2025-v1.13_datamask_40N_070E.tif |

- **Use:** forest mask, annual loss year (labels to validate the logging detector).

## 3. Global Reforestation Sites (LoDIA), Scientific Data 2025 ⚠️ (Pakistan coverage not yet confirmed)
- DOI: https://doi.org/10.7910/DVN/ZJODGO (Harvard Dataverse v3.0, **CC0**) · Code: https://github.com/Societal-Computing/Forest_Monitoring
- **Main file:** `updated_LoDIA_Reforestation_Dataset.parquet`, 1.23 GB, MD5 e0f0bcf2c33cc8af9bafce2f9af43d99
  → https://dataverse.harvard.edu/api/access/datafile/12556067 (the API reported `canDownloadFile: false`, so it may need a Dataverse login)
- Also ~3,900 RGB Sentinel-2 chips (`<site>_at_planting_<year>_RGB.tif`, `_1yr_after_`…), e.g. https://dataverse.harvard.edu/api/access/datafile/11988683
- Columns (from the paper): site_id_reported, project_id_reported, **iso3**, country, geometry_reported, **planting_date_reported**, site_sqkm, tree_cover_area_2000…2020, loss_post_5, mean_elevation, mean_slope, total_road_length_km, built_area
- **Pakistan check:** "Pakistan" does not appear in the paper text. The data comes from Restor/Verra-type registries. Needs `iso3 == "PAK"` checked on the parquet.

## 4. DISFOR: disturbance agents (logging / bark beetle / fire / drought) ✅
- DOI: https://doi.org/10.57967/hf/7983 → https://huggingface.co/datasets/JR-DIGITAL/DISFOR · License EUPL-1.2 · ESSD preprint doi:10.5194/essd-2026-185
- **Small files to start with** (no need for the 34 GB of chips):

| File | Size | Link |
|---|---|---|
| samples.parquet | 141 kB | https://huggingface.co/datasets/JR-DIGITAL/DISFOR/resolve/main/samples.parquet?download=true |
| labels.parquet | 116 kB | https://huggingface.co/datasets/JR-DIGITAL/DISFOR/resolve/main/labels.parquet?download=true |
| **pixel_data.parquet** | 65.1 MB | https://huggingface.co/datasets/JR-DIGITAL/DISFOR/resolve/main/pixel_data.parquet?download=true |
| classes.json | 758 B | https://huggingface.co/datasets/JR-DIGITAL/DISFOR/resolve/main/classes.json?download=true |
| train_ids.json / val_ids.json | 33 kB / 4 kB | …/resolve/main/train_ids.json , …/resolve/main/val_ids.json |

- pixel_data = per-pixel Sentinel-2 time series (B02–B12 + SCL). Image chips: `disfor-0-499.tar.zst` … `disfor-3500-3999.tar.zst` (2.4–5.7 GB each).
- **Classes:** 211 Clear cut, 212 Thinning, 221/222 Salvage, 231 Bark beetle, 232 Gypsy moth, 241 Drought, 242 Wildfire, 243 Wind, 244 Avalanche, 245 Flood, 110 Undisturbed, 121–123 Revegetation.
- **Use:** train the **cause classifier** (illegal logging vs disease vs fire) on Sentinel-2 time series, then apply it to KP pixels.

## 5. Ukraine forest change detection (HF) ✅
- https://huggingface.co/datasets/Moriae/ukraine-forest-change-detection · **CC BY-NC-SA 4.0** · 19,405 S2 before/after triplets, 256×256, 10 bands (B2,B3,B4,B8,B11,B12,NDVI,NBR,NDMI,NBR2), Hansen-derived masks

| File | Size | Link |
|---|---|---|
| metadata.csv | 7.2 MB | https://huggingface.co/datasets/Moriae/ukraine-forest-change-detection/resolve/main/metadata.csv?download=true |
| dataset_val.tar.zst | 11.5 GB | …/resolve/main/dataset_val.tar.zst?download=true |
| dataset_test.tar.zst | 14.9 GB | …/resolve/main/dataset_test.tar.zst?download=true |
| dataset_train.tar.zst | 64.7 GB | …/resolve/main/dataset_train.tar.zst?download=true |

- ⚠️ Too big for tonight. Use the val split only if we train a change-detection CNN.

## 6. UNet-Diff pretrained forest change model (Ukraine) ⚠️
- Repo: https://github.com/robmarkcole/forest_change_detection (fork of QuantuMobileSoftware)
- Weights (Google Drive): https://drive.google.com/file/d/1rbJf9lPLScT4h-X3e0CAsOqMqZfA6KNI/view?usp=sharing → `models/unet-diff.pth`
- Training data (Google Drive folder, S2 tiles 36UYA/36UXA + 2,318 polygons): https://drive.google.com/folder/1GJwDQ7SqASyPlusjbYWHLbrpNg_wAtuP
- Drive contents and license not verified.

## 7. Seedling survival tabular data ✅ (public domain; North American species, greenhouse/field experiment)
**Wood et al. 2023, PLoS ONE** (doi:10.1371/journal.pone.0293906). Dryad: https://doi.org/10.5061/dryad.xd2547dpw

| File | Size | Link |
|---|---|---|
| Data.csv | 390.7 KB | https://datadryad.org/downloads/file_stream/2692064 |
| README.md | 4.3 KB | https://datadryad.org/downloads/file_stream/2692080 |

Columns: Species, Light ISF/Cat, Soil, Sterile, Conspecific, Myco, AMF, EMF, Phenolics, NSC, Lignin, Time (days), **Event (1 = dead)**, Alive. 3,024 seedlings. This is the source of Kaggle's "Tree Survival Prediction"; the exact Kaggle URL was not found, so use Dryad, the original.

**Companion (Acer greenhouse):** https://doi.org/10.5061/dryad.7d7wm380b
- Acer_GH_Data.csv (174 KB): https://datadryad.org/downloads/file_stream/2674917
- README: https://datadryad.org/downloads/file_stream/2674915

## 8. Restoration tree survival, South & Southeast Asia (UKCEH) ✅ (no Pakistan)
- DOI https://doi.org/10.5285/935781e1-9119-4673-bd09-3fc76ae627d5 · OGL v3 · 176 sites, CSV + R
- Data zip: https://data-package.ceh.ac.uk/data/935781e1-9119-4673-bd09-3fc76ae627d5
- Supporting code: https://data-package.ceh.ac.uk/sd/935781e1-9119-4673-bd09-3fc76ae627d5.zip
- Extent starts at 87.5°E, so it **does not cover Pakistan**. Useful only for survival priors.

## 9. Validation sets (Europe) ✅
- **EFID** (Zenodo, CC BY 4.0): https://zenodo.org/records/17582705/files/EFID_Photoint_Dataset_20250910.zip?download=1 (2.0 MB) · https://zenodo.org/records/17582705/files/EFID_Samples_20250910.zip?download=1 (313 KB). Disturbance types: CC clear-cut, FF fire, PE pests, WT wind, TH thinning.
- **Italy S2 disturbance 2017–20** (Mendeley, CC BY 4.0): https://data.mendeley.com/datasets/5jyp57ymw4/1 (⚠️ file list not exposed; use "Download All" in a browser)

## 10. Not available ❌
- **Mehmood et al. 2025 (BTAP ML):** no data repository; only supplementary `ECE3-15-e70736-s001.docx` at https://pmc.ncbi.nlm.nih.gov/articles/instance/11839268/bin/ECE3-15-e70736-s001.docx
- **AI-ForestWatch (Pakistan, 15 districts):** promised release, no public repo found.
- **WRI SDPT v2.1:** https://datasets.wri.org/datasets/spatial-database-of-planted-trees-sdpt-version-21 has a ZIP, but the direct link and Pakistan coverage were not exposed. Open it in a browser.
- **GFW GLAD alerts:** tropics only (30°N–30°S), so they don't cover KP. Use DIST-ALERT via the GFW Data API.

## 11. Live / covariate layers (Earth Engine, no download)
`COPERNICUS/S2_SR_HARMONIZED`, `COPERNICUS/S2_CLOUD_PROBABILITY`, `COPERNICUS/S1_GRD`, `GOOGLE/DYNAMICWORLD/V1`, `FIRMS`, `ESA/WorldCover/v200`, `UCSB-CHG/CHIRPS/DAILY`, `ECMWF/ERA5_LAND/DAILY_AGGR`, `COPERNICUS/DEM/GLO30`, SoilGrids (`projects/soilgrids-isric/...`).

---

## What we actually download tonight (~600 MB total)
1. `lulc2010.tif` + `lulc2020.tif` (Pakistan LULC): forest mask + afforestation candidate sites. Or use the GEE asset.
2. DISFOR `pixel_data.parquet` + `labels.parquet` + `samples.parquet` + `classes.json`: cause classifier.
3. Wood et al. `Data.csv`: secondary tabular survival model.
4. Hansen: use via GEE (no download needed).
5. LoDIA parquet: only if it contains PAK rows. Check first by reading the `iso3` column remotely.
