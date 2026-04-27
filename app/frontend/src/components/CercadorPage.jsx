import { useState, useRef, useCallback, useEffect } from 'react'
import ThemeToggle from './ThemeToggle'
import SongDetail from './SongDetail'
import { cercadorSearch } from '../api/client'

const GENRE_COLORS = {
  pop: '#FF6B6B',
  rock: '#00BFA5',
  folk: '#4FC3F7',
  electronica: '#AB47BC',
  'hip-hop': '#FFB74D',
  rumba: '#FF8A65',
}

/**
 * Highlight all occurrences of any term in `terms` within `text`.
 * Used to highlight both the original query AND the corrected form,
 * so "buos" → finds "Buhos" and highlights it because the corrected
 * form "buhos" is also in the terms list.
 */
function highlightText(text, terms) {
  if (!terms || terms.length === 0) return text
  // Filter out very short terms to avoid noise
  const validTerms = terms.filter(t => t && t.length >= 2)
  if (validTerms.length === 0) return text
  const escaped = validTerms.map(t => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
  const regex = new RegExp(`(${escaped.join('|')})`, 'gi')
  const parts = text.split(regex)
  return parts.map((part, i) =>
    regex.test(part) ? <mark key={i} className="cerca-highlight">{part}</mark> : part
  )
}

export default function CercadorPage({ theme, onToggleTheme, onBack, onDescobreix }) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState(null)
  const [isSearching, setIsSearching] = useState(false)
  const [selectedSongId, setSelectedSongId] = useState(null)
  const debounceRef = useRef(null)
  const inputRef = useRef(null)

  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  const doSearch = useCallback(async (q) => {
    if (!q.trim()) {
      setResults(null)
      return
    }
    setIsSearching(true)
    try {
      const data = await cercadorSearch(q)
      setResults(data)
    } catch (err) {
      console.error('Search error:', err)
    } finally {
      setIsSearching(false)
    }
  }, [])

  function handleInput(e) {
    const val = e.target.value
    setQuery(val)
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => doSearch(val), 150)
  }

  function handleClear() {
    setQuery('')
    setResults(null)
    inputRef.current?.focus()
  }

  function handleUseCorrection(corrected) {
    setQuery(corrected)
    doSearch(corrected)
  }

  const grups = results?.grups || []
  const cancons = results?.cancons || []
  const noticies = results?.noticies || []
  const hasResults = grups.length > 0 || cancons.length > 0 || noticies.length > 0
  const showDropdown = query.trim().length > 0

  const hasLeft = grups.length > 0
  const hasRight = cancons.length > 0 || noticies.length > 0
  const useTwoCol = hasLeft && hasRight

  // Build highlight terms: original query + corrected form
  const highlightTerms = [query.trim()]
  if (results?.correction?.corrected) {
    highlightTerms.push(results.correction.corrected)
    // Also add individual words of corrected form
    results.correction.corrected.split(/\s+/).forEach(w => {
      if (w.length >= 3) highlightTerms.push(w)
    })
  }
  // Add individual words of query
  query.trim().split(/\s+/).forEach(w => {
    if (w.length >= 3) highlightTerms.push(w)
  })

  return (
    <div className="cercador-page">
      <ThemeToggle theme={theme} onToggle={onToggleTheme} />

      <div className="cercador-nav">
        <button className="cercador-nav-btn" onClick={onBack}>
          ← Tornar
        </button>
        <button className="cercador-nav-btn cercador-nav-btn--accent" onClick={onDescobreix}>
          Descobreix Viasona
        </button>
      </div>

      <div className="cercador-container">
        <h1 className="cercador-title">Cerca Viasona</h1>

        <div className="cercador-search-wrap">
          <div className="cercador-input-row">
            <span className="cercador-icon">&#128269;</span>
            <input
              ref={inputRef}
              type="text"
              className="cercador-input"
              placeholder="Cerca grups, lletres, noticies..."
              value={query}
              onChange={handleInput}
              autoComplete="off"
              spellCheck="false"
            />
            {query && (
              <button className="cercador-clear" onClick={handleClear}>
                ×
              </button>
            )}
          </div>

          {showDropdown && (
            <div className="cercador-dropdown">
              {isSearching && !results && (
                <div className="cercador-loading">Cercant...</div>
              )}

              {results && results.correction && (
                <div className="cercador-correction">
                  Volies dir:{' '}
                  <button
                    className="cercador-correction-btn"
                    onClick={() => handleUseCorrection(results.correction.corrected)}
                  >
                    {results.correction.corrected}
                  </button>
                  {results.correction.suggestions?.length > 0 && (
                    <span className="cercador-suggestions">
                      {' '}o potser{' '}
                      {results.correction.suggestions.slice(0, 2).map((s, i) => (
                        <span key={i}>
                          {i > 0 && ', '}
                          <button
                            className="cercador-suggestion-btn"
                            onClick={() => handleUseCorrection(s)}
                          >
                            {s}
                          </button>
                        </span>
                      ))}
                    </span>
                  )}
                </div>
              )}

              {hasResults ? (
                <div className={`cercador-results ${useTwoCol ? 'cercador-results--two-col' : ''}`}>
                  {/* LEFT COLUMN: GRUPS */}
                  {grups.length > 0 && (
                    <div className="cercador-section cercador-section--grups">
                      <h3 className="cercador-section-title">GRUPS</h3>
                      {grups.map((g, i) => (
                        <div key={i} className="cercador-item cercador-item--grup">
                          <div className="cercador-item-main">
                            <span className="cercador-grup-name">
                              {highlightText(g.name, highlightTerms)}
                            </span>
                          </div>
                          <span className="cercador-grup-meta">
                            {g.song_count} {g.song_count === 1 ? 'canco' : 'cancons'}
                            {g.genres?.length > 0 && (
                              <> · {g.genres.join(', ')}</>
                            )}
                          </span>
                        </div>
                      ))}
                      {grups.length >= 5 && (
                        <div className="cercador-more">Veure'n mes resultats →</div>
                      )}
                    </div>
                  )}

                  {/* RIGHT COLUMN: wrap cancons + noticies */}
                  {hasRight && (
                    <div className="cercador-right-col">
                      {/* LLETRES */}
                      {cancons.length > 0 && (
                        <div className="cercador-section">
                          <h3 className="cercador-section-title">LLETRES</h3>
                          {cancons.map((s) => (
                            <div
                              key={s.id}
                              className="cercador-item cercador-item--song"
                              onClick={() => setSelectedSongId(s.id)}
                            >
                              <div className="cercador-item-main">
                                <span className="cercador-song-title">
                                  {highlightText(s.title, highlightTerms)}
                                </span>
                                {s.genre && (
                                  <span
                                    className="cercador-genre-tag"
                                    style={{ background: GENRE_COLORS[s.genre] || '#888' }}
                                  >
                                    {s.genre}
                                  </span>
                                )}
                              </div>
                              <div className="cercador-song-sub">
                                {highlightText(s.artist, highlightTerms)}
                              </div>
                              {s.lyrics_snippet && (
                                <div className="cercador-song-snippet">
                                  ...{highlightText(s.lyrics_snippet, highlightTerms)}
                                </div>
                              )}
                            </div>
                          ))}
                          {cancons.length >= 8 && (
                            <div className="cercador-more">Veure'n mes resultats →</div>
                          )}
                        </div>
                      )}

                      {/* NOTICIES */}
                      {noticies.length > 0 && (
                        <div className="cercador-section">
                          <h3 className="cercador-section-title">NOTICIES</h3>
                          {noticies.map((n) => (
                            <div key={n.id} className="cercador-item cercador-item--noticia">
                              <div className="cercador-item-main">
                                <span className="cercador-noticia-title">
                                  {highlightText(n.title, highlightTerms)}
                                </span>
                              </div>
                              <span className="cercador-noticia-date">{n.date}</span>
                            </div>
                          ))}
                          {noticies.length >= 5 && (
                            <div className="cercador-more">Veure'n mes resultats →</div>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ) : (
                results && !isSearching && (
                  <div className="cercador-empty">
                    No s'han trobat resultats per «{query}»
                  </div>
                )
              )}
            </div>
          )}
        </div>
      </div>

      <SongDetail songId={selectedSongId} onClose={() => setSelectedSongId(null)} />
    </div>
  )
}
