import * as maplibregl from 'maplibre-gl'
import type { GeoJSONSource, Map as MlMap, MapLayerMouseEvent } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { useEffect, useRef } from 'react'
import type { AlertProps, DistrictProps, FC, Fire, Layers } from '../api'

export type LayerKey = 'satellite_recent' | 'forest_mask' | 'health' | 'suitability' | 'districts' | 'alerts' | 'fires'
export type Visibility = Record<LayerKey, boolean>

const RASTERS: { key: Exclude<LayerKey, 'districts' | 'alerts' | 'fires'>; opacity: number }[] = [
  { key: 'satellite_recent', opacity: 1 },
  { key: 'forest_mask', opacity: 0.45 },
  { key: 'suitability', opacity: 0.75 },
  { key: 'health', opacity: 0.85 },
]

// The worker is served untouched from /public (copied on npm install). Vite's dev server otherwise
// injects `/@vite/client` into the node_modules worker, which silently kills it (map never loads).
maplibregl.setWorkerUrl('/maplibre-gl-worker.mjs')

const LIVE_MINZOOM = 9
const OVERLAY_MAXZOOM = 11
const esc = (v: unknown) => String(v ?? '—').replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`)

function firePopupHtml(p: Record<string, unknown>): string {
  const k = Number(p.brightness_k)
  const temp = Number.isFinite(k) ? `${Math.round(k)} K (${Math.round(k - 273.15)} °C at the sensor)` : '—'
  const known = p.in_forest !== undefined && p.in_forest !== null
  const inForest = p.in_forest === true || p.in_forest === 'true'
  const verdict = !known
    ? '<div class="fp-note">Land type not checked yet.</div>'
    : inForest
      ? `<div class="fp-tag fp-forest">🔥 Forest fire — ${esc(p.forest_pct)}% of this ~1 km pixel is forest</div>`
      : `<div class="fp-tag fp-farm">Not in forest — ${esc(p.land_class)} land (${esc(p.forest_pct)}% forest). Likely crop-residue burning or a kiln.</div>`
  return `
    <div class="fp">
      <div class="fp-title">Active fire hotspot</div>
      ${verdict}
      <table>
        <tr><td>Detected</td><td>${esc(p.date)}</td></tr>
        <tr><td>Brightness</td><td>${esc(temp)}</td></tr>
        <tr><td>Confidence</td><td>${esc(p.confidence)}${typeof p.confidence === 'number' ? '%' : ''}</td></tr>
        <tr><td>Location</td><td>${Number(p.lat).toFixed(4)}, ${Number(p.lon).toFixed(4)}</td></tr>
        <tr><td>Source</td><td>${esc(p.source)}</td></tr>
      </table>
    </div>`
}

const KP_BOUNDS: [number, number, number, number] = [69.2, 31.0, 74.2, 37.1]
const EMPTY: GeoJSON.FeatureCollection = { type: 'FeatureCollection', features: [] }

export type Overlays = Record<string, { url: string; coordinates: [number, number][] }>

type Props = {
  layers: Layers | null
  overlays: Overlays
  visible: Visibility
  districts: FC<DistrictProps> | null
  alerts: FC<AlertProps> | null
  fires: Fire[]
  selectedAlert: string | null
  flyTo: { lon: number; lat: number; zoom?: number; key: number } | null
  onSelectAlert: (id: string) => void
  onSelectDistrict: (name: string) => void
}

export function MapView(p: Props) {
  const box = useRef<HTMLDivElement>(null)
  const map = useRef<MlMap | null>(null)
  const ready = useRef(false)
  const cb = useRef(p)
  cb.current = p

  useEffect(() => {
    if (!box.current) return
    const m = new maplibregl.Map({
      container: box.current,
      bounds: KP_BOUNDS,
      fitBoundsOptions: { padding: 20 },
      style: {
        version: 8,
        glyphs: 'https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf',
        sources: {
          esri: {
            type: 'raster',
            tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'],
            tileSize: 256,
            attribution: 'Imagery © Esri, Maxar, Earthstar Geographics',
          },
        },
        layers: [{ id: 'esri', type: 'raster', source: 'esri', paint: { 'raster-saturation': -0.35, 'raster-brightness-max': 0.8 } }],
      },
    })
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'bottom-right')
    m.addControl(new maplibregl.ScaleControl({ unit: 'metric' }), 'bottom-left')
    m.on('load', () => {
      m.addSource('districts', { type: 'geojson', data: EMPTY })
      m.addLayer({
        id: 'districts-fill',
        type: 'fill',
        source: 'districts',
        paint: {
          'fill-color': ['interpolate', ['linear'], ['coalesce', ['get', 'alerts'], 0], 0, '#0f3d2e', 20, '#c9a227', 80, '#b23a2b'],
          'fill-opacity': 0.25,
        },
      })
      m.addLayer({ id: 'districts-line', type: 'line', source: 'districts', paint: { 'line-color': '#e6efe9', 'line-width': 0.8, 'line-opacity': 0.7 } })
      m.addSource('alerts', { type: 'geojson', data: EMPTY })
      m.addLayer({
        id: 'alerts-fill',
        type: 'fill',
        source: 'alerts',
        paint: { 'fill-color': ['match', ['get', 'type'], 'logging', '#ff3b30', '#ff9f0a'], 'fill-opacity': 0.55 },
      })
      m.addLayer({ id: 'alerts-line', type: 'line', source: 'alerts', paint: { 'line-color': '#fff', 'line-width': 1 } })
      m.addSource('alert-points', { type: 'geojson', data: EMPTY })
      m.addLayer({
        id: 'alerts-pts',
        type: 'circle',
        source: 'alert-points',
        maxzoom: 12,
        paint: {
          'circle-radius': ['interpolate', ['linear'], ['get', 'priority'], 0, 3, 60, 8],
          'circle-color': ['match', ['get', 'type'], 'logging', '#ff3b30', '#ff9f0a'],
          'circle-stroke-color': '#fff',
          'circle-stroke-width': ['case', ['==', ['get', 'id'], ''], 3, 1],
        },
      })
      m.addSource('fires', { type: 'geojson', data: EMPTY })
      m.addLayer({
        id: 'fires',
        type: 'circle',
        source: 'fires',
        paint: {
          'circle-radius': ['case', ['==', ['get', 'in_forest'], true], 8, 6],
          'circle-color': ['case', ['==', ['get', 'in_forest'], true], '#ff5e00', '#ffd60a'],
          'circle-stroke-color': '#7a2e00',
          'circle-stroke-width': 2,
        },
      })
      m.on('click', 'fires', (e: MapLayerMouseEvent) => {
        const f = e.features?.[0]
        if (!f) return
        const p = f.properties as Record<string, unknown>
        const coords = (f.geometry as GeoJSON.Point).coordinates as [number, number]
        new maplibregl.Popup({ closeButton: true, maxWidth: '260px', className: 'fire-popup' })
          .setLngLat(coords)
          .setHTML(firePopupHtml(p))
          .addTo(m)
      })
      m.on('mouseenter', 'fires', () => (m.getCanvas().style.cursor = 'pointer'))
      m.on('mouseleave', 'fires', () => (m.getCanvas().style.cursor = ''))
      for (const id of ['alerts-fill', 'alerts-pts']) {
        m.on('click', id, (e: MapLayerMouseEvent) => {
          const f = e.features?.[0]
          if (f) cb.current.onSelectAlert(String(f.properties.id))
        })
        m.on('mouseenter', id, () => (m.getCanvas().style.cursor = 'pointer'))
        m.on('mouseleave', id, () => (m.getCanvas().style.cursor = ''))
      }
      m.on('click', 'districts-fill', (e: MapLayerMouseEvent) => {
        const hit = m.queryRenderedFeatures(e.point, { layers: ['alerts-fill', 'alerts-pts', 'fires'] })
        if (!hit.length && e.features?.[0]) cb.current.onSelectDistrict(String(e.features[0].properties.district))
      })
      ready.current = true
      sync()
    })
    map.current = m
    if (import.meta.env.DEV) (window as unknown as { __map: MlMap }).__map = m
    return () => m.remove()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function sync() {
    const m = map.current
    if (!m || !ready.current) return
    const { layers, overlays, visible, districts, alerts, fires, selectedAlert } = cb.current
    for (const r of RASTERS) {
      // snapshot overlay underneath: shows instantly and survives an Earth Engine outage
      const ov = overlays[r.key]
      const osrc = `ov-${r.key}`
      if (ov && !m.getSource(osrc)) {
        m.addSource(osrc, { type: 'image', url: ov.url, coordinates: ov.coordinates as [[number, number], [number, number], [number, number], [number, number]] })
        // overlay is zoom-8 detail: hide it at street zoom where it would show as misleading blocks
        m.addLayer(
          { id: osrc, type: 'raster', source: osrc, maxzoom: OVERLAY_MAXZOOM, paint: { 'raster-opacity': r.opacity, 'raster-resampling': 'nearest' } },
          'districts-fill',
        )
      }
      if (m.getLayer(osrc)) m.setLayoutProperty(osrc, 'visibility', visible[r.key] ? 'visible' : 'none')
      const src = `ee-${r.key}`
      // Tiles go through the backend proxy (disk cache + throttling + retry) instead of straight to
      // Earth Engine, which rate-limits (HTTP 429) bursts of browser requests.
      const url = layers?.[r.key]?.url ? `${window.location.origin}/api/forest/tiles/${r.key}/{z}/{x}/{y}.png` : null
      if (url && !m.getSource(src)) {
        // Live tiles only from district zoom up; the snapshot overlay covers wider views.
        const minzoom = ov && r.key !== 'satellite_recent' ? LIVE_MINZOOM : 0
        m.addSource(src, { type: 'raster', tiles: [url], tileSize: 256, minzoom, attribution: 'Google Earth Engine' })
        m.addLayer({ id: src, type: 'raster', source: src, minzoom, paint: { 'raster-opacity': r.opacity } }, 'districts-fill')
      }
      if (m.getLayer(src)) m.setLayoutProperty(src, 'visibility', visible[r.key] ? 'visible' : 'none')
    }
    ;(m.getSource('districts') as GeoJSONSource).setData((districts as unknown as GeoJSON.FeatureCollection) ?? EMPTY)
    ;(m.getSource('alerts') as GeoJSONSource).setData((alerts as unknown as GeoJSON.FeatureCollection) ?? EMPTY)
    ;(m.getSource('alert-points') as GeoJSONSource).setData({
      type: 'FeatureCollection',
      features: (alerts?.features ?? []).map((f) => ({
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [f.properties.lon, f.properties.lat] },
        properties: { id: f.properties.id, type: f.properties.type, priority: f.properties.priority },
      })),
    })
    ;(m.getSource('fires') as GeoJSONSource).setData({
      type: 'FeatureCollection',
      features: fires.map((f) => ({ type: 'Feature', geometry: { type: 'Point', coordinates: [f.lon, f.lat] }, properties: { ...f } })),
    })
    for (const [id, key] of [
      ['districts-fill', 'districts'],
      ['districts-line', 'districts'],
      ['alerts-fill', 'alerts'],
      ['alerts-line', 'alerts'],
      ['alerts-pts', 'alerts'],
      ['fires', 'fires'],
    ] as const) {
      m.setLayoutProperty(id, 'visibility', visible[key] ? 'visible' : 'none')
    }
    m.setPaintProperty('alerts-pts', 'circle-stroke-width', ['case', ['==', ['get', 'id'], selectedAlert ?? ''], 3, 1])
  }

  useEffect(sync, [p.layers, p.overlays, p.visible, p.districts, p.alerts, p.fires, p.selectedAlert])

  useEffect(() => {
    if (p.flyTo && map.current) map.current.flyTo({ center: [p.flyTo.lon, p.flyTo.lat], zoom: p.flyTo.zoom ?? 14, speed: 1.6 })
  }, [p.flyTo])

  // maplibre-gl.css sets `.maplibregl-map { position: relative }` (unlayered CSS beats Tailwind's layered
  // utilities), so positioning lives on a wrapper and the map div just fills it.
  return (
    <div className="absolute inset-0">
      <div ref={box} style={{ width: '100%', height: '100%' }} />
    </div>
  )
}
