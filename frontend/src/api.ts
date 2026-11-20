export type TileLayer = { url: string; palette?: string[]; legend?: Record<string, string>; [k: string]: unknown }

export type Layers = {
  health: TileLayer & { recent_window: string[]; baseline_windows: string[][] }
  forest_mask: TileLayer
  suitability: TileLayer & { applies_to: string }
  satellite_recent: TileLayer & { window: string[] }
  _cached_at?: string
  _stale?: boolean
}

export type Attribution = {
  cause: string
  confidence: number | null
  probabilities?: Record<string, number>
  event_date?: string
  fire_override?: boolean
  model_note?: string
  note?: string
  error?: string
}

export type AlertProps = {
  id: string
  district: string
  type: 'logging' | 'encroachment'
  area_ha: number
  lon: number
  lat: number
  dndvi: number | null
  dnbr: number | null
  s1_vh_change_db: number | null
  in_protected_area: boolean
  road_dist_m: number | null
  priority: number
  confidence?: 'high' | 'standard'
  recent_window: string[]
  prior_window: string[]
  attribution?: Attribution
  images?: { before?: string; after?: string; error?: string }
}

export type Feature<P> = { type: 'Feature'; geometry: GeoJSON.Geometry; properties: P }
export type FC<P> = { type: 'FeatureCollection'; features: Feature<P>[]; total?: number; _stale?: boolean; _cached_at?: string }

export type DistrictProps = {
  district: string
  district_km2?: number
  lulc_forest_km2_2020?: number
  mask_forest_km2?: number
  pct_healthy?: number
  pct_stressed?: number
  pct_severe?: number
  alerts: number
  alert_area_ha: number
  fires_7d: number
}

export type Summary = {
  province: string
  districts: number
  area_km2: number
  forest_km2_mask: number
  forest_km2_pk_lulc_2020: number
  pct_stressed: number
  pct_severe: number
  alerts: number
  alert_area_ha: number
  alerts_generated?: string
  hansen_validation?: {
    precision_all: number
    precision_high: number
    alerts_all: number
    alerts_high: number
    hansen_hits_kept_by_high: string
    districts: string[]
    caveat: string
  } | null
  _cached_at?: string
  _stale?: boolean
}

export type Fire = { lon: number; lat: number; date: string; brightness_k: number; confidence: number | string; source: string }

export type Explain = {
  survival?: {
    label_definition: string
    n_samples: number
    cv: { auc: number; scheme: string }
    shap_importance: { feature: string; label: string; mean_abs_shap: number }[]
  }
  attribution?: {
    n_events: number
    cv: { macro_f1: number; scheme: string; per_class: Record<string, { precision: number; recall: number; 'f1-score': number }> }
  }
  shap_chart?: string | null
}

export type Drought = {
  districts: {
    district: string
    rain_mm: number
    et0_mm: number
    water_deficit_mm: number
    hot_days_ge35c: number
    stress: 'high' | 'moderate' | 'low'
    forecast_from: string
    forecast_to: string
  }[]
  _cached_at?: string
}

async function get<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, init)
  if (!r.ok) throw new Error(`${path}: ${r.status} ${await r.text()}`)
  return r.json() as Promise<T>
}

export const api = {
  health: () => get<{ status: string; offline: boolean; earth_engine: { ready: boolean; error: string | null } }>('/api/health'),
  layers: () => get<Layers>('/api/forest/layers'),
  summary: () => get<Summary>('/api/forest/summary'),
  districts: () => get<FC<DistrictProps>>('/api/forest/districts'),
  district: (n: string) =>
    get<{ district: string; hansen_loss_km2_by_year: Record<string, number> }>(`/api/forest/districts/${encodeURIComponent(n)}`),
  alerts: () => get<FC<AlertProps>>('/api/forest/alerts'),
  alert: (id: string) => get<Feature<AlertProps>>(`/api/forest/alerts/${encodeURIComponent(id)}`),
  refresh: (d: string) => get<Record<string, unknown>>(`/api/forest/alerts/refresh?district=${encodeURIComponent(d)}`, { method: 'POST' }),
  fires: (days = 7) => get<{ days: number; fires: Fire[] }>(`/api/forest/fires?days=${days}`),
  overlays: () =>
    get<{ generated?: string; layers: Record<string, { url: string; coordinates: [number, number][] }> }>('/api/forest/overlays'),
  explain: () => get<Explain>('/api/forest/survival/explain'),
  drought: () => get<Drought>('/api/forest/survival/drought-stress'),
}

export const CAUSE_LABEL: Record<string, string> = {
  logging: 'Logging / clearing',
  disease_drought: 'Disease, pests or drought',
  fire: 'Fire',
  other_natural: 'Storm / flood damage',
  undisturbed: 'No disturbance signal',
  unknown: 'Undetermined',
}
