import { useEffect, useMemo, useState } from 'react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, CAUSE_LABEL, type AlertProps, type DistrictProps, type Drought, type Explain, type FC, type Summary } from '../api'
import { AlertDetail } from './AlertDetail'

type Tab = 'overview' | 'alerts' | 'plantations'

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-lg border border-[#1f2d27] bg-[#121c18] p-2">
      <div className="text-[10px] uppercase tracking-wide text-slate-400">{label}</div>
      <div className="text-lg font-semibold">{value}</div>
      {sub && <div className="text-[10px] text-slate-400">{sub}</div>}
    </div>
  )
}

function Overview({ summary, districts, selected, onPick }: {
  summary: Summary | null
  districts: FC<DistrictProps> | null
  selected: string | null
  onPick: (d: string) => void
}) {
  const [loss, setLoss] = useState<{ year: string; km2: number }[] | null>(null)
  useEffect(() => {
    if (!selected) return
    setLoss(null)
    api
      .district(selected)
      .then((d) => setLoss(Object.entries(d.hansen_loss_km2_by_year).map(([year, km2]) => ({ year, km2 }))))
      .catch(() => setLoss([]))
  }, [selected])
  const rows = useMemo(
    () => [...(districts?.features ?? [])].map((f) => f.properties).sort((a, b) => (b.alerts ?? 0) - (a.alerts ?? 0)),
    [districts],
  )
  const sel = rows.find((r) => r.district === selected)
  return (
    <div className="space-y-3">
      {!summary && <p className="animate-pulse text-xs text-slate-400">Loading province statistics…</p>}
      {summary && (
        <div className="grid grid-cols-2 gap-2">
          <Stat label="Forest extent" value={`${summary.forest_km2_mask.toLocaleString()} km²`} sub={`${((100 * summary.forest_km2_mask) / summary.area_km2).toFixed(1)}% of KP`} />
          <Stat label="Canopy under stress" value={`${(summary.pct_stressed + summary.pct_severe).toFixed(1)}%`} sub={`${summary.pct_severe}% severe`} />
          <Stat label="Active alerts" value={summary.alerts.toLocaleString()} sub={`${summary.alert_area_ha.toLocaleString()} ha`} />
          <Stat
            label="Agreement with Hansen 2024"
            value={summary.hansen_validation ? `${Math.round(summary.hansen_validation.precision_high * 100)}% high-conf.` : '—'}
            sub={
              summary.hansen_validation
                ? `${Math.round(summary.hansen_validation.precision_all * 100)}% for all alerts · 5 forest districts`
                : 'validation pending'
            }
          />
        </div>
      )}
      {sel && (
        <div className="rounded-lg border border-emerald-800 p-2">
          <div className="mb-1 flex items-baseline justify-between">
            <span className="text-sm font-semibold">{sel.district}</span>
            <span className="text-[10px] text-slate-400">{sel.mask_forest_km2?.toLocaleString()} km² forest</span>
          </div>
          <div className="mb-2 grid grid-cols-3 gap-1 text-center text-[10px]">
            <div>
              <div className="text-base font-semibold text-red-400">{sel.alerts}</div>alerts
            </div>
            <div>
              <div className="text-base font-semibold text-amber-300">{((sel.pct_stressed ?? 0) + (sel.pct_severe ?? 0)).toFixed(1)}%</div>stressed
            </div>
            <div>
              <div className="text-base font-semibold text-yellow-300">{sel.fires_7d}</div>fires (7d)
            </div>
          </div>
          <div className="text-[10px] text-slate-400">Tree-cover loss per year (Hansen GFC, km²)</div>
          <div className="h-32">
            {loss === null ? (
              <p className="animate-pulse text-[10px] text-slate-500">loading…</p>
            ) : (
              <ResponsiveContainer>
                <BarChart data={loss} margin={{ top: 4, right: 4, left: -24, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="2 4" stroke="#1f2d27" />
                  <XAxis dataKey="year" tick={{ fontSize: 9, fill: '#94a3b8' }} interval={3} />
                  <YAxis tick={{ fontSize: 9, fill: '#94a3b8' }} />
                  <Tooltip contentStyle={{ background: '#0f1714', border: '1px solid #1f2d27', fontSize: 11 }} />
                  <Bar dataKey="km2" fill="#e05d44" />
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>
      )}
      <div>
        <div className="mb-1 text-[10px] uppercase tracking-wide text-slate-400">Districts — click to inspect</div>
        <div className="max-h-72 overflow-auto rounded-lg border border-[#1f2d27]">
          <table className="w-full text-[11px]">
            <thead className="sticky top-0 bg-[#121c18] text-slate-400">
              <tr>
                <th className="p-1 text-left">District</th>
                <th className="p-1 text-right">Forest km²</th>
                <th className="p-1 text-right">Stress %</th>
                <th className="p-1 text-right">Alerts</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr
                  key={r.district}
                  onClick={() => onPick(r.district)}
                  className={`cursor-pointer border-t border-[#1f2d27] hover:bg-emerald-950 ${r.district === selected ? 'bg-emerald-950' : ''}`}
                >
                  <td className="p-1">{r.district}</td>
                  <td className="p-1 text-right">{Math.round(r.mask_forest_km2 ?? 0).toLocaleString()}</td>
                  <td className="p-1 text-right">{((r.pct_stressed ?? 0) + (r.pct_severe ?? 0)).toFixed(1)}</td>
                  <td className="p-1 text-right">{r.alerts}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

function Alerts({ alerts, onSelect, district }: { alerts: FC<AlertProps> | null; onSelect: (id: string) => void; district: string | null }) {
  const [type, setType] = useState<'all' | 'logging' | 'encroachment'>('all')
  const [onlyDistrict, setOnlyDistrict] = useState(true)
  const [onlyHigh, setOnlyHigh] = useState(false)
  const list = (alerts?.features ?? [])
    .map((f) => f.properties)
    .filter(
      (p) =>
        (type === 'all' || p.type === type) &&
        (!onlyDistrict || !district || p.district === district) &&
        (!onlyHigh || p.confidence === 'high'),
    )
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-1 text-[11px]">
        {(['all', 'logging', 'encroachment'] as const).map((t) => (
          <button key={t} onClick={() => setType(t)} className={`rounded px-2 py-1 ${type === t ? 'bg-emerald-700' : 'bg-[#1f2d27]'}`}>
            {t}
          </button>
        ))}
        <label className="flex items-center gap-1">
          <input type="checkbox" className="accent-emerald-500" checked={onlyHigh} onChange={(e) => setOnlyHigh(e.target.checked)} />
          high confidence
        </label>
        {district && (
          <label className="ml-auto flex items-center gap-1">
            <input type="checkbox" className="accent-emerald-500" checked={onlyDistrict} onChange={(e) => setOnlyDistrict(e.target.checked)} />
            {district} only
          </label>
        )}
      </div>
      <p className="text-[10px] text-slate-400">
        {list.length} alerts. High-confidence first (strong greenness + burn-index drop), then by priority (size, protected area, road
        access). Recent 60 days vs same window last year.
      </p>
      <ul className="max-h-[60vh] space-y-1 overflow-auto">
        {list.slice(0, 300).map((p) => (
          <li key={p.id}>
            <button onClick={() => onSelect(p.id)} className="w-full rounded-lg border border-[#1f2d27] p-2 text-left hover:border-emerald-700">
              <div className="flex items-center gap-2 text-[11px]">
                <span className={`h-2 w-2 rounded-full ${p.type === 'logging' ? 'bg-red-500' : 'bg-amber-500'}`} />
                <span className="font-semibold">{p.district}</span>
                <span className="text-slate-400">{p.area_ha} ha</span>
                {p.confidence === 'high' && <span className="rounded bg-red-900 px-1 text-[9px]">high conf.</span>}
                {p.in_protected_area && <span className="rounded bg-sky-900 px-1 text-[9px]">protected</span>}
                <span className="ml-auto text-slate-400">P{Math.round(p.priority)}</span>
              </div>
              {p.attribution && (
                <div className="mt-0.5 text-[10px] text-slate-400">
                  AI: {CAUSE_LABEL[p.attribution.cause] ?? p.attribution.cause}
                  {p.attribution.confidence != null && ` (${Math.round(p.attribution.confidence * 100)}%)`}
                </div>
              )}
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}

function Plantations() {
  const [ex, setEx] = useState<Explain | null>(null)
  const [dr, setDr] = useState<Drought | null>(null)
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => {
    api.explain().then(setEx).catch((e) => setErr(String(e)))
    api.drought().then(setDr).catch((e) => setErr(String(e)))
  }, [])
  const color = { high: 'text-red-400', moderate: 'text-amber-300', low: 'text-emerald-400' }
  return (
    <div className="space-y-3">
      {err && <p className="text-xs text-amber-400">{err.slice(0, 200)}</p>}
      <div>
        <div className="text-[10px] uppercase tracking-wide text-slate-400">Young plantations — water stress next 16 days</div>
        {!dr && <p className="animate-pulse text-[10px] text-slate-500">loading live forecast…</p>}
        {dr && (
          <ul className="mt-1 max-h-48 space-y-0.5 overflow-auto text-[11px]">
            {dr.districts.map((d) => (
              <li key={d.district} className="flex gap-2">
                <span className={`w-16 font-semibold uppercase ${color[d.stress]}`}>{d.stress}</span>
                <span className="flex-1">{d.district}</span>
                <span className="text-slate-400">
                  {d.rain_mm} mm rain · deficit {d.water_deficit_mm} mm
                </span>
              </li>
            ))}
          </ul>
        )}
        {dr && <p className="mt-1 text-[10px] text-slate-500">Open-Meteo forecast {dr.districts[0]?.forecast_from} → {dr.districts[0]?.forecast_to}; deficit = evapotranspiration − rain.</p>}
      </div>
      {ex?.survival && (
        <div className="rounded-lg border border-[#1f2d27] p-2">
          <div className="text-[10px] uppercase tracking-wide text-slate-400">Where do new trees take hold? (AI)</div>
          <p className="text-[11px]">
            Spatially cross-validated AUC <b>{ex.survival.cv.auc.toFixed(2)}</b> on {ex.survival.n_samples.toLocaleString()} KP sample points.
          </p>
          <div className="h-48">
            <ResponsiveContainer>
              <BarChart data={ex.survival.shap_importance.slice(0, 8)} layout="vertical" margin={{ top: 4, right: 8, left: 40, bottom: 0 }}>
                <XAxis type="number" tick={{ fontSize: 9, fill: '#94a3b8' }} />
                <YAxis type="category" dataKey="label" tick={{ fontSize: 9, fill: '#cbd5e1' }} width={110} />
                <Tooltip contentStyle={{ background: '#0f1714', border: '1px solid #1f2d27', fontSize: 11 }} />
                <Bar dataKey="mean_abs_shap" fill="#2e7d32" name="impact (SHAP)" />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <p className="text-[10px] italic text-slate-500">{ex.survival.label_definition}</p>
        </div>
      )}
      {ex?.attribution && (
        <div className="rounded-lg border border-[#1f2d27] p-2 text-[11px]">
          <div className="text-[10px] uppercase tracking-wide text-slate-400">Cause model quality</div>
          Macro-F1 <b>{ex.attribution.cv.macro_f1.toFixed(2)}</b> on {ex.attribution.n_events.toLocaleString()} labelled events (grouped CV).
          <ul className="mt-1 grid grid-cols-2 gap-x-2 text-[10px] text-slate-300">
            {Object.entries(ex.attribution.cv.per_class).map(([k, v]) => (
              <li key={k}>
                {CAUSE_LABEL[k] ?? k}: F1 {v['f1-score'].toFixed(2)}
              </li>
            ))}
          </ul>
        </div>
      )}
      <p className="text-[10px] text-slate-500">Turn on “Planting suitability” in Layers to see where planting is most likely to succeed on rangeland and barren land.</p>
    </div>
  )
}

export function ForestPanel(p: {
  summary: Summary | null
  districts: FC<DistrictProps> | null
  alerts: FC<AlertProps> | null
  selectedAlert: string | null
  selectedDistrict: string | null
  onSelectAlert: (id: string | null) => void
  onSelectDistrict: (d: string) => void
}) {
  const [tab, setTab] = useState<Tab>('overview')
  useEffect(() => {
    if (p.selectedAlert) setTab('alerts')
  }, [p.selectedAlert])
  return (
    <div className="flex h-full flex-col">
      <div className="flex border-b border-[#1f2d27] text-xs">
        {(['overview', 'alerts', 'plantations'] as const).map((t) => (
          <button key={t} onClick={() => setTab(t)} className={`flex-1 py-2 capitalize ${tab === t ? 'border-b-2 border-emerald-400 text-emerald-200' : 'text-slate-400'}`}>
            {t}
          </button>
        ))}
      </div>
      <div className="flex-1 overflow-auto p-3">
        {tab === 'overview' && <Overview summary={p.summary} districts={p.districts} selected={p.selectedDistrict} onPick={p.onSelectDistrict} />}
        {tab === 'alerts' &&
          (p.selectedAlert ? (
            <AlertDetail id={p.selectedAlert} onClose={() => p.onSelectAlert(null)} />
          ) : (
            <Alerts alerts={p.alerts} onSelect={(id) => p.onSelectAlert(id)} district={p.selectedDistrict} />
          ))}
        {tab === 'plantations' && <Plantations />}
      </div>
    </div>
  )
}
