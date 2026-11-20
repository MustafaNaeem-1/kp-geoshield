import type { Layers } from '../api'
import type { LayerKey, Visibility } from './MapView'

const ITEMS: { key: LayerKey; label: string; legend?: [string, string][] }[] = [
  { key: 'alerts', label: 'Logging & encroachment alerts', legend: [['#ff3b30', 'Logging'], ['#ff9f0a', 'Encroachment']] },
  { key: 'fires', label: 'Active fires (7 days)', legend: [['#ffd60a', 'Fire hotspot']] },
  { key: 'health', label: 'Canopy health (live)', legend: [['#2e7d32', 'Healthy'], ['#f9a825', 'Stressed'], ['#c62828', 'Severe decline']] },
  { key: 'suitability', label: 'Planting suitability', legend: [['#d73027', 'Low'], ['#fee08b', 'Medium'], ['#1a9850', 'High']] },
  { key: 'forest_mask', label: 'Forest extent', legend: [['#1b5e20', 'Forest']] },
  { key: 'districts', label: 'Districts (shaded by alerts)' },
  { key: 'satellite_recent', label: 'Latest Sentinel-2 (60 days)' },
]

export function LayerPanel({ visible, setVisible, layers, layersError }: {
  visible: Visibility
  setVisible: (v: Visibility) => void
  layers: Layers | null
  layersError: string | null
}) {
  const needsEE: LayerKey[] = ['health', 'suitability', 'forest_mask', 'satellite_recent']
  return (
    <div className="w-64 rounded-xl border border-[#1f2d27] bg-[#0f1714]/90 p-3 text-xs shadow-xl backdrop-blur">
      <div className="mb-2 font-semibold uppercase tracking-wide text-emerald-300">Layers</div>
      <ul className="space-y-2">
        {ITEMS.map((it) => {
          const pending = needsEE.includes(it.key) && !layers
          return (
            <li key={it.key}>
              <label className={`flex cursor-pointer items-center gap-2 ${pending ? 'opacity-60' : ''}`}>
                <input
                  type="checkbox"
                  className="accent-emerald-500"
                  checked={visible[it.key]}
                  onChange={(e) => setVisible({ ...visible, [it.key]: e.target.checked })}
                />
                <span>{it.label}</span>
                {pending && !layersError && <span className="ml-auto animate-pulse text-[10px] text-slate-400">loading</span>}
              </label>
              {visible[it.key] && it.legend && (
                <div className="ml-6 mt-1 flex flex-wrap gap-x-3 gap-y-1">
                  {it.legend.map(([c, l]) => (
                    <span key={l} className="flex items-center gap-1 text-[10px] text-slate-300">
                      <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: c }} />
                      {l}
                    </span>
                  ))}
                </div>
              )}
            </li>
          )
        })}
      </ul>
      {layersError && <p className="mt-2 text-[10px] text-amber-400">Satellite layers unavailable: {layersError.slice(0, 120)}</p>}
      {layers?.health && (
        <p className="mt-2 text-[10px] leading-snug text-slate-400">
          Health compares {layers.health.recent_window.join(' → ')} with the same weeks of the 3 previous years. Tiles are computed live by
          Earth Engine and can take ~10 s.
        </p>
      )}
    </div>
  )
}
