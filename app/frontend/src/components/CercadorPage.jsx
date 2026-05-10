import { useState, useRef, useCallback, useEffect } from 'react'
import ThemeToggle from './ThemeToggle'
import SongDetail from './SongDetail'
import { cercadorSearch } from '../api/client'
import { GENRE_COLORS } from './visualizations/genreColors'

/**
 * Highlight all occurrences of any term in `terms` within `text`.
 */
function highlightText(text, terms) {
  if (!terms || terms.length === 0) return text
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

  // Cmd/Ctrl + K shortcut
  useEffect(() => {
    function onKey(e) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        inputRef.current?.focus()
        inputRef.current?.select()
      } else if (e.key === 'Escape' && document.activeElement === inputRef.current) {
        if (query) {
          setQuery('')
          setResults(null)
        }
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [query])

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

  const highlightTerms = [query.trim()]
  if (results?.correction?.corrected) {
    highlightTerms.push(results.correction.corrected)
    results.correction.corrected.split(/\s+/).forEach(w => {
      if (w.length >= 3) highlightTerms.push(w)
    })
  }
  query.trim().split(/\s+/).forEach(w => {
    if (w.length >= 3) highlightTerms.push(w)
  })

  return (
    <div className="cercador-page">
      <header className="cercador-nav">
        <button className="cercador-nav-btn" onClick={onBack}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M19 12H5M12 19l-7-7 7-7" />
          </svg>
          Inici
        </button>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          <button className="cercador-nav-btn cercador-nav-btn--accent" onClick={onDescobreix}>
            Descobridor
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M5 12h14M13 5l7 7-7 7" />
            </svg>
          </button>
          <ThemeToggle theme={theme} onToggle={onToggleTheme} inline />
        </div>
      </header>

      <main className="cercador-container">
        <span className="cercador-eyebrow">Cercador</span>
        <h1 className="cercador-title">
          Què vols <em>escoltar</em> avui?
        </h1>
        <p className="cercador-lede">
          Cerca per nom de grup, títol de cançó, una frase d'una lletra o una notícia.
        </p>

        <div className="cercador-search-wrap">
          <div className="cercador-input-row">
            <span className="cercador-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="11" cy="11" r="7" />
                <path d="m20 20-3.5-3.5" />
              </svg>
            </span>
            <input
              ref={inputRef}
              type="text"
              className="cercador-input"
              placeholder="Cerca grups, lletres, notícies…"
              value={query}
              onChange={handleInput}
              autoComplete="off"
              spellCheck="false"
            />
            {query && (
              <button className="cercador-clear" onClick={handleClear} aria-label="Esborrar cerca">
                ×
              </button>
            )}
          </div>

          {!showDropdown && (
            <div className="cercador-kbd-hint">
              <span><span className="cercador-kbd">⌘</span><span className="cercador-kbd">K</span> per enfocar</span>
              <span><span className="cercador-kbd">esc</span> per netejar</span>
            </div>
          )}

          {showDropdown && (
            <div className="cercador-dropdown">
              {isSearching && !results && (
                <div className="cercador-loading">Cercant…</div>
              )}

              {results && results.correction && (
                <div className="cercador-correction">
                  Volies dir{' '}
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
                  {grups.length > 0 && (
                    <div className="cercador-section cercador-section--grups">
                      <h3 className="cercador-section-title">Grups</h3>
                      {grups.map((g, i) => (
                        <a
                          key={i}
                          className="cercador-item cercador-item--grup"
                          href={g.viasona_link || undefined}
                          target={g.viasona_link ? '_blank' : undefined}
                          rel="noopener noreferrer"
                          style={{ textDecoration: 'none', display: 'block', cursor: g.viasona_link ? 'pointer' : 'default' }}
                        >
                          <div className="cercador-item-main">
                            <span className="cercador-grup-name">
                              {highlightText(g.name, highlightTerms)}
                            </span>
                            {g.viasona_link && (
                              <span className="cercador-external-icon">↗</span>
                            )}
                          </div>
                          <span className="cercador-grup-meta">
                            {g.song_count} {g.song_count === 1 ? 'cançó' : 'cançons'}
                            {g.municipi && <> · {g.municipi}</>}
                          </span>
                        </a>
                      ))}
                      {grups.length >= 5 && (
                        <div className="cercador-more">Veure'n més →</div>
                      )}
                    </div>
                  )}

                  {hasRight && (
                    <div className="cercador-right-col">
                      {cancons.length > 0 && (
                        <div className="cercador-section">
                          <h3 className="cercador-section-title">Lletres</h3>
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
                                {s.url && (
                                  <a
                                    href={s.url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="cercador-external-icon"
                                    onClick={e => e.stopPropagation()}
                                  >↗</a>
                                )}
                              </div>
                              <div className="cercador-song-sub">
                                {highlightText(s.artist, highlightTerms)}
                              </div>
                              {s.lyrics_snippet && (
                                <div className="cercador-song-snippet">
                                  «{highlightText(s.lyrics_snippet, highlightTerms)}»
                                </div>
                              )}
                            </div>
                          ))}
                          {cancons.length >= 8 && (
                            <div className="cercador-more">Veure'n més →</div>
                          )}
                        </div>
                      )}

                      {noticies.length > 0 && (
                        <div className="cercador-section">
                          <h3 className="cercador-section-title">Notícies</h3>
                          {noticies.map((n) => (
                            <a
                              key={n.id}
                              className="cercador-item cercador-item--noticia"
                              href={n.viasona_link || undefined}
                              target={n.viasona_link ? '_blank' : undefined}
                              rel="noopener noreferrer"
                              style={{ textDecoration: 'none', display: 'block', cursor: n.viasona_link ? 'pointer' : 'default' }}
                            >
                              <div className="cercador-item-main">
                                <span className="cercador-noticia-title">
                                  {highlightText(n.title, highlightTerms)}
                                </span>
                                {n.viasona_link && (
                                  <span className="cercador-external-icon">↗</span>
                                )}
                              </div>
                              {n.snippet && (
                                <div className="cercador-noticia-snippet">
                                  {highlightText(n.snippet, highlightTerms)}
                                </div>
                              )}
                              <span className="cercador-noticia-date">{n.date}</span>
                            </a>
                          ))}
                          {noticies.length >= 5 && (
                            <div className="cercador-more">Veure'n més →</div>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ) : (
                results && !isSearching && (
                  <div className="cercador-empty">
                    Cap resultat per <strong>«{query}»</strong>
                  </div>
                )
              )}
            </div>
          )}
        </div>
      </main>

      <SongDetail songId={selectedSongId} onClose={() => setSelectedSongId(null)} />
    </div>
  )
}
