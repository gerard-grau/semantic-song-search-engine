import { useState } from 'react'

/**
 * Filter bar with typed chips.
 *
 * `chips` is now an array of `{ kind, label }` objects:
 *   - kind: 'query'   — free-text semantic search (filters by lyrics + multi-field)
 *   - kind: 'similar' — "songs similar to X" filter from a point click
 *
 * Both kinds are removable and visually distinct (similar chips wear the
 * accent colour so the user can tell at a glance which constraints are
 * active).
 */
export default function FilterBar({ chips, onAddChip, onRemoveChip, onReset, isLoading }) {
  const [input, setInput] = useState('')

  function handleSubmit(e) {
    e.preventDefault()
    const q = input.trim()
    if (q) {
      onAddChip(q)
      setInput('')
    }
  }

  return (
    <form className="filter-bar" onSubmit={handleSubmit}>
      <div className="filter-chips-input">
        {chips.map((chip, i) => {
          const isSimilar = chip.kind === 'similar'
          return (
            <span
              key={i}
              className={`filter-chip${isSimilar ? ' filter-chip--similar' : ''}`}
            >
              {isSimilar && <span className="filter-chip-icon" aria-hidden="true">≈</span>}
              {chip.label}
              <button
                type="button"
                className="filter-chip-remove"
                onClick={() => onRemoveChip(i)}
                disabled={isLoading}
                aria-label="Treu filtre"
              >
                ×
              </button>
            </span>
          )
        })}
        <input
          type="text"
          className="filter-input"
          value={input}
          onChange={e => setInput(e.target.value)}
          placeholder={chips.length ? 'Afegeix un altre filtre...' : 'Escriu una cerca (ex: cançons tristes, amor, rock català)...'}
          disabled={isLoading}
        />
      </div>
      <button type="submit" className="btn-search" disabled={isLoading || !input.trim()}>
        {isLoading ? 'Cercant...' : 'Filtrar'}
      </button>
      {chips.length > 0 && (
        <button type="button" className="btn-reset" onClick={onReset} disabled={isLoading}>
          Reset
        </button>
      )}
    </form>
  )
}
