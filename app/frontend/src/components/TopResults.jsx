import { useState } from 'react'
import { GENRE_COLORS } from './visualizations/genreColors'

export default function TopResults({ songs, message, query, onSongHover, onSongClick, highlightedId }) {
  const [visibleCount, setVisibleCount] = useState(12)

  const visible = songs.slice(0, visibleCount)
  const hasMore = songs.length > visibleCount

  function handleShowMore() {
    setVisibleCount(prev => prev + 12)
  }

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

      {message && <div className="results-message">{message}</div>}

      <ol className="results-list">
        {visible.map((song, idx) => {
          const color = GENRE_COLORS[song.genre] || '#8B8B95'
          const isActive = highlightedId === song.id
          const scorePct = song.score != null ? Math.round(song.score * 100) : null
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
                <div className="result-score-wrap" aria-label={`Similitud ${scorePct}%`}>
                  <div className="result-score-ring" style={{ '--pct': scorePct }}>
                    <span className="result-score-label">{scorePct}</span>
                  </div>
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
    </div>
  )
}
