import { useState, useCallback, useRef } from 'react'
import useTheme from './hooks/useTheme'
import WelcomePage from './components/WelcomePage'
import CercadorPage from './components/CercadorPage'
import ThemeToggle from './components/ThemeToggle'
import FilterBar from './components/FilterBar'
import TopResults from './components/TopResults'
import SongDetail from './components/SongDetail'
import Scatter2D from './components/visualizations/Scatter2D'
import { fetchAllSongs, filterSongs, fetchNeighbors } from './api/client'
import './App.css'

export default function App() {
  const { theme, toggleTheme } = useTheme()

  const [page, setPage] = useState('welcome')

  const [allSongs, setAllSongs] = useState([])
  const [baseProj2d, setBaseProj2d] = useState([])

  // null = no filter applied (everything is active).
  const [activeIds, setActiveIds] = useState(null)
  const [scoreMap, setScoreMap] = useState({})

  const [chips, setChips] = useState([])

  const [similarToId, setSimilarToId] = useState(null)
  const [similarToTitle, setSimilarToTitle] = useState(null)

  const [selectedSongId, setSelectedSongId] = useState(null)
  const [highlightedId, setHighlightedId] = useState(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState(null)
  const [message, setMessage] = useState(null)

  const aliveIdsRef = useRef(null)

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

  async function handleEnter() {
    await loadAll()
    setPage('main')
  }

  async function handleAddChip(q) {
    if (!q.trim()) return
    setIsLoading(true)
    setError(null)
    setSimilarToId(null)
    setSimilarToTitle(null)
    try {
      const data = await filterSongs(q, aliveIdsRef.current)
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

  async function handleRemoveChip(index) {
    const newChips = chips.filter((_, i) => i !== index)
    setChips(newChips)

    if (newChips.length === 0) {
      setActiveIds(null)
      setScoreMap({})
      aliveIdsRef.current = null
      setMessage(null)
      return
    }

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

  function handleReset() {
    setActiveIds(null)
    setScoreMap({})
    setChips([])
    setSimilarToId(null)
    setSimilarToTitle(null)
    setMessage(null)
    aliveIdsRef.current = null
  }

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

      const chipAlive = aliveIdsRef.current
      if (chipAlive) {
        const chipSet = new Set(chipAlive)
        neighborIds = new Set([...neighborIds].filter(id => chipSet.has(id)))
        neighborIds.add(songId)
      }

      setActiveIds(neighborIds)

      const newScoreMap = {}
      data.songs.forEach(s => { newScoreMap[s.id] = s.score ?? 0 })
      newScoreMap[songId] = 1
      setScoreMap(newScoreMap)
    } catch (err) {
      setError('Error carregant cançons similars.')
      console.error(err)
    } finally {
      setIsLoading(false)
    }
  }

  function handleExitSimilar() {
    setSimilarToId(null)
    setSimilarToTitle(null)
    if (chips.length > 0 && aliveIdsRef.current) {
      setActiveIds(new Set(aliveIdsRef.current))
    } else {
      setActiveIds(null)
      setScoreMap({})
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
            query={chips.length > 0 ? chips[chips.length - 1] : ''}
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
              {similarToId ? (
                <><strong>{activeCount}</strong> cançons similars</>
              ) : activeIds ? (
                <><strong>{activeCount}</strong> / {allSongs.length} cançons</>
              ) : (
                <><strong>{allSongs.length}</strong> cançons al mapa</>
              )}
            </span>
          </div>

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
          </div>
        </section>
      </main>

      <SongDetail songId={selectedSongId} onClose={() => setSelectedSongId(null)} />
    </div>
  )
}
