const MODULES = [
  { id: 'forest', label: 'Forests', icon: '🌲', ready: true },
  { id: 'floods', label: 'Floods', icon: '🌊', ready: false },
  { id: 'glaciers', label: 'Glaciers', icon: '🏔️', ready: false },
]

export function ModuleNav() {
  return (
    <nav className="flex shrink-0 flex-row gap-1 border-[#1f2d27] bg-[#0f1714] p-2 md:w-20 md:flex-col md:border-r">
      {MODULES.map((m) => (
        <button
          key={m.id}
          disabled={!m.ready}
          title={m.ready ? m.label : `${m.label} — coming soon`}
          className={`flex flex-1 flex-col items-center gap-1 rounded-lg px-2 py-2 text-[11px] md:flex-none ${
            m.ready ? 'bg-emerald-900/50 text-emerald-200' : 'cursor-not-allowed text-slate-500'
          }`}
        >
          <span className="text-xl" aria-hidden>
            {m.icon}
          </span>
          {m.label}
          {!m.ready && <span className="text-[9px] uppercase tracking-wide">soon</span>}
        </button>
      ))}
    </nav>
  )
}
