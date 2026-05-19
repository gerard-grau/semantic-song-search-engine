import { useEffect, useRef, useState } from 'react'
import { GENRE_COLORS } from './visualizations/genreColors'

// Map a similarity percentage to a colour: red (0%) → orange → dark green
// (100%). Independent of genre so the eye reads "how close a match is
// this?" rather than "what genre is this?".
function scoreColor(pct) {
  const p = Math.max(0, Math.min(100, pct)) / 100
  const hue   = 0 + p * 130          // 0=red → 130=deep green
  const light = 48 - p * 18          // 48% → 30% (darker at high scores)
  return `hsl(${Math.round(hue)}, 70%, ${Math.round(light)}%)`
}

// CSV-escape per RFC 4180: wrap in quotes and double any internal quote
// whenever the value contains a comma, quote, or newline.
function csvCell(v) {
  if (v == null) return ''
  const s = String(v)
  return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
}

function exportSongsCsv(rows, filename) {
  const headers = ['rank', 'id', 'title', 'artist', 'album', 'year', 'genre', 'score']
  const lines = [headers.join(',')]
  rows.forEach((s, i) => {
    lines.push([
      i + 1,
      s.id,
      csvCell(s.title),
      csvCell(s.artist),
      csvCell(s.album || ''),
      s.year || '',
      csvCell(s.genre || ''),
      s.score != null ? s.score.toFixed(4) : '',
    ].join(','))
  })
  // BOM so Excel opens UTF-8 (accents, ç) correctly without the user
  // having to fiddle with import settings.
  const blob = new Blob(['﻿' + lines.join('\n')], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

export default function TopResults({
  songs, message, query,
  chips = [], chipScoreMaps = [],
  onSongHover, onSongClick, highlightedId,
}) {
  const [visibleCount, setVisibleCount] = useState(12)
  // Open breakdown: { songId, x, y } — viewport coords of the score
  // ring's centre-right edge. Null = closed.
  const [breakdown, setBreakdown] = useState(null)

  // Export menu state
  const [exportOpen, setExportOpen] = useState(false)
  const [customCount, setCustomCount] = useState('')
  const exportRef = useRef(null)

  const visible = songs.slice(0, visibleCount)
  const hasMore = songs.length > visibleCount

  function handleExport(n) {
    const count = Math.max(1, Math.min(songs.length, Math.floor(n)))
    const rows = songs.slice(0, count)
    const slug = (query || 'cataleg')
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-|-$/g, '')
      .slice(0, 40) || 'cataleg'
    exportSongsCsv(rows, `top-${count}-${slug}.csv`)
    setExportOpen(false)
    setCustomCount('')
  }

  function handleCustomSubmit(e) {
    e.preventDefault()
    const n = parseInt(customCount, 10)
    if (!Number.isFinite(n) || n <= 0) return
    handleExport(n)
  }

  // Close the export menu when clicking outside it.
  useEffect(() => {
    if (!exportOpen) return
    function onDown(e) {
      if (exportRef.current && !exportRef.current.contains(e.target)) {
        setExportOpen(false)
      }
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [exportOpen])

  function handleShowMore() {
    setVisibleCount(prev => prev + 12)
  }

  // Close the popover on any layout shift — scrolling the results panel
  // would otherwise leave it floating at stale coords.
  useEffect(() => {
    if (!breakdown) return
    const close = () => setBreakdown(null)
    window.addEventListener('scroll', close, true)
    window.addEventListener('resize', close)
    return () => {
      window.removeEventListener('scroll', close, true)
      window.removeEventListener('resize', close)
    }
  }, [breakdown])

  function openBreakdown(e, songId) {
    e.stopPropagation()
    if (chips.length < 2) return
    if (breakdown?.songId === songId) { setBreakdown(null); return }
    const rect = e.currentTarget.getBoundingClientRect()
    setBreakdown({
      songId,
      x: rect.right + 8,
      y: rect.top + rect.height / 2,
    })
  }

  function breakdownRows(songId) {
    return chips.map((chip, i) => ({
      key: i,
      label: chip.label || `chip ${i + 1}`,
      kind: chip.kind,
      score: chipScoreMaps[i]?.[songId] ?? null,
    }))
  }

  const breakdownSong = breakdown
    ? songs.find(s => s.id === breakdown.songId)
    : null

  return (
    <div className="top-results">
      <header className="results-head">
        <div className="results-head-titles">
          <span className="results-eyebrow">
            {query ? 'Resultats' : 'Catàleg'}
          </span>
          <h2 className="results-title">
            {query
              ? <>Per <em>«{query}»</em></>
              : <>Totes les <em>cançons</em></>}
          </h2>
        </div>
        <span className="results-badge">{songs.length}</span>
      </header>

      <div className="results-toolbar" ref={exportRef}>
        <button
          type="button"
          className="results-export-btn"
          onClick={() => setExportOpen(v => !v)}
          aria-expanded={exportOpen}
          disabled={songs.length === 0}
          title="Exporta els top resultats com a CSV"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M12 3v12M7 10l5 5 5-5M5 21h14" />
          </svg>
          Exportar
        </button>
        {exportOpen && (
          <div className="results-export-menu" role="dialog" aria-label="Exporta top resultats">
            <div className="results-export-head">Quants resultats?</div>
            <div className="results-export-presets">
              {[10, 50, 100].map(n => (
                <button
                  key={n}
                  type="button"
                  className="results-export-preset"
                  onClick={() => handleExport(n)}
                  disabled={n > songs.length}
                  title={n > songs.length ? `Només hi ha ${songs.length} resultats` : `Exporta el top ${n}`}
                >
                  Top {n}
                </button>
              ))}
            </div>
            <form className="results-export-custom" onSubmit={handleCustomSubmit}>
              <input
                type="number"
                min="1"
                max={songs.length}
                value={customCount}
                onChange={e => setCustomCount(e.target.value)}
                placeholder={`Núm. concret (1–${songs.length})`}
                className="results-export-input"
                autoFocus
              />
              <button
                type="submit"
                className="results-export-submit"
                disabled={!customCount || parseInt(customCount, 10) <= 0}
              >
                Exporta
              </button>
            </form>
            <div className="results-export-foot">
              Format CSV · {songs.length} disponibles
            </div>
          </div>
        )}
      </div>

      {message && <div className="results-message">{message}</div>}

      <ol className="results-list">
        {visible.map((song, idx) => {
          const color = GENRE_COLORS[song.genre] || '#8B8B95'
          const isActive = highlightedId === song.id
          const scorePct = song.score != null ? Math.round(song.score * 100) : null
          const ringColor = scorePct != null ? scoreColor(scorePct) : null
          const hasMultiChip = chips.length > 1
          return (
            <li
              key={song.id}
              className={`result-card${isActive ? ' result-card--active' : ''}`}
              onMouseEnter={() => onSongHover(song.id)}
              onMouseLeave={() => onSongHover(null)}
              onClick={() => onSongClick(song.id)}
              style={{ '--genre-color': color }}
            >
              <span className="result-stripe" aria-hidden="true" />

              <span className="result-rank">
                <span className="result-rank-num">{idx + 1}</span>
              </span>

              <div className="result-body">
                <div className="result-header">
                  <span className="result-title">{song.title}</span>
                  {song.genre && (
                    <span
                      className="result-genre-tag"
                      style={{ background: color }}
                    >
                      {song.genre}
                    </span>
                  )}
                </div>
                <div className="result-artist">{song.artist}</div>
                {(song.album || song.year) && (
                  <div className="result-meta">
                    {song.album}
                    {song.album && song.year ? ' · ' : ''}
                    {song.year || ''}
                  </div>
                )}
                {song.lyrics_snippet && (
                  <div className="result-lyrics">«{song.lyrics_snippet}»</div>
                )}
              </div>

              {query && scorePct != null && (
                <div
                  className={`result-score-wrap${hasMultiChip ? ' result-score-wrap--clickable' : ''}`}
                  aria-label={
                    hasMultiChip
                      ? `Similitud combinada ${scorePct}% (clica per veure el desglossament)`
                      : `Similitud ${scorePct}%`
                  }
                >
                  <button
                    type="button"
                    className="result-score-ring"
                    style={{ '--pct': scorePct, '--score-color': ringColor }}
                    onClick={(e) => openBreakdown(e, song.id)}
                    aria-expanded={breakdown?.songId === song.id}
                    disabled={!hasMultiChip}
                    title={hasMultiChip ? 'Veure puntuació per filtre' : `Similitud ${scorePct}%`}
                  >
                    <span className="result-score-label">{scorePct}</span>
                  </button>
                </div>
              )}
            </li>
          )
        })}

        {hasMore && (
          <button className="show-more-btn" onClick={handleShowMore}>
            Veure'n més
            <span className="show-more-count">+{Math.min(12, songs.length - visibleCount)}</span>
          </button>
        )}
      </ol>

      {!hasMore && songs.length > 12 && (
        <p className="results-footnote">Mostrant les {songs.length} cançons</p>
      )}

      {breakdown && breakdownSong && (
        <div
          className="result-score-breakdown"
          style={{
            position: 'fixed',
            left: breakdown.x,
            top: breakdown.y,
            transform: 'translateY(-50%)',
          }}
          onMouseDown={e => e.stopPropagation()}
          onClick={e => e.stopPropagation()}
          role="dialog"
        >
          <div className="result-score-breakdown-head">
            <span>Per filtre</span>
            <button
              type="button"
              className="result-score-breakdown-close"
              onClick={() => setBreakdown(null)}
              aria-label="Tanca"
            >×</button>
          </div>
          <div className="result-score-breakdown-song" title={breakdownSong.title}>
            {breakdownSong.title}
          </div>
          <ul className="result-score-breakdown-list">
            {breakdownRows(breakdown.songId).map(item => {
              const pct = item.score != null ? Math.round(item.score * 100) : null
              return (
                <li key={item.key} className="result-score-breakdown-row">
                  <span
                    className={`result-score-breakdown-chip result-score-breakdown-chip--${item.kind}`}
                    title={item.label}
                  >
                    {item.label}
                  </span>
                  <span
                    className="result-score-breakdown-val"
                    style={pct != null ? { color: scoreColor(pct) } : undefined}
                  >
                    {pct != null ? `${pct}%` : '—'}
                  </span>
                </li>
              )
            })}
            <li className="result-score-breakdown-row result-score-breakdown-row--total">
              <span className="result-score-breakdown-chip result-score-breakdown-chip--total">
                Mitjana
              </span>
              <span
                className="result-score-breakdown-val"
                style={breakdownSong.score != null
                  ? { color: scoreColor(Math.round(breakdownSong.score * 100)) }
                  : undefined}
              >
                {breakdownSong.score != null
                  ? `${Math.round(breakdownSong.score * 100)}%`
                  : '—'}
              </span>
            </li>
          </ul>
        </div>
      )}
    </div>
  )
}
