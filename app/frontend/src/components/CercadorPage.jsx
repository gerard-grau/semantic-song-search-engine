import { useState, useRef, useCallback, useEffect } from 'react'
import ThemeToggle from './ThemeToggle'
import SongDetail from './SongDetail'
import { cercadorSearch, cercadorSuggestions } from '../api/client'
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

// Trigger gate for the embedding-based suggestion call. The keystroke
// stream feeds two pipelines: the cheap keyword search (150ms debounce
// per keystroke) and the slow embedding search. We don't want to encode
// a 1024-dim BGE-M3 vector on every keystroke — that's the bug the user
// described. Instead we fire only when the user has produced a complete
// new "thought":
//   1. a space immediately after a non-space character (finished a word),
//   2. OR 2s of typing inactivity (assume the prompt is done).
// Multiple consecutive spaces, or repeat firings for the same query
// (deduped against `lastTriggeredRef`), no-op.
const SUGGESTION_IDLE_MS = 2000

function normalizeForTrigger(s) {
  return s.trim().replace(/\s+/g, ' ')
}

export default function CercadorPage({ theme, onToggleTheme, onBack, onDescobreix }) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState(null)
  const [isSearching, setIsSearching] = useState(false)
  const [selectedSongId, setSelectedSongId] = useState(null)

  // Embedding-suggestion pipeline state. `suggestions` is null until the
  // first trigger fires for this query — we use the null marker to hide
  // the Sugerències section before any embedding call has been made.
  const [suggestions, setSuggestions] = useState(null)
  const [lyricsExtra, setLyricsExtra] = useState([])
  // Embedding-suggested group (the lexical engine missed it but the artist
  // embedding matched the query). 0 or 1 entry, kept alongside the lyrics
  // extras so the whole embedding pass shares one fetch.
  const [groupExtra, setGroupExtra] = useState(null)
  const [isSuggesting, setIsSuggesting] = useState(false)
  // Artist filter: when set, all Qdrant suggestion calls are narrowed to
  // songs by this exact artist name via a Qdrant payload filter.
  const [artistFilter, setArtistFilter] = useState(null)
  const artistFilterRef = useRef(null)
  const [suggestionMode, setSuggestionMode] = useState('qualitative')

  function handleModeChange(id) {
    setSuggestionMode(id)
    suggestionModeRef.current = id
    lastTriggeredRef.current = ''
    doSuggestionSearch(latestQueryRef.current)
  }

  const debounceRef = useRef(null)
  const inputRef = useRef(null)
  const inactivityRef = useRef(null)
  // Last normalised query we sent to /cercador/suggestions. Used to
  // dedupe: "a b" triggered, "a b " typed → same normalised → skip.
  const lastTriggeredRef = useRef('')
  // Latest input value, mirrored to a ref so the 2s idle callback fires
  // against the current value rather than the closure-captured one.
  const latestQueryRef = useRef('')
  // Latest /cercador response, mirrored so the embedding call can pass
  // the keyword-cancons ids as exclude_ids without re-creating callbacks.
  const latestResultsRef = useRef(null)
  // Bumped on every suggestion fire so a stale slow response can't
  // overwrite a newer fast one.
  const suggestReqRef = useRef(0)

  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  useEffect(() => { latestResultsRef.current = results }, [results])

  // Cmd/Ctrl + K shortcut
  useEffect(() => {
    function onKey(e) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        inputRef.current?.focus()
        inputRef.current?.select()
      } else if (e.key === 'Escape' && document.activeElement === inputRef.current) {
        if (query) {
          handleClear()
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

  // Keep a ref so the async callback always reads the current filter value
  // without needing to be recreated on every artistFilter state change.
  useEffect(() => { artistFilterRef.current = artistFilter }, [artistFilter])

  const suggestionModeRef = useRef('qualitative')
  useEffect(() => { suggestionModeRef.current = suggestionMode }, [suggestionMode])

  const doSuggestionSearch = useCallback(async (q, forceArtistFilter) => {
    if (!q) return
    const reqId = ++suggestReqRef.current
    const activeFilter = forceArtistFilter !== undefined
      ? forceArtistFilter
      : artistFilterRef.current
    setIsSuggesting(true)
    setSuggestions(null)
    setLyricsExtra([])
    setGroupExtra([])
    try {
      const excludeIds    = (latestResultsRef.current?.cancons || []).map(c => c.id)
      const excludeGroups = (latestResultsRef.current?.grups   || []).map(g => g.name)
      const data = await cercadorSuggestions(q, excludeIds, excludeGroups, activeFilter, suggestionModeRef.current)
      if (reqId !== suggestReqRef.current) return
      setSuggestions(data.suggestions || [])
      setLyricsExtra(data.lyrics_extra || [])
      setGroupExtra(Array.isArray(data.group_extra) ? data.group_extra : (data.group_extra ? [data.group_extra] : []))
    } catch (err) {
      console.error('Suggestion error:', err)
      if (reqId === suggestReqRef.current) {
        setSuggestions([])
        setLyricsExtra([])
        setGroupExtra([])
      }
    } finally {
      if (reqId === suggestReqRef.current) {
        setIsSuggesting(false)
      }
    }
  }, [])

  const maybeFireSuggestion = useCallback((value) => {
    const normalized = normalizeForTrigger(value)
    if (!normalized) return
    if (normalized === lastTriggeredRef.current) return
    lastTriggeredRef.current = normalized
    doSuggestionSearch(normalized)
  }, [doSuggestionSearch])

  function handleInput(e) {
    const newVal = e.target.value
    const oldVal = latestQueryRef.current
    latestQueryRef.current = newVal
    setQuery(newVal)

    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => doSearch(newVal), 150)

    if (inactivityRef.current) clearTimeout(inactivityRef.current)

    // Clearing the field resets the whole pipeline. Without this, an
    // in-flight suggestion request would land later and re-show stale
    // results over an empty query.
    if (!newVal.trim()) {
      suggestReqRef.current++  // invalidate any in-flight response
      lastTriggeredRef.current = ''
      setSuggestions(null)
      setLyricsExtra([])
      setGroupExtra([])
      setIsSuggesting(false)
      return
    }

    // Fire-on-space: only if the new last char is a space AND the
    // previous last char was a real character. Pasting a string ending
    // in a space also counts (oldVal.last is undefined / not-space).
    const lastChar  = newVal.length > 0 ? newVal[newVal.length - 1] : ''
    const prevLast  = oldVal.length > 0 ? oldVal[oldVal.length - 1] : ''
    const grew      = newVal.length > oldVal.length
    if (grew && lastChar === ' ' && prevLast !== ' ') {
      maybeFireSuggestion(newVal)
      return
    }

    // Idle fallback: 2s without further typing → treat as "user finished
    // the prompt". `latestQueryRef` is read inside the callback so it
    // sees whatever the user actually has in the box at fire time.
    inactivityRef.current = setTimeout(() => {
      maybeFireSuggestion(latestQueryRef.current)
    }, SUGGESTION_IDLE_MS)
  }

  function handleClear() {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    if (inactivityRef.current) clearTimeout(inactivityRef.current)
    suggestReqRef.current++  // invalidate in-flight suggestion
    lastTriggeredRef.current = ''
    latestQueryRef.current = ''
    setQuery('')
    setResults(null)
    setSuggestions(null)
    setLyricsExtra([])
    setGroupExtra([])
    setIsSuggesting(false)
    setArtistFilter(null)
    inputRef.current?.focus()
  }

  function handleSetArtistFilter(name) {
    setArtistFilter(name)
    artistFilterRef.current = name
    // Re-fire suggestion search immediately with the new filter
    lastTriggeredRef.current = ''  // allow re-triggering the same query
    doSuggestionSearch(latestQueryRef.current, name)
  }

  function handleClearArtistFilter() {
    setArtistFilter(null)
    artistFilterRef.current = null
    lastTriggeredRef.current = ''
    doSuggestionSearch(latestQueryRef.current, null)
  }

  function handleUseCorrection(corrected) {
    latestQueryRef.current = corrected
    setQuery(corrected)
    doSearch(corrected)
    // Treat a correction click as a "complete prompt" event — fire the
    // embedding pass too without waiting for the next space/idle.
    maybeFireSuggestion(corrected)
  }

  const grupsRaw = results?.grups || []
  const canconsRaw = results?.cancons || []
  const noticies = results?.noticies || []

  // When an artist filter is active, restrict the lexical results to that
  // artist too — otherwise the keyword columns show unfiltered results while
  // the embedding columns are filtered, making the filter look broken.
  const grups   = artistFilter
    ? grupsRaw.filter(g => g.name === artistFilter)
    : grupsRaw
  const cancons = artistFilter
    ? canconsRaw.filter(s => s.artist === artistFilter)
    : canconsRaw

  // Append lyrics_extra to cancons, deduplicating by id. Extras stay
  // tagged via the `_embedding` flag so the UI can mark them and show
  // their % match without conflating them with keyword hits.
  const canconsIds = new Set(cancons.map(c => c.id))
  const extraTagged = lyricsExtra
    .filter(s => !canconsIds.has(s.id))
    .map(s => ({ ...s, _embedding: true }))
  const lletresCombined = [...cancons, ...extraTagged]

  // Append the embedding-suggested groups at the end of the Grups list,
  // marked _embedding so the UI can flag them. The backend already excludes
  // groups that are in the lexical results, so a dupe-by-name check here
  // is belt-and-braces only.
  const grupsNames = new Set(grups.map(g => g.name))
  const grupExtraTagged = (groupExtra || [])
    .filter(g => !grupsNames.has(g.name))
    .map(g => ({ ...g, _embedding: true }))
  const grupsCombined = [...grups, ...grupExtraTagged]

  const hasResults = grupsCombined.length > 0 || lletresCombined.length > 0 || noticies.length > 0
  const showDropdown = query.trim().length > 0
  const showSuggestions = showDropdown && (isSuggesting || (suggestions && suggestions.length > 0))

  const hasLeft = grupsCombined.length > 0 || showSuggestions
  const hasRight = lletresCombined.length > 0 || noticies.length > 0
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

              {artistFilter && (
                <div className="cercador-artist-filter">
                  <span className="cercador-artist-filter-label">Filtrant per:</span>
                  <strong className="cercador-artist-filter-name">{artistFilter}</strong>
                  <button
                    className="cercador-artist-filter-clear"
                    onClick={handleClearArtistFilter}
                    aria-label="Treure filtre d'artista"
                  >×</button>
                </div>
              )}

              {(hasResults || showSuggestions) ? (
                <div className={`cercador-results ${useTwoCol ? 'cercador-results--two-col' : ''}`}>
                  {hasLeft && (
                    <div className="cercador-left-col">
                      {grupsCombined.length > 0 && (
                        <div className="cercador-section cercador-section--grups">
                          <h3 className="cercador-section-title">Grups</h3>
                          {grupsCombined.slice(0, 5).map((g, i) => (
                            <a
                              key={i}
                              className={
                                'cercador-item cercador-item--grup'
                                + (g._embedding ? ' cercador-item--embedding' : '')
                              }
                              href={g.viasona_link || undefined}
                              target={g.viasona_link ? '_blank' : undefined}
                              rel="noopener noreferrer"
                              style={{ textDecoration: 'none', display: 'block', cursor: g.viasona_link ? 'pointer' : 'default' }}
                            >
                              <div className="cercador-item-main">
                                <span className="cercador-grup-name">
                                  {g._embedding && (
                                    <span
                                      className="cercador-embedding-badge"
                                      title={`Sugerit per similitud d'embedding (${Math.round((g.score || 0) * 100)}% match)`}
                                    >
                                      ✦
                                    </span>
                                  )}
                                  {highlightText(g.name, highlightTerms)}
                                </span>
                                {g.viasona_link && (
                                  <span className="cercador-external-icon">↗</span>
                                )}
                                <button
                                  className={
                                    'cercador-filter-btn'
                                    + (artistFilter === g.name ? ' cercador-filter-btn--active' : '')
                                  }
                                  title={artistFilter === g.name ? 'Treure filtre' : `Filtrar per ${g.name}`}
                                  onClick={(e) => {
                                    e.preventDefault()
                                    e.stopPropagation()
                                    if (artistFilter === g.name) {
                                      handleClearArtistFilter()
                                    } else {
                                      handleSetArtistFilter(g.name)
                                    }
                                  }}
                                >
                                  {artistFilter === g.name ? 'Filtrant ✓' : 'Filtrar'}
                                </button>
                              </div>
                              <span className="cercador-grup-meta">
                                {g._embedding
                                  ? <em>Sugerit · {Math.round((g.score || 0) * 100)}% match</em>
                                  : <>
                                      {g.song_count} {g.song_count === 1 ? 'cançó' : 'cançons'}
                                      {g.municipi && <> · {g.municipi}</>}
                                    </>
                                }
                              </span>
                            </a>
                          ))}
                          {grupsCombined.length > 5 && (
                            <div className="cercador-more">Veure'n més →</div>
                          )}
                        </div>
                      )}

                      {showDropdown && (
                        <div className="cercador-mode-wrap">
                          <div className="cercador-mode-seg">
                            {[
                              { id: 'qualitative', label: 'Temàtica', title: 'Cerca per descripció qualitativa' },
                              { id: 'lyrics',      label: 'Lletra',   title: 'Cerca per fragments de lletra' },
                              { id: 'title',       label: 'Títol',    title: 'Cerca per similitud de títol' },
                            ].map(m => (
                              <button
                                key={m.id}
                                className={'cercador-mode-seg-btn' + (suggestionMode === m.id ? ' active' : '')}
                                title={m.title}
                                onClick={() => handleModeChange(m.id)}
                              >
                                {m.label}
                              </button>
                            ))}
                          </div>
                        </div>
                      )}

                      {showSuggestions && (
                        <div className="cercador-section cercador-section--suggestions">
                          <h3 className="cercador-section-title">Sugerències</h3>
                          {isSuggesting ? (
                            <div className="cercador-loading cercador-loading--inline">
                              <span className="cercador-loading-dot" />
                              Generant sugerències…
                            </div>
                          ) : (
                            suggestions.map((s) => (
                              <div
                                key={s.id}
                                className="cercador-item cercador-item--song cercador-item--suggestion"
                                onClick={() => setSelectedSongId(s.id)}
                              >
                                <div className="cercador-item-main">
                                  <span className="cercador-song-title">{s.title}</span>
                                  {s.genre && (
                                    <span
                                      className="cercador-genre-tag"
                                      style={{ background: GENRE_COLORS[s.genre] || '#888' }}
                                    >
                                      {s.genre}
                                    </span>
                                  )}
                                  <span
                                    className="cercador-match-badge"
                                    title="Similitud semàntica amb la teva cerca"
                                  >
                                    ◈ {Math.round((s.score || 0) * 100)}%
                                  </span>
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
                                <div className="cercador-song-sub">{s.artist}</div>
                                {s.lyrics_snippet && (
                                  <div className="cercador-song-snippet">«{s.lyrics_snippet}»</div>
                                )}
                              </div>
                            ))
                          )}
                        </div>
                      )}
                    </div>
                  )}

                  {hasRight && (
                    <div className="cercador-right-col">
                      {lletresCombined.length > 0 && (
                        <div className="cercador-section">
                          <h3 className="cercador-section-title">Lletres</h3>
                          {lletresCombined.map((s) => (
                            <div
                              key={s.id}
                              className={`cercador-item cercador-item--song${s._embedding ? ' cercador-item--embedding' : ''}`}
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
                                {s._embedding && (
                                  <span
                                    className="cercador-match-badge"
                                    title="Similitud semàntica amb la teva cerca"
                                  >
                                    ◈ {Math.round((s.score || 0) * 100)}%
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
