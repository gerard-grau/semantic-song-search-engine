import { useState, useCallback, useRef } from 'react'
import useTheme from './hooks/useTheme'
import WelcomePage from './components/WelcomePage'
import CercadorPage from './components/CercadorPage'
import ThemeToggle from './components/ThemeToggle'
import FilterBar from './components/FilterBar'
import TopResults from './components/TopResults'
import SongDetail from './components/SongDetail'
import HelpPage from './components/HelpPage'
import Scatter2D from './components/visualizations/Scatter2D'
import { fetchAllSongs, filterSongs, filterSimilarTo } from './api/client'
import './App.css'

// Chip shape:
//   { kind: 'query',   value: string,         label: string }
//   { kind: 'similar', value: number (songId), label: string }
//
// Filters compose progressively: each chip narrows the current alive set,
// regardless of kind. Removing a chip re-runs the remaining chips from
// scratch so the result reflects the displayed constraints exactly.
//
// The genre legend is a SEPARATE filter dimension — clicking a legend item
// toggles a slug in ``selectedGenres`` and the survivors are intersected
// locally (every song already carries its genre from /api/songs). It is
// not a chip: there's no round-trip, no scoring, no embedding — just a
// metadata filter visualised by the legend highlight.
export default function App() {
  const { theme, toggleTheme } = useTheme()

  const [page, setPage] = useState('welcome')

  const [allSongs, setAllSongs] = useState([])
  const [baseProj2d, setBaseProj2d] = useState([])

  // null = no filter applied (everything is active).
  const [activeIds, setActiveIds] = useState(null)
  // Combined score per surviving song: arithmetic mean of its per-chip
  // scores. Stored separately so we don't recompute on every render.
  const [scoreMap, setScoreMap] = useState({})
  // One score map per chip, in chip order. Lets the right panel break
  // the combined score back down into "boig: 0.81, amore: 0.74, …".
  const [chipScoreMaps, setChipScoreMaps] = useState([])

  const [chips, setChips] = useState([])
  // Genre legend selection — independent of chips. Empty = no genre filter.
  const [selectedGenres, setSelectedGenres] = useState([])

  const [selectedSongId, setSelectedSongId] = useState(null)
  const [highlightedId, setHighlightedId] = useState(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState(null)
  const [message, setMessage] = useState(null)
  const [showHelp, setShowHelp] = useState(false)

  const aliveIdsRef = useRef(null)

  // The most recent "similar" chip's song id becomes the visualization's
  // focal (diamond) so the anchor of the current similarity filter stays
  // visible while other filters compose.
  const focalSimilarId = (() => {
    for (let i = chips.length - 1; i >= 0; i--) {
      if (chips[i].kind === 'similar') return chips[i].value
    }
    return null
  })()

  // Intersect chip-derived survivors with the genre legend selection.
  // Either dimension can be null/empty independently:
  //   - no chips, no genres  → finalActiveIds = null (everything is alive)
  //   - only chips           → finalActiveIds = activeIds
  //   - only genres          → finalActiveIds = songs whose genre is selected
  //   - both                 → intersection of the two
  const finalActiveIds = (() => {
    if (selectedGenres.length === 0) return activeIds
    const wanted = new Set(selectedGenres)
    if (activeIds == null) {
      return new Set(allSongs.filter(s => wanted.has(s.genre)).map(s => s.id))
    }
    const out = new Set()
    for (const s of allSongs) {
      if (activeIds.has(s.id) && wanted.has(s.genre)) out.add(s.id)
    }
    return out
  })()

  const displaySongs = finalActiveIds
    ? allSongs
        .filter(s => finalActiveIds.has(s.id))
        .map(s => ({ ...s, score: scoreMap[s.id] ?? 0 }))
        .sort((a, b) => b.score - a.score)
    : allSongs

  const loadAll = useCallback(async () => {
    setIsLoading(true)
    setError(null)
    try {
      const data = await fetchAllSongs()
      setAllSongs(data.songs)
      setBaseProj2d(data.projections_2d)
      setActiveIds(null)
      setScoreMap({})
      setChipScoreMaps([])
      setChips([])
      setSelectedGenres([])
      setMessage(null)
      aliveIdsRef.current = null
    } catch (err) {
      setError("No s'ha pogut connectar amb el servidor.")
      console.error(err)
    } finally {
      setIsLoading(false)
    }
  }, [])

  async function handleEnter() {
    await loadAll()
    setPage('main')
  }

  // Apply one chip on top of the current alive set. Both kinds round-trip
  // to the backend; the genre filter is no longer a chip (see ``selectedGenres``).
  async function applyChip(chip, aliveIds) {
    if (chip.kind === 'similar') {
      return filterSimilarTo(chip.value, aliveIds)
    }
    return filterSongs(chip.value, aliveIds)
  }

  // Re-run an ordered list of chips from scratch (used on add and remove).
  // Returns the final alive set + per-chip score maps so the right panel
  // can display a combined score and a per-chip breakdown.
  async function applyChipsFromScratch(orderedChips) {
    let alive = null
    const perChipMaps = []
    let lastMessage = null
    for (const chip of orderedChips) {
      const data = await applyChip(chip, alive)
      const map = {}
      data.songs.forEach(s => { map[s.id] = s.score ?? 0 })
      perChipMaps.push(map)
      alive = data.songs.map(s => s.id)
      lastMessage = data.message ?? null
    }
    return { alive, perChipMaps, lastMessage }
  }

  async function handleAddChip(text) {
    const q = (text || '').trim()
    if (!q) return
    await runChipUpdate([...chips, { kind: 'query', value: q, label: q }])
  }

  async function handleAddSimilarChip(songId, title) {
    if (songId == null) return
    const label = title ? `similars a "${title}"` : `similars a #${songId}`
    // Replace existing similar chip if it points to the same song.
    const filtered = chips.filter(c => !(c.kind === 'similar' && c.value === songId))
    await runChipUpdate([...filtered, { kind: 'similar', value: songId, label }])
  }

  // Plain click  ⇒ replace selection with just this slug; if it was already
  //                 the single active slug, clear the selection.
  // Ctrl/⌘-click ⇒ toggle this slug in the existing set.
  function handleToggleGenre(slug, additive = false) {
    if (!slug) return
    setSelectedGenres(current => {
      if (additive) {
        return current.includes(slug)
          ? current.filter(g => g !== slug)
          : [...current, slug]
      }
      if (current.length === 1 && current[0] === slug) return []
      return [slug]
    })
  }

  async function handleRemoveChip(index) {
    const newChips = chips.filter((_, i) => i !== index)
    if (newChips.length === 0) {
      setChips([])
      setActiveIds(null)
      setScoreMap({})
      setChipScoreMaps([])
      aliveIdsRef.current = null
      setMessage(null)
      return
    }
    await runChipUpdate(newChips)
  }

  async function runChipUpdate(newChips) {
    setIsLoading(true)
    setError(null)
    try {
      const { alive, perChipMaps, lastMessage } = await applyChipsFromScratch(newChips)
      aliveIdsRef.current = alive
      setActiveIds(new Set(alive))
      // Combined score = arithmetic mean of per-chip scores. Every remaining
      // chip kind is a ranking chip now (the genre filter lives outside the
      // chip pipeline) so the mean is just over all chips.
      const combined = {}
      for (const id of alive) {
        if (newChips.length === 0) { combined[id] = 1; continue }
        let sum = 0
        for (let i = 0; i < newChips.length; i++) sum += (perChipMaps[i][id] ?? 0)
        combined[id] = sum / newChips.length
      }
      setScoreMap(combined)
      setChipScoreMaps(perChipMaps)
      setChips(newChips)
      setMessage(lastMessage)
    } catch (err) {
      setError('Error aplicant filtres.')
      console.error(err)
    } finally {
      setIsLoading(false)
    }
  }

  function handleReset() {
    setActiveIds(null)
    setScoreMap({})
    setChipScoreMaps([])
    setChips([])
    setSelectedGenres([])
    setMessage(null)
    aliveIdsRef.current = null
  }

  function handleOpenDetail(songId) {
    setSelectedSongId(songId)
  }

  if (page === 'welcome') {
    return (
      <WelcomePage
        onEnter={handleEnter}
        onCercador={() => setPage('cercador')}
        theme={theme}
        onToggleTheme={toggleTheme}
        isLoading={isLoading}
      />
    )
  }

  if (page === 'cercador') {
    return (
      <CercadorPage
        theme={theme}
        onToggleTheme={toggleTheme}
        onBack={() => setPage('welcome')}
        onDescobreix={handleEnter}
      />
    )
  }

  const activeCount = finalActiveIds ? finalActiveIds.size : allSongs.length
  const isFiltered  = finalActiveIds != null

  return (
    <div className="app">
      <header className="app-header">
        <div className="header-left">
          <button className="header-home-btn" onClick={() => setPage('welcome')}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M19 12H5M12 19l-7-7 7-7" />
            </svg>
            Inici
          </button>
          <span className="header-divider" />
          <h1 className="header-title">
            <em>Descobridor</em>
          </h1>
        </div>
        <div className="header-right">
          <button
            className="header-help-btn"
            onClick={() => setShowHelp(true)}
            aria-label="Ajuda — què pots fer"
            title="Ajuda — què pots fer"
            type="button"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <circle cx="12" cy="12" r="9.5" />
              <path d="M9.2 9.2a2.8 2.8 0 1 1 3.9 2.6c-.8.4-1.1 1-1.1 2" />
              <circle cx="12" cy="17" r="0.6" fill="currentColor" stroke="none" />
            </svg>
          </button>
          <button className="header-link-btn" onClick={() => setPage('cercador')}>Cercador</button>
          <ThemeToggle theme={theme} onToggle={toggleTheme} inline />
        </div>
      </header>

      {error && <div className="error-banner">{error}</div>}

      <main className="app-main">
        <section className="panel-left">
          <TopResults
            songs={displaySongs}
            message={message}
            query={chips.length > 0 ? chips[chips.length - 1].label : ''}
            chips={chips}
            chipScoreMaps={chipScoreMaps}
            onSongHover={setHighlightedId}
            onSongClick={handleOpenDetail}
            highlightedId={highlightedId}
          />
        </section>

        <section className="panel-right">
          <div className="viz-bar">
            <FilterBar
              chips={chips}
              onAddChip={handleAddChip}
              onRemoveChip={handleRemoveChip}
              onReset={handleReset}
              isLoading={isLoading}
            />
          </div>

          <div className="viz-bar viz-bar--controls">
            <span className="viz-count">
              {isFiltered ? (
                <><strong>{activeCount}</strong> / {allSongs.length} cançons</>
              ) : (
                <><strong>{allSongs.length}</strong> cançons al mapa</>
              )}
            </span>
          </div>

          <div className="viz-area">
            <Scatter2D
              points={baseProj2d}
              activeIds={finalActiveIds}
              focalId={focalSimilarId}
              highlightedId={highlightedId}
              onPointHover={setHighlightedId}
              onPointOpenDetail={handleOpenDetail}
              onAddGenreChip={handleToggleGenre}
              activeGenres={selectedGenres}
            />
          </div>
        </section>
      </main>

      <SongDetail
        songId={selectedSongId}
        onClose={() => setSelectedSongId(null)}
        onFilterSimilar={handleAddSimilarChip}
      />

      {showHelp && <HelpPage onClose={() => setShowHelp(false)} />}
    </div>
  )
}
