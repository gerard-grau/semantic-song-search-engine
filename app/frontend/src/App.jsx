import { useState, useCallback, useRef } from 'react'
import useTheme from './hooks/useTheme'
import WelcomePage from './components/WelcomePage'
import CercadorPage from './components/CercadorPage'
import ThemeToggle from './components/ThemeToggle'
import FilterBar from './components/FilterBar'
import TopResults from './components/TopResults'
import SongDetail from './components/SongDetail'
import VizSelector from './components/VizSelector'
import Scatter2D from './components/visualizations/Scatter2D'
import Scatter3D from './components/visualizations/Scatter3D'
import Navigation2D from './components/visualizations/Navigation2D'
import { fetchAllSongs, filterSongs, fetchNeighbors } from './api/client'
import './App.css'

export default function App() {
  const { theme, toggleTheme } = useTheme()

  // Page state
  const [page, setPage] = useState('welcome')

  // Data state — allSongs & baseProj are the permanent full dataset
  const [allSongs, setAllSongs] = useState([])
  const [baseProj2d, setBaseProj2d] = useState([])
  const [baseProj3d, setBaseProj3d] = useState([])

  // Active highlights — which songs are "active" (filtered or neighbors)
  // null means all songs are active (no filter applied)
  const [activeIds, setActiveIds] = useState(null)
  // Score map: songId → score (0-1) for sizing active songs
  const [scoreMap, setScoreMap] = useState({})

  // Chip-based filters
  const [chips, setChips] = useState([])

  // Similarity mode: clicked song
  const [similarToId, setSimilarToId] = useState(null)
  const [similarToTitle, setSimilarToTitle] = useState(null)

  // UI state
  const [vizMode, setVizMode] = useState('2D')
  const [selectedSongId, setSelectedSongId] = useState(null)
  const [highlightedId, setHighlightedId] = useState(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState(null)
  const [message, setMessage] = useState(null)

  // Track current alive IDs for progressive filtering
  const aliveIdsRef = useRef(null)

  // Songs to show in left panel (active ones, sorted by score)
  const displaySongs = activeIds
    ? allSongs
        .filter(s => activeIds.has(s.id))
        .map(s => ({ ...s, score: scoreMap[s.id] ?? 0 }))
        .sort((a, b) => b.score - a.score)
    : allSongs

  // ── Load all songs (initial + reset) ──
  const loadAll = useCallback(async () => {
    setIsLoading(true)
    setError(null)
    try {
      const data = await fetchAllSongs()
      setAllSongs(data.songs)
      setBaseProj2d(data.projections_2d)
      setBaseProj3d(data.projections_3d)
      setActiveIds(null)
      setScoreMap({})
      setChips([])
      setSimilarToId(null)
      setSimilarToTitle(null)
      setMessage(null)
      aliveIdsRef.current = null
    } catch (err) {
      setError("No s'ha pogut connectar amb el servidor.")
      console.error(err)
    } finally {
      setIsLoading(false)
    }
  }, [])

  // ── Enter main app from welcome ──
  async function handleEnter() {
    await loadAll()
    setPage('main')
  }

  // ── Add a chip filter ──
  async function handleAddChip(q) {
    if (!q.trim()) return
    setIsLoading(true)
    setError(null)
    // Exit similarity mode when filtering
    setSimilarToId(null)
    setSimilarToTitle(null)
    try {
      const currentAlive = aliveIdsRef.current
      const data = await filterSongs(q, currentAlive)
      const newAliveIds = data.songs.map(s => s.id)
      aliveIdsRef.current = newAliveIds
      setActiveIds(new Set(newAliveIds))
      const newScoreMap = {}
      data.songs.forEach(s => { newScoreMap[s.id] = s.score ?? 0 })
      setScoreMap(newScoreMap)
      setChips(prev => [...prev, q])
      setMessage(data.message)
    } catch (err) {
      setError('Error en la cerca.')
      console.error(err)
    } finally {
      setIsLoading(false)
    }
  }

  // ── Remove a chip (re-apply remaining chips from scratch) ──
  async function handleRemoveChip(index) {
    const newChips = chips.filter((_, i) => i !== index)
    setChips(newChips)

    if (newChips.length === 0) {
      // No filters left — show everything
      setActiveIds(null)
      setScoreMap({})
      aliveIdsRef.current = null
      setMessage(null)
      return
    }

    // Re-apply all remaining chips from scratch
    setIsLoading(true)
    setError(null)
    try {
      let currentAlive = null
      let lastData = null
      for (const chip of newChips) {
        lastData = await filterSongs(chip, currentAlive)
        currentAlive = lastData.songs.map(s => s.id)
      }
      aliveIdsRef.current = currentAlive
      setActiveIds(new Set(currentAlive))
      const newScoreMap = {}
      lastData.songs.forEach(s => { newScoreMap[s.id] = s.score ?? 0 })
      setScoreMap(newScoreMap)
      setMessage(lastData.message)
    } catch (err) {
      setError('Error actualitzant filtres.')
      console.error(err)
    } finally {
      setIsLoading(false)
    }
  }

  // ── Reset everything ──
  function handleReset() {
    setActiveIds(null)
    setScoreMap({})
    setChips([])
    setSimilarToId(null)
    setSimilarToTitle(null)
    setMessage(null)
    aliveIdsRef.current = null
  }

  // ── Click a song in scatter → show similar songs (respecting chip filters) ──
  async function handleSongExplore(songId) {
    setIsLoading(true)
    setError(null)
    setMessage(null)

    const song = allSongs.find(s => s.id === songId)
    setSimilarToId(songId)
    setSimilarToTitle(song?.title ?? null)

    try {
      const data = await fetchNeighbors(songId, { n: 20 })
      let neighborIds = new Set(data.songs.map(s => s.id))
      neighborIds.add(songId)

      // If chip filters are active, intersect neighbors with alive IDs
      const chipAlive = aliveIdsRef.current
      if (chipAlive) {
        const chipSet = new Set(chipAlive)
        neighborIds = new Set([...neighborIds].filter(id => chipSet.has(id)))
        neighborIds.add(songId) // always keep focal
      }

      setActiveIds(neighborIds)

      // Build score map from neighbor distances
      const newScoreMap = {}
      data.songs.forEach(s => {
        newScoreMap[s.id] = s.score ?? 0
      })
      newScoreMap[songId] = 1
      setScoreMap(newScoreMap)
    } catch (err) {
      setError('Error carregant cançons similars.')
      console.error(err)
    } finally {
      setIsLoading(false)
    }
  }

  // ── Exit similarity mode ──
  function handleExitSimilar() {
    setSimilarToId(null)
    setSimilarToTitle(null)
    // If we had chip filters, restore them
    if (chips.length > 0 && aliveIdsRef.current) {
      setActiveIds(new Set(aliveIdsRef.current))
    } else {
      setActiveIds(null)
      setScoreMap({})
    }
  }

  // ── Open song detail modal ──
  function handleOpenDetail(songId) {
    setSelectedSongId(songId)
  }

  // ── Render ──
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
      {/* Header */}
      <header className="app-header">
        <div className="header-left">
          <button className="header-home-btn" onClick={() => setPage('welcome')}>← Inici</button>
          <h1 className="header-title">Descobridor de Cançons</h1>
        </div>
        <ThemeToggle theme={theme} onToggle={toggleTheme} />
      </header>

      {error && <div className="error-banner">{error}</div>}

      {/* Main */}
      <main className="app-main">
        <section className="panel-left">
          <TopResults
            songs={displaySongs}
            message={message}
            query={chips.length > 0 ? chips[chips.length - 1] : ''}
            onSongHover={setHighlightedId}
            onSongClick={handleOpenDetail}
            highlightedId={highlightedId}
          />
        </section>

        <section className="panel-right">
          {/* Filter bar with chips */}
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
            <VizSelector mode={vizMode} onChange={setVizMode} />
            <span className="viz-count">
              {similarToId
                ? `${activeCount} cançons similars`
                : activeIds
                  ? `${activeCount} / ${allSongs.length} cançons`
                  : `${allSongs.length} cançons`}
            </span>
          </div>

          {/* Similarity mode bar */}
          {similarToId && (
            <div className="viz-bar viz-bar--explore">
              <button className="explore-back-btn" onClick={handleExitSimilar}>← Enrere</button>
              <span className="explore-label">
                Similars a: <strong>{similarToTitle}</strong>
              </span>
              <span className="explore-hint">Clica una altra cançó per explorar-ne les similars</span>
            </div>
          )}

          <div className="viz-area">
            {vizMode === '2D' && (
              <Scatter2D
                points={baseProj2d}
                activeIds={activeIds}
                scoreMap={scoreMap}
                focalId={similarToId}
                highlightedId={highlightedId}
                onPointHover={setHighlightedId}
                onPointClick={handleSongExplore}
                onPointDoubleClick={handleOpenDetail}
              />
            )}
            {vizMode === '3D' && (
              <Scatter3D
                points={baseProj3d}
                highlightedId={highlightedId}
                onPointHover={setHighlightedId}
                onPointClick={handleOpenDetail}
                topIds={activeIds ? [...activeIds] : []}
                faded={false}
                scores={displaySongs}
              />
            )}
            {vizMode === 'nav' && (
              <Navigation2D
                points={baseProj2d}
                highlightedId={highlightedId}
                onPointHover={setHighlightedId}
                onPointClick={handleOpenDetail}
                topIds={activeIds ? [...activeIds] : []}
                faded={false}
                scores={displaySongs}
              />
            )}
          </div>
        </section>
      </main>

      {/* Song detail popup */}
      <SongDetail songId={selectedSongId} onClose={() => setSelectedSongId(null)} />
    </div>
  )
}
