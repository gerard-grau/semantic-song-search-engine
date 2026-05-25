import { useState, useEffect, useMemo, useRef } from 'react'
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
//
// When a genre IS selected, the scatter's salience is recomputed *within*
// that genre (see ``genreAdjustedMap``): the same shape as the backend
// salience (min-max × discriminability) but over the in-genre survivors
// only, working off each song's ``rank`` (catalog norm_score ∈ [0, 1]).
// GENRE_DISCRIM_REF is the (max − median) rank gap at which a within-genre
// standout reaches full brightness; FLOOR mirrors config.py
// QUERY_DISCRIM_FLOOR so a genre where nothing stands out for the query
// stays at the same neutral level it had catalog-wide (no blind stretch).
const GENRE_DISCRIM_REF   = 0.12
const GENRE_DISCRIM_FLOOR = 0.5

export default function App() {
  const { theme, toggleTheme } = useTheme()

  const [page, setPage] = useState('welcome')

  const [allSongs, setAllSongs] = useState([])
  const [baseProj2d, setBaseProj2d] = useState([])

  // null = no filter applied (everything is active).
  const [activeIds, setActiveIds] = useState(null)
  // Combined per-song filter scores: `{ [id]: { sal, rank } }`.
  //   sal  — drives opacity / colour (dimmed when the query is uninformative)
  //   rank — drives point size (untouched by discriminability) so weak
  //          queries still show which songs are relatively best.
  // Empty object = no active chip filter; Scatter2D treats every point at
  // full salience/size in that case.
  const [filterMap, setFilterMap] = useState({})
  // One salience map per chip (for the right-panel score breakdown popover).
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
  // Promise that resolves once /api/songs has loaded. Kicked off on mount
  // so by the time the user clicks "Entrar al mapa" it has usually already
  // resolved — but if they're fast, `handleEnter` awaits it instead of
  // dropping them into an empty scatter.
  const prefetchPromiseRef = useRef(null)

  // The most recent "similar" chip's song id becomes the visualization's
  // focal (diamond) so the anchor of the current similarity filter stays
  // visible while other filters compose.
  const focalSimilarId = useMemo(() => {
    for (let i = chips.length - 1; i >= 0; i--) {
      if (chips[i].kind === 'similar') return chips[i].value
    }
    return null
  }, [chips])

  // Intersect chip-derived survivors with the genre legend selection.
  // Either dimension can be null/empty independently:
  //   - no chips, no genres  → finalActiveIds = null (everything is alive)
  //   - only chips           → finalActiveIds = activeIds
  //   - only genres          → finalActiveIds = songs whose genre is selected
  //   - both                 → intersection of the two
  const finalActiveIds = useMemo(() => {
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
  }, [activeIds, selectedGenres, allSongs])

  // Genre-local salience. With no genre selected — or before any chip has
  // produced scores — this is just ``filterMap`` (catalog-wide, as before).
  // With genre(s) selected, every surviving song's salience / rank is
  // recomputed over the in-genre survivors only, so a song that stands out
  // *within* its genre brightens even if it's mediocre catalog-wide, while
  // a genre where nothing stands out for the query doesn't change at all.
  const genreAdjustedMap = useMemo(() => {
    if (selectedGenres.length === 0 || chips.length === 0 || !finalActiveIds) {
      return filterMap
    }
    const ids = [...finalActiveIds]
    if (ids.length === 0) return filterMap
    const ranks = ids.map(id => filterMap[id]?.rank ?? 0)
    let rMin = Infinity, rMax = -Infinity
    for (const r of ranks) {
      if (r < rMin) rMin = r
      if (r > rMax) rMax = r
    }
    const spread = rMax - rMin
    // Robust "does anything stand out?" contrast: top minus median. A lone
    // standout lifts the max while the median stays put (→ it brightens);
    // a uniform genre keeps contrast ≈ 0, so discriminability collapses to
    // the FLOOR and the view matches its catalog-wide appearance.
    const sorted = [...ranks].sort((a, b) => a - b)
    const mid = sorted.length >> 1
    const median = sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2
    const discrim = Math.min(1, Math.max(GENRE_DISCRIM_FLOOR, Math.max(0, rMax - median) / GENRE_DISCRIM_REF))
    const out = {}
    for (let i = 0; i < ids.length; i++) {
      const norm = spread > 1e-6 ? (ranks[i] - rMin) / spread : 0.5
      out[ids[i]] = { sal: norm * discrim, rank: norm }
    }
    return out
  }, [selectedGenres, chips.length, finalActiveIds, filterMap])

  // The right-panel list shows the ABSOLUTE match % (catalog-wide salience
  // from `filterMap`) and sorts by it — never the genre-local value. The
  // within-genre recompute (`genreAdjustedMap`) drives ONLY the scatter's
  // opacity / size, so the reported % stays a true catalog-wide similarity.
  const displaySongs = useMemo(() => {
    if (!finalActiveIds) return allSongs
    return allSongs
      .filter(s => finalActiveIds.has(s.id))
      .map(s => ({ ...s, score: filterMap[s.id]?.sal ?? 0 }))
      .sort((a, b) => b.score - a.score)
  }, [finalActiveIds, allSongs, filterMap])

  // Scatter2D consumes the score map directly (plain object, indexed by id).
  // `null` means "no chip filter active" so every visible point renders
  // at full salience / size — the genre legend, if any, gates via
  // `activeIds` separately. When a genre IS selected we hand it the
  // genre-local map so opacity / size reflect within-genre ranking.
  const filterScores = chips.length === 0 ? null : genreAdjustedMap

  // Display count: "X cançons rellevants" — songs that read as actually
  // highlighted on the scatter (salience above STRONG_MATCH_THRESHOLD).
  // For chip-less / genre-only filtering, fall back to the legend's exact
  // subset size since every alive song is fully colored anyway.
  const STRONG_MATCH_THRESHOLD = 0.30
  const matchCount = useMemo(() => {
    if (!finalActiveIds) return allSongs.length
    if (chips.length === 0) return finalActiveIds.size
    let c = 0
    for (const id of finalActiveIds) {
      if ((filterMap[id]?.sal ?? 0) >= STRONG_MATCH_THRESHOLD) c++
    }
    return c
  }, [finalActiveIds, filterMap, chips.length, allSongs.length])

  // Prefetch the catalog as soon as the app mounts. The welcome page stays
  // fully interactive — we don't toggle `isLoading` here — so the user can
  // pick the cercador or read the page while /api/songs streams in.
  useEffect(() => {
    if (prefetchPromiseRef.current) return
    prefetchPromiseRef.current = fetchAllSongs()
      .then(data => {
        setAllSongs(data.songs)
        setBaseProj2d(data.projections_2d)
      })
      .catch(err => {
        prefetchPromiseRef.current = null  // allow a retry on next click
        setError("No s'ha pogut connectar amb el servidor.")
        console.error(err)
      })
  }, [])

  function resetFilters() {
    setActiveIds(null)
    setFilterMap({})
    setChipScoreMaps([])
    setChips([])
    setSelectedGenres([])
    setMessage(null)
    aliveIdsRef.current = null
  }

  async function handleEnter() {
    resetFilters()
    // If the user clicks before the background prefetch resolves, show the
    // loading state and await it; otherwise navigate instantly.
    if (allSongs.length === 0) {
      setIsLoading(true)
      try {
        await prefetchPromiseRef.current
      } finally {
        setIsLoading(false)
      }
    }
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
  // Returns the final alive set + per-chip salience maps + per-chip rank
  // maps. The per-chip salience maps feed the right-panel breakdown
  // popover; per-chip ranks are only used here to compute the combined
  // size driver and never enter React state.
  async function applyChipsFromScratch(orderedChips) {
    let alive = null
    const perChipSal = []
    const perChipRank = []
    let lastMessage = null
    for (const chip of orderedChips) {
      const data = await applyChip(chip, alive)
      const salMap = {}
      const rankMap = {}
      data.songs.forEach(s => {
        salMap[s.id]  = s.score ?? 0
        rankMap[s.id] = s.rank ?? s.score ?? 0
      })
      perChipSal.push(salMap)
      perChipRank.push(rankMap)
      alive = data.songs.map(s => s.id)
      lastMessage = data.message ?? null
    }
    return { alive, perChipSal, perChipRank, lastMessage }
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
      resetFilters()
      return
    }
    await runChipUpdate(newChips)
  }

  async function runChipUpdate(newChips) {
    setIsLoading(true)
    setError(null)
    try {
      const { alive, perChipSal, perChipRank, lastMessage } = await applyChipsFromScratch(newChips)
      aliveIdsRef.current = alive
      setActiveIds(new Set(alive))
      // Combined { sal, rank } per surviving song.
      //
      // rank — arithmetic mean across chips. Size keeps a smooth
      //   ordering across chips so the user can still read the relative
      //   ranking from point size even when colour collapses to grey.
      //
      // sal — drives colour. Two stages:
      //   1. Geometric mean across chips — punishes songs that score
      //      weakly on ANY chip (a low value drags the product down).
      //   2. At n≥2 only, max-normalise (top survivor → 1.0) and raise
      //      to a falloff power that grows with n. Without this, a
      //      uniform gamma dimmed even the top winner, leaving every
      //      multi-chip result reading as mid-grey. Now the relative
      //      winner stays fully saturated and runners-up fall off
      //      steeply: at n=2 a song at 80% of top's geom score lands
      //      at ≈0.51, at n=3 at ≈0.33, at n=4 at ≈0.21 — only the
      //      closest matches survive visually as the chips stack.
      //
      // At n=1, salience passes through unchanged (geom of one value =
      // identity, no max-norm) so the backend's discriminability-scaled
      // single-chip colouring the user calibrated against is preserved.
      const n = newChips.length || 1
      const falloffPower = 1 + 2 * (n - 1)   // 1 / 3 / 5 / 7 / …

      const geomMap = {}
      const rankMap = {}
      let maxGeom = 0
      for (const id of alive) {
        let prodSal = 1
        let sumRank = 0
        for (let i = 0; i < newChips.length; i++) {
          prodSal *= (perChipSal[i][id]  ?? 0)
          sumRank += (perChipRank[i][id] ?? 0)
        }
        const g = Math.pow(prodSal, 1 / n)
        geomMap[id] = g
        rankMap[id] = sumRank / n
        if (g > maxGeom) maxGeom = g
      }

      const useMaxNorm = n >= 2 && maxGeom > 1e-6
      const combined = {}
      for (const id of alive) {
        const g = geomMap[id]
        const sal = useMaxNorm
          ? Math.pow(g / maxGeom, falloffPower)
          : g
        combined[id] = { sal, rank: rankMap[id] }
      }
      setFilterMap(combined)
      setChipScoreMaps(perChipSal)
      setChips(newChips)
      setMessage(lastMessage)
    } catch (err) {
      setError('Error aplicant filtres.')
      console.error(err)
    } finally {
      setIsLoading(false)
    }
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
            <span className="header-help-btn-label">Ajuda</span>
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
              onReset={resetFilters}
              isLoading={isLoading}
            />
          </div>

          <div className="viz-bar viz-bar--controls">
            <span className="viz-count">
              {isFiltered ? (
                <><strong>{matchCount}</strong> {chips.length > 0 ? 'rellevants' : 'cançons'} / {allSongs.length}</>
              ) : (
                <><strong>{allSongs.length}</strong> cançons al mapa</>
              )}
            </span>
          </div>

          <div className="viz-area">
            <Scatter2D
              points={baseProj2d}
              activeIds={finalActiveIds}
              filterScores={filterScores}
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
        onAddQueryFilter={handleAddChip}
      />

      {showHelp && <HelpPage onClose={() => setShowHelp(false)} />}
    </div>
  )
}
