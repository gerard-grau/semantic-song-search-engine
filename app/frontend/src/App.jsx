import { useState, useCallback, useRef } from 'react'
import useTheme from './hooks/useTheme'
import WelcomePage from './components/WelcomePage'
import CercadorPage from './components/CercadorPage'
import ThemeToggle from './components/ThemeToggle'
import FilterBar from './components/FilterBar'
import TopResults from './components/TopResults'
import SongDetail from './components/SongDetail'
import Scatter2D from './components/visualizations/Scatter2D'
import { fetchAllSongs, filterSongs, filterSimilarTo } from './api/client'
import './App.css'

// Chip shape:
//   { kind: 'query',   value: string,         label: string }
//   { kind: 'similar', value: number (songId), label: string }
//   { kind: 'genre',   value: string[] (slugs), label: string }
//
// Filters compose progressively: each chip narrows the current alive set,
// regardless of kind. Removing a chip re-runs the remaining chips from
// scratch so the result reflects the displayed constraints exactly.
// Genre chips are evaluated locally (every song already carries its genre
// from /api/songs) so they don't need a round-trip to the backend. Their
// value is a list of slugs UNION'd together (a song matches if its genre
// is in the list) — multiple slugs in one chip is the only sensible
// composition since AND'ing distinct genres always intersects to ∅.
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

  const [selectedSongId, setSelectedSongId] = useState(null)
  const [highlightedId, setHighlightedId] = useState(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState(null)
  const [message, setMessage] = useState(null)

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

  const displaySongs = activeIds
    ? allSongs
        .filter(s => activeIds.has(s.id))
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

  // Apply one chip on top of the current alive set; returns a FilterResponse-
  // shaped object. Genre chips are pure metadata filters and run locally
  // (every song dict already has a `genre` field from /api/songs); the other
  // kinds round-trip to the backend.
  async function applyChip(chip, aliveIds) {
    if (chip.kind === 'similar') {
      return filterSimilarTo(chip.value, aliveIds)
    }
    if (chip.kind === 'genre') {
      const aliveSet = aliveIds == null ? null : new Set(aliveIds)
      // Tolerate the legacy ``value: string`` shape just in case a stale chip
      // is in flight while this lands; new chips always carry ``string[]``.
      const wanted = new Set(Array.isArray(chip.value) ? chip.value : [chip.value])
      const survivors = allSongs
        .filter(s => (aliveSet == null || aliveSet.has(s.id)) && wanted.has(s.genre))
        // Score 1.0 for every survivor — a genre chip is a hard yes/no
        // filter, so it doesn't add ranking signal beyond "in the bucket".
        .map(s => ({ ...s, score: 1 }))
      return { songs: survivors, projections_2d: [], total_remaining: survivors.length, message: null }
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

  // Build the visible label for a genre chip from its current slug list.
  function genreChipLabel(values) {
    return values.join(' + ')
  }

  // Plain click  ⇒ replace the genre filter with just this slug; if it was
  //                 already the single active slug, toggle the chip off.
  // Ctrl/⌘-click ⇒ toggle this slug in the existing set; if the set becomes
  //                 empty after the toggle, remove the chip entirely.
  async function handleAddGenreChip(slug, additive = false) {
    if (!slug) return
    const existingIdx = chips.findIndex(c => c.kind === 'genre')
    const current = existingIdx === -1
      ? []
      : (Array.isArray(chips[existingIdx].value)
          ? chips[existingIdx].value
          : [chips[existingIdx].value])

    let nextValues
    if (additive) {
      nextValues = current.includes(slug)
        ? current.filter(g => g !== slug)
        : [...current, slug]
    } else {
      nextValues = current.length === 1 && current[0] === slug ? [] : [slug]
    }

    if (nextValues.length === 0) {
      if (existingIdx !== -1) await handleRemoveChip(existingIdx)
      return
    }

    const newChip = { kind: 'genre', value: nextValues, label: genreChipLabel(nextValues) }
    const newChips = existingIdx === -1
      ? [...chips, newChip]
      : chips.map((c, i) => (i === existingIdx ? newChip : c))
    await runChipUpdate(newChips)
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
      // Combined score = mean of per-chip scores from RANKING chips only.
      // Genre chips are binary metadata filters (score=1 for every survivor)
      // so including them would pull every score toward 1 and flatten the
      // ranking. If all chips are genre, fall back to 1.0 so survivors keep
      // a consistent (uniform) score.
      const combined = {}
      const rankingIdx = newChips
        .map((c, i) => (c.kind === 'genre' ? -1 : i))
        .filter(i => i >= 0)
      for (const id of alive) {
        if (rankingIdx.length === 0) { combined[id] = 1; continue }
        let sum = 0
        for (const i of rankingIdx) sum += (perChipMaps[i][id] ?? 0)
        combined[id] = sum / rankingIdx.length
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

  const activeCount = activeIds ? activeIds.size : allSongs.length

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
              {activeIds ? (
                <><strong>{activeCount}</strong> / {allSongs.length} cançons</>
              ) : (
                <><strong>{allSongs.length}</strong> cançons al mapa</>
              )}
            </span>
          </div>

          <div className="viz-area">
            <Scatter2D
              points={baseProj2d}
              activeIds={activeIds}
              focalId={focalSimilarId}
              highlightedId={highlightedId}
              onPointHover={setHighlightedId}
              onPointOpenDetail={handleOpenDetail}
              onAddGenreChip={handleAddGenreChip}
              activeGenres={
                (() => {
                  const v = chips.find(c => c.kind === 'genre')?.value
                  if (v == null) return []
                  return Array.isArray(v) ? v : [v]
                })()
              }
            />
          </div>
        </section>
      </main>

      <SongDetail
        songId={selectedSongId}
        onClose={() => setSelectedSongId(null)}
        onFilterSimilar={handleAddSimilarChip}
      />
    </div>
  )
}
