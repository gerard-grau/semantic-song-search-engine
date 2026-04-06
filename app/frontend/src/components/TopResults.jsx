import { useState } from 'react'
import { GENRE_COLORS } from './visualizations/genreColors'

export default function TopResults({ songs, message, query, onSongHover, onSongClick, highlightedId }) {
  const [visibleCount, setVisibleCount] = useState(10)

  // Reset visible count when songs list changes
  const visible = songs.slice(0, visibleCount)
  const hasMore = songs.length > visibleCount

  function handleShowMore() {
    setVisibleCount(prev => prev + 10)
  }

  return (
    <div className="top-results">
      <h2 className="results-title">
        {query ? `Resultats per "${query}"` : 'Totes les cançons'}
        <span className="results-badge">{songs.length}</span>
      </h2>

      {message && <div className="results-message">{message}</div>}

      <div className="results-list">
        {visible.map((song, idx) => (
          <div
            key={song.id}
            className={`result-card ${highlightedId === song.id ? 'result-card--active' : ''}`}
            onMouseEnter={() => onSongHover(song.id)}
            onMouseLeave={() => onSongHover(null)}
            onClick={() => onSongClick(song.id)}
          >
            <div className="result-rank">{idx + 1}</div>

            <div className="result-body">
              <div className="result-header">
                <span className="result-title">{song.title}</span>
                <span
                  className="result-genre-tag"
                  style={{ background: GENRE_COLORS[song.genre] || '#888' }}
                >
                  {song.genre}
                </span>
              </div>
              <div className="result-artist">{song.artist}</div>
              <div className="result-meta">{song.album} · {song.year}</div>
              <div className="result-lyrics">{song.lyrics_snippet}</div>
            </div>

            {query && (
              <div className="result-score-wrap">
                <div className="result-score-bar">
                  <div
                    className="result-score-fill"
                    style={{ height: `${song.score * 100}%` }}
                  />
                </div>
                <span className="result-score-label">{(song.score * 100).toFixed(0)}%</span>
              </div>
            )}
          </div>
        ))}

        {hasMore && (
          <button className="show-more-btn" onClick={handleShowMore}>
            Veure més ({songs.length - visibleCount} restants)
          </button>
        )}
      </div>

      {!hasMore && songs.length > 10 && (
        <p className="results-footnote">Mostrant totes les {songs.length} cançons</p>
      )}
    </div>
  )
}
