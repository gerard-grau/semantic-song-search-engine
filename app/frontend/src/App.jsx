import { useState, useCallback, useRef } from 'react'
import useTheme from './hooks/useTheme'
import WelcomePage from './components/WelcomePage'
import ThemeToggle from './components/ThemeToggle'
import SearchBar from './components/SearchBar'
import TopResults from './components/TopResults'
import SongDetail from './components/SongDetail'
import SongShowcase from './components/SongShowcase'
import VizSelector from './components/VizSelector'
import Scatter2D from './components/visualizations/Scatter2D'
import Scatter3D from './components/visualizations/Scatter3D'
import Navigation2D from './components/visualizations/Navigation2D'
import { fetchAllSongs, filterSongs, fetchNeighbors } from './api/client'
import './App.css'

export default function App() {
  const { theme, toggleTheme } = useTheme()

  // Page state
  const [page, setPage] = useState('welcome') // 'welcome' | 'main'

  // Data state
  const [allSongs, setAllSongs] = useState([])
  const [songs, setSongs] = useState([])
  const [songIds, setSongIds] = useState(null) // current alive IDs (null = all)
  const [proj2d, setProj2d] = useState([])
  const [proj3d, setProj3d] = useState([])
  const [query, setQuery] = useState('')
  const [message, setMessage] = useState(null)

  // UI state
  const [vizMode, setVizMode] = useState('2D')
  const [selectedSongId, setSelectedSongId] = useState(null)
  const [highlightedId, setHighlightedId] = useState(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState(null)

  // Neighborhood exploration state
  const [isExploring, setIsExploring] = useState(false)
  const [focalId, setFocalId] = useState(null)
  const [exploredSongTitle, setExploredSongTitle] = useState(null)
  // Saved view to restore when pressing "back"
  const savedStateRef = useRef(null)

  const isShowcase = songs.length <= 5 && query !== '' && !isExploring
  const topIds = songs.slice(0, 10).map(s => s.id)

  // ── Load all songs (initial + reset) ──
  const loadAll = useCallback(async () => {
    setIsLoading(true)
    setError(null)
    try {
      const data = await fetchAllSongs()
      setAllSongs(data.songs)
      setSongs(data.songs)
      setSongIds(null)
      setProj2d(data.projections_2d)
      setProj3d(data.projections_3d)
      setQuery('')
      setMessage(null)
      setIsExploring(false)
      setFocalId(null)
      setExploredSongTitle(null)
      savedStateRef.current = null
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

  // ── Progressive filter ──
  async function handleSearch(q) {
    setIsLoading(true)
    setError(null)
    // Searching exits exploration mode
    setIsExploring(false)
    setFocalId(null)
    setExploredSongTitle(null)
    savedStateRef.current = null
    try {
      const data = await filterSongs(q, songIds)
      setSongs(data.songs)
      setSongIds(data.songs.map(s => s.id))
      setProj2d(data.projections_2d)
      setProj3d(data.projections_3d)
      setQuery(q)
      setMessage(data.message)
    } catch (err) {
      setError('Error en la cerca.')
      console.error(err)
    } finally {
      setIsLoading(false)
    }
  }

  // ── Reset ──
  function handleReset() {
    loadAll()
  }

  // ── Explore neighborhood of a song (2D scatter click) ──
  async function handleExplore(songId) {
    setIsLoading(true)
    setError(null)
    setMessage(null)

    // Save current state only on the first exploration step (not when traveling deeper)
    if (!isExploring) {
      savedStateRef.current = { songs, proj2d, songIds, query }
    }

    // Find title for display; search both current songs and full catalog
    const song = songs.find(s => s.id === songId) ?? allSongs.find(s => s.id === songId)
    setExploredSongTitle(song?.title ?? null)
    setFocalId(songId)
    setIsExploring(true)

    try {
      const data = await fetchNeighbors(songId, {
        // The current focal becomes "previous" in the next step
        previousSongId: isExploring ? focalId : null,
        // All current neighborhood IDs are offered as bridge candidates
        bridgeSongIds: songs.map(s => s.id),
        bridgeCount: 5,
        // Current projection positions → used for Procrustes alignment
        previousPositions: proj2d.map(p => ({ id: p.id, x: p.x, y: p.y })),
      })
      setSongs(data.songs)
      setSongIds(data.songs.map(s => s.id))
      setProj2d(data.projections_2d)
    } catch (err) {
      setError('Error carregant veïns.')
      console.error(err)
    } finally {
      setIsLoading(false)
    }
  }

  // ── Back from exploration to previous view ──
  function handleBack() {
    const saved = savedStateRef.current
    if (saved) {
      setSongs(saved.songs)
      setProj2d(saved.proj2d)
      setSongIds(saved.songIds)
      setQuery(saved.query)
    }
    setIsExploring(false)
    setFocalId(null)
    setExploredSongTitle(null)
    savedStateRef.current = null
  }

  // ── Render ──
  if (page === 'welcome') {
    return <WelcomePage onEnter={handleEnter} theme={theme} onToggleTheme={toggleTheme} isLoading={isLoading} />
  }

  const vizProps2D = {
    highlightedId,
    onPointHover: setHighlightedId,
    onPointClick: handleExplore,
    topIds,
    faded: false,
    scores: songs,
    centerOnId: focalId,
  }

  const vizPropsOther = {
    highlightedId,
    onPointHover: setHighlightedId,
    onPointClick: setSelectedSongId,
    topIds,
    faded: false,
    scores: songs,
  }

  return (
    <div className="app">
      {/* Header — title + theme toggle only */}
      <header className="app-header">
        <h1 className="header-title">Descobridor de Cançons</h1>
        <ThemeToggle theme={theme} onToggle={toggleTheme} />
      </header>

      {error && <div className="error-banner">{error}</div>}

      {/* Main */}
      <main className="app-main">
        <section className="panel-left">
          <TopResults
            songs={songs}
            message={message}
            query={query}
            onSongHover={setHighlightedId}
            onSongClick={setSelectedSongId}
            highlightedId={highlightedId}
          />
        </section>

        <section className="panel-right">
          {/* Search bar + viz selector bar */}
          <div className="viz-bar">
            <SearchBar onSearch={handleSearch} onReset={handleReset} isLoading={isLoading} />
          </div>
          <div className="viz-bar viz-bar--controls">
            <VizSelector mode={vizMode} onChange={setVizMode} />
            <span className="viz-count">
              {isExploring
                ? `${songs.length} cançons similars`
                : query
                  ? `${songs.length} cançons supervivents`
                  : `${songs.length} cançons`}
            </span>
          </div>

          {/* Exploration breadcrumb bar */}
          {isExploring && (
            <div className="viz-bar viz-bar--explore">
              <button className="explore-back-btn" onClick={handleBack}>← Enrere</button>
              <span className="explore-label">
                Veïns de: <strong>{exploredSongTitle}</strong>
              </span>
              <span className="explore-hint">Clica una cançó per explorar-ne els veïns</span>
            </div>
          )}

          <div className="viz-area">
            {isShowcase ? (
              <SongShowcase songs={songs} onSongClick={setSelectedSongId} />
            ) : (
              <>
                {vizMode === '2D' && <Scatter2D points={proj2d} {...vizProps2D} />}
                {vizMode === '3D' && <Scatter3D points={proj3d} {...vizPropsOther} />}
                {vizMode === 'nav' && <Navigation2D points={proj2d} {...vizPropsOther} />}
              </>
            )}
          </div>
        </section>
      </main>

      {/* Song detail popup */}
      <SongDetail songId={selectedSongId} onClose={() => setSelectedSongId(null)} />
    </div>
  )
}
