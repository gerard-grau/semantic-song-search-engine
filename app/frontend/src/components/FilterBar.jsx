import { useState } from 'react'
import { GENRE_COLORS } from './visualizations/genreColors'

/**
 * Filter bar with typed chips.
 *
 * `chips` is an array of `{ kind, value, label }` objects:
 *   - kind: 'query'   — free-text semantic search (multi-field cosine).
 *   - kind: 'similar' — "songs similar to X" filter from a point click.
 *   - kind: 'genre'   — hard metadata filter; added by clicking a legend
 *                       swatch on the visualization (Scatter2D owns the
 *                       legend, which doubles as the genre filter UI).
 *
 * All three kinds are removable and share the chip primitive; only the
 * styling differs (similar wears the brand accent; genre wears its own
 * genre colour from genreColors.js).
 */
export default function FilterBar({
  chips, onAddChip, onRemoveChip, onReset, isLoading,
}) {
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
          const isGenre   = chip.kind === 'genre'
          // Normalise genre value to an array; chips authored before
          // multi-select might still be plain strings in flight.
          const genres = isGenre
            ? (Array.isArray(chip.value) ? chip.value : [chip.value])
            : []
          // Single-genre chip wears its own colour (cohesive with the legend
          // pill it came from). Multi-genre chip stays on the neutral chip
          // background and prefixes a coloured dot per slug — wearing only
          // the first colour would lie about which genres are active.
          const style = (isGenre && genres.length === 1)
            ? { background: GENRE_COLORS[genres[0]], color: '#0e1116' }
            : undefined
          return (
            <span
              key={i}
              className={
                'filter-chip'
                + (isSimilar ? ' filter-chip--similar' : '')
                + (isGenre   ? ' filter-chip--genre'   : '')
                + (isGenre && genres.length > 1 ? ' filter-chip--genre-multi' : '')
              }
              style={style}
            >
              {isSimilar && <span className="filter-chip-icon" aria-hidden="true">≈</span>}
              {isGenre && genres.length === 1 && (
                <span className="filter-chip-icon" aria-hidden="true">●</span>
              )}
              {isGenre && genres.length > 1 && (
                <span className="filter-chip-genre-dots" aria-hidden="true">
                  {genres.map(g => (
                    <span
                      key={g}
                      className="filter-chip-genre-dot"
                      style={{ background: GENRE_COLORS[g] }}
                    />
                  ))}
                </span>
              )}
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
