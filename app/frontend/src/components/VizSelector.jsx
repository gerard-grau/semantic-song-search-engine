const MODES = [
  { key: '2D', label: 'Dispersió 2D' },
  { key: '3D', label: 'Dispersió 3D' },
  { key: 'nav', label: 'Navegació' },
]

export default function VizSelector({ mode, onChange }) {
  return (
    <div className="viz-selector">
      {MODES.map(m => (
        <button
          key={m.key}
          className={`viz-selector-btn ${mode === m.key ? 'viz-selector-btn--active' : ''}`}
          onClick={() => onChange(m.key)}
        >
          {m.label}
        </button>
      ))}
    </div>
  )
}
