import { useEffect, useState } from 'react'
import { api, CAUSE_LABEL, type AlertProps } from '../api'

function BeforeAfter({ before, after }: { before: string; after: string }) {
  const [pos, setPos] = useState(50)
  return (
    <div className="relative aspect-square w-full overflow-hidden rounded-lg border border-[#1f2d27]">
      <img src={after} alt="After (recent)" className="absolute inset-0 h-full w-full object-cover" />
      <img
        src={before}
        alt="Before (one year earlier)"
        className="absolute inset-0 h-full w-full object-cover"
        style={{ clipPath: `inset(0 ${100 - pos}% 0 0)` }}
      />
      <div className="pointer-events-none absolute inset-y-0 w-0.5 bg-white" style={{ left: `${pos}%` }} />
      <span className="absolute left-2 top-2 rounded bg-black/60 px-1.5 py-0.5 text-[10px]">Before</span>
      <span className="absolute right-2 top-2 rounded bg-black/60 px-1.5 py-0.5 text-[10px]">After</span>
      <input
        aria-label="Before/after slider"
        type="range"
        min={0}
        max={100}
        value={pos}
        onChange={(e) => setPos(Number(e.target.value))}
        className="absolute inset-x-2 bottom-2 accent-white"
      />
    </div>
  )
}

const fmt = (v: number | null | undefined, d = 2) => (v === null || v === undefined ? '—' : v.toFixed(d))

export function AlertDetail({ id, onClose }: { id: string; onClose: () => void }) {
  const [a, setA] = useState<AlertProps | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [sent, setSent] = useState(false)
  const [retrying, setRetrying] = useState(false)

  useEffect(() => {
    setA(null)
    setErr(null)
    setSent(false)
    api.alert(id).then((f) => setA(f.properties)).catch((e) => setErr(String(e)))
  }, [id])

  const retryImages = () => {
    setRetrying(true)
    api
      .alert(id)
      .then((f) => setA(f.properties))
      .catch((e) => setErr(String(e)))
      .finally(() => setRetrying(false))
  }

  return (
    <div className="space-y-3">
      <button onClick={onClose} className="text-xs text-emerald-300 hover:underline">
        ← All alerts
      </button>
      {err && <p className="text-xs text-red-400">{err}</p>}
      {!a && !err && <p className="animate-pulse text-xs text-slate-400">Loading imagery and running cause model (first open can take ~20 s)…</p>}
      {a && (
        <>
          <div>
            <div className="flex items-center gap-2">
              <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${a.type === 'logging' ? 'bg-red-600' : 'bg-amber-600'}`}>
                {a.type}
              </span>
              <span className="text-sm font-semibold">{a.district}</span>
              {a.confidence && (
                <span className={`rounded px-1.5 py-0.5 text-[10px] ${a.confidence === 'high' ? 'bg-red-900' : 'bg-slate-700'}`}>
                  {a.confidence === 'high' ? 'high confidence' : 'standard'}
                </span>
              )}
              <span className="ml-auto text-xs text-slate-400">priority {a.priority}</span>
            </div>
            <p className="mt-1 text-[11px] text-slate-400">
              {a.area_ha} ha · {a.lat.toFixed(4)}, {a.lon.toFixed(4)} · {a.prior_window[0]} → {a.recent_window[1]}
            </p>
          </div>

          {a.images?.before && a.images?.after ? (
            <BeforeAfter before={a.images.before} after={a.images.after} />
          ) : (
            <div className="flex aspect-square w-full flex-col items-center justify-center gap-2 rounded-lg border border-[#1f2d27] p-4 text-center">
              <p className="text-xs text-amber-300">{retrying ? 'Fetching satellite images…' : a.images?.error ?? 'Imagery unavailable'}</p>
              <button
                onClick={retryImages}
                disabled={retrying}
                className="rounded-lg bg-emerald-700 px-3 py-1.5 text-xs font-semibold hover:bg-emerald-600 disabled:bg-slate-600"
              >
                {retrying ? 'Retrying…' : 'Retry'}
              </button>
            </div>
          )}

          {a.attribution && (
            <div className="rounded-lg border border-[#1f2d27] p-2">
              <div className="text-[10px] uppercase tracking-wide text-slate-400">Likely cause (AI)</div>
              <div className="text-sm font-semibold">
                {CAUSE_LABEL[a.attribution.cause] ?? a.attribution.cause}
                {a.attribution.confidence != null && (
                  <span className="ml-2 text-xs font-normal text-slate-400">{Math.round(a.attribution.confidence * 100)}% confidence</span>
                )}
              </div>
              {a.attribution.fire_override && <p className="text-[11px] text-amber-300">NASA FIRMS detected a fire here near the event date.</p>}
              {a.attribution.probabilities && (
                <div className="mt-2 space-y-1">
                  {Object.entries(a.attribution.probabilities)
                    .sort((x, y) => y[1] - x[1])
                    .map(([k, v]) => (
                      <div key={k} className="flex items-center gap-2 text-[10px]">
                        <span className="w-32 truncate text-slate-300">{CAUSE_LABEL[k] ?? k}</span>
                        <div className="h-1.5 flex-1 rounded bg-[#1f2d27]">
                          <div className="h-1.5 rounded bg-emerald-500" style={{ width: `${v * 100}%` }} />
                        </div>
                        <span className="w-8 text-right">{Math.round(v * 100)}%</span>
                      </div>
                    ))}
                </div>
              )}
              {a.attribution.event_date && <p className="mt-1 text-[10px] text-slate-400">Estimated change date: {a.attribution.event_date}</p>}
              {(a.attribution.note || a.attribution.error) && (
                <p className="mt-1 text-[10px] text-slate-400">{a.attribution.note ?? a.attribution.error}</p>
              )}
              <p className="mt-1 text-[10px] italic text-slate-500">
                Cause model trained on European Sentinel-2 disturbance labels (DISFOR); treat as a lead for field verification.
              </p>
            </div>
          )}

          <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-[11px]">
            <dt className="text-slate-400">Greenness change (ΔNDVI)</dt>
            <dd>{fmt(a.dndvi)}</dd>
            <dt className="text-slate-400">Burn/clearing index (ΔNBR)</dt>
            <dd>{fmt(a.dnbr)}</dd>
            <dt className="text-slate-400">Radar VH change</dt>
            <dd>{fmt(a.s1_vh_change_db, 1)} dB</dd>
            <dt className="text-slate-400">Protected area</dt>
            <dd>{a.in_protected_area ? 'Yes' : 'No'}</dd>
            <dt className="text-slate-400">Distance to road</dt>
            <dd>{a.road_dist_m == null ? '—' : `${Math.round(a.road_dist_m)} m`}</dd>
          </dl>

          <button
            onClick={() => setSent(true)}
            className="w-full rounded-lg bg-emerald-600 py-2 text-xs font-semibold hover:bg-emerald-500 disabled:bg-slate-600"
            disabled={sent}
          >
            {sent ? 'Queued for field team (demo — dispatch module not connected yet)' : 'Send to forest field team'}
          </button>
          <a
            className="block text-center text-[11px] text-emerald-300 hover:underline"
            href={`https://www.google.com/maps?q=${a.lat},${a.lon}`}
            target="_blank"
            rel="noreferrer"
          >
            Open location in Google Maps
          </a>
        </>
      )}
    </div>
  )
}
