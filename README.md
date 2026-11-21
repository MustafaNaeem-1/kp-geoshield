# KP GeoShield: Forest module

A live forest and plantation monitor for Khyber Pakhtunkhwa: canopy health, logging and encroachment alerts with an AI cause model, fires, and planting suitability.

## First-time setup on a new laptop
You need Python 3.12+ and Node 20+.

```powershell
git clone https://github.com/MustafaNaeem-1/kp-geoshield.git
cd kp-geoshield\backend
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
copy .env.example .env
cd ..\frontend
npm install
```

- **Without Earth Engine access:** set `OFFLINE=1` in `backend\.env`. The app then runs fully from the snapshots included in the repo (alerts, statistics, map overlays, models).
- **For live satellite data:**
  1. The project owner adds your Google account to the `kp-geoshield` Cloud project.
  2. Set `EE_PROJECT=kp-geoshield` and `OFFLINE=0` in `backend\.env`.
  3. Sign in once:
     ```powershell
     .\.venv\Scripts\python -c "import ee; ee.Authenticate()"
     ```

## Run (Windows)
```powershell
# backend (http://localhost:8000)
cd backend
.\.venv\Scripts\python -m uvicorn app.main:app --port 8000

# frontend (http://localhost:5173), in a second terminal
cd frontend
npm run dev
```
- `backend/.env` holds `EE_PROJECT=kp-geoshield`.
- Earth Engine credentials come from `ee.Authenticate()`, which has already been done on this PC.
- **Demo safety switch:** set `OFFLINE=1` in `backend/.env` and restart the backend. The app then serves the last saved snapshots and overlays, with no internet or Earth Engine needed.

## Refresh data (before the demo)
```powershell
cd backend
.\.venv\Scripts\python scripts\precompute_alerts.py      # alerts for 31 districts (~15 min)
.\.venv\Scripts\python scripts\make_overlays.py          # offline map overlays
.\.venv\Scripts\python scripts\warm_tiles.py             # pre-fetch live map tiles over KP (~20 min)
.\.venv\Scripts\python -m pytest tests -q                # tests
```
Open the app once while online so every panel's snapshot is saved for offline mode.

## Data and models (all verified; see docs/forest_datasets.md)
- **Sentinel-2 L2A** (harmonized) + Cloud Score+, **Sentinel-1**, **Dynamic World**, **NASA FIRMS**: live, via Earth Engine
- **Pakistan LULC 1990–2020** (Waleed et al. 2024), **Hansen GFC v1.13**, **ESA WorldCover**: forest mask and validation
- **Cause model:** XGBoost trained on **DISFOR** (European Sentinel-2 disturbance labels)
  - grouped-CV macro-F1 0.71
  - per-class F1: fire 0.93, logging 0.74, disease/drought 0.50
- **Establishment / suitability model:** labels derived from PK-LULC 2010→2020 change plus 2024 NDVI. It is a proxy, not field survival data.
- **Drought stress:** Open-Meteo 16-day forecast (no key)

The approved plan and every change to it are logged in `~/.claude/plans/sharded-sprouting-brooks.md`.
