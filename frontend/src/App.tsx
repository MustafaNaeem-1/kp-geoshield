import { useEffect, useState } from 'react'
import { api, type AlertProps, type DistrictProps, type FC, type Fire, type Layers, type Summary } from './api'
import { ForestPanel } from './components/ForestPanel'
import { LayerPanel } from './components/LayerPanel'
import { MapView, type Overlays, type Visibility } from './components/MapView'
import { ModuleNav } from './components/ModuleNav'

const DEFAULT_VIS: Visibility = {
  satellite_recent: false,
  forest_mask: false,
  health: true,
  suitability: false,
  districts: true,
  alerts: true,
  fires: true,
}

export default function App() {
  const [layers, setLayers] = useState<Layers | null>(null)
  const [layersErr, setLayersErr] = useState<string | null>(null)
  const [overlays, setOverlays] = useState<Overlays>({})
  const [summary, setSummary] = useState<Summary | null>(null)
  const [districts, setDistricts] = useState<FC<DistrictProps> | null>(null)
  const [alerts, setAlerts] = useState<FC<AlertProps> | null>(null)
  const [fires, setFires] = useState<Fire[]>([])
  const [visible, setVisible] = useState<Visibility>(DEFAULT_VIS)
  const [selAlert, setSelAlert] = useState<string | null>(null)
  const [selDistrict, setSelDistrict] = useState<string | null>(null)
  const [flyTo, setFlyTo] = useState<{ lon: number; lat: number; zoom?: number; key: number } | null>(null)
  const [panelOpen, setPanelOpen] = useState(true)
  const [showLayers, setShowLayers] = useState(() => window.innerWidth >= 768)
  const [status, setStatus] = useState<{ ee: boolean; offline: boolean } | null>(null)
  const [errors, setErrors] = useState<string[]>([])

  useEffect(() => {
    const note = (e: unknown) => setErrors((x) => [...x, String(e).slice(0, 160)])
    api.health().then((h) => setStatus({ ee: h.earth_engine.ready, offline: h.offline })).catch(note)
    api.alerts().then(setAlerts).catch(note)
    api.summary().then(setSummary).catch(note)
    api.districts().then(setDistricts).catch(note)
    api.fires(7).then((f) => setFires(f.fires)).catch(note)
    api.overlays().then((o) => setOverlays(o.layers)).catch(note)
    api.layers().then(setLayers).catch((e) => setLayersErr(String(e)))
  }, [])

  const selectAlert = (id: string | null) => {
    setSelAlert(id)
    if (!id) return
    const f = alerts?.features.find((x) => x.properties.id === id)
    if (f) setFlyTo({ lon: f.properties.lon, lat: f.properties.lat, zoom: 14.5, key: Date.now() })
    setPanelOpen(true)
  }
  const selectDistrict = (d: string) => {
    setSelDistrict(d)
    setPanelOpen(true)
  }

  return (
    <div className="flex h-full flex-col md:flex-row">
      <ModuleNav />
      <div className="relative flex-1 overflow-hidden">
        <header className="absolute left-3 right-3 top-3 z-10 flex items-center gap-3 md:right-auto">
          <div className="rounded-xl border border-[#1f2d27] bg-[#0f1714]/90 px-3 py-2 shadow-xl backdrop-blur">
            <div className="text-sm font-semibold">KP GeoShield · Forests</div>
            <div className="text-[10px] text-slate-400">
              Khyber Pakhtunkhwa forest & plantation monitoring ·{' '}
              {status ? (
                status.offline ? (
                  <span className="text-amber-300">offline snapshot mode</span>
                ) : status.ee ? (
                  <span className="text-emerald-400">● live satellite data</span>
                ) : (
                  <span className="text-slate-300">connecting…</span>
                )
              ) : (
                '…'
              )}
            </div>
          </div>
          <button
            onClick={() => setShowLayers((v) => !v)}
            className="shrink-0 rounded-lg border border-[#1f2d27] bg-[#0f1714]/90 px-2 py-1 text-xs"
          >
            {showLayers ? 'Hide layers' : 'Layers'}
          </button>
          <button
            onClick={() => setPanelOpen((v) => !v)}
            className="shrink-0 rounded-lg border border-[#1f2d27] bg-[#0f1714]/90 px-2 py-1 text-xs md:hidden"
          >
            {panelOpen ? 'Map' : 'Panel'}
          </button>
        </header>
        {showLayers && (
          <div className="absolute left-3 top-20 z-10 max-h-[calc(100%-6rem)] overflow-auto">
            <LayerPanel visible={visible} setVisible={setVisible} layers={layers} layersError={layersErr} />
          </div>
        )}
        <MapView
          layers={layers}
          overlays={overlays}
          visible={visible}
          districts={districts}
          alerts={alerts}
          fires={fires}
          selectedAlert={selAlert}
          flyTo={flyTo}
          onSelectAlert={selectAlert}
          onSelectDistrict={selectDistrict}
        />
        {errors.length > 0 && (
          <div className="absolute bottom-10 left-3 z-10 max-w-md rounded-lg bg-red-950/90 p-2 text-[10px] text-red-200">
            {errors.map((e, i) => (
              <div key={i}>{e}</div>
            ))}
          </div>
        )}
      </div>
      {panelOpen && (
        <aside className="absolute inset-x-0 bottom-0 z-10 h-[55%] border-t border-[#1f2d27] bg-[#0f1714] md:static md:h-auto md:w-[380px] md:border-l md:border-t-0">
          <ForestPanel
            summary={summary}
            districts={districts}
            alerts={alerts}
            selectedAlert={selAlert}
            selectedDistrict={selDistrict}
            onSelectAlert={selectAlert}
            onSelectDistrict={selectDistrict}
          />
        </aside>
      )}
    </div>
  )
}
