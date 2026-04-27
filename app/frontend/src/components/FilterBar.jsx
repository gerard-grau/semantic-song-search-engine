import { useState } from 'react'

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
        {chips.map((chip, i) => (
          <span key={i} className="filter-chip">
            {chip}
            <button
              type="button"
              className="filter-chip-remove"
              onClick={() => onRemoveChip(i)}
              disabled={isLoading}
            >
              ×
            </button>
          </span>
        ))}
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
