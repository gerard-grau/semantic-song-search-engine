import { useState } from 'react'
import { genreColor } from './visualizations/genreColors'

/**
 * Showcase view — displayed when ≤5 songs remain after filtering.
 * Shows each song as a large, detailed card with score bar,
 * lyrics snippet, and animated entrance.
 */
export default function SongShowcase({ songs, onSongClick }) {
  const [hoveredId, setHoveredId] = useState(null)

  if (!songs.length) return null

  const maxScore = Math.max(...songs.map(s => s.score), 0.01)

  return (
    <div className="showcase">
      <div className="showcase-header">
        <h2 className="showcase-title">
          {songs.length === 1 ? 'La teva cançó!' : `Les teves ${songs.length} cançons finalistes`}
        </h2>
        <p className="showcase-subtitle">
          {songs.length === 1
            ? 'Hem trobat la cançó perfecta per tu.'
            : 'Aquestes cançons han sobreviscut tots els filtres.'}
        </p>
      </div>

      <div className="showcase-grid">
        {songs.map((song, i) => {
          const color = genreColor(song.genre)
          const pct = Math.round((song.score / maxScore) * 100)
          const isHovered = hoveredId === song.id

          return (
            <div
              key={song.id}
              className={`showcase-card ${isHovered ? 'showcase-card--hover' : ''}`}
              style={{
                '--card-accent': color,
                animationDelay: `${i * 0.12}s`,
              }}
              onMouseEnter={() => setHoveredId(song.id)}
              onMouseLeave={() => setHoveredId(null)}
              onClick={() => onSongClick(song.id)}
            >
              {/* Rank medal */}
              <div className="showcase-rank" style={{ background: color }}>
                {i + 1}
              </div>

              {/* Score ring */}
              <div className="showcase-score-ring">
                <svg viewBox="0 0 36 36" className="showcase-ring-svg">
                  <path
                    className="showcase-ring-bg"
                    d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                  />
                  <path
                    className="showcase-ring-fill"
                    strokeDasharray={`${pct}, 100`}
                    style={{ stroke: color }}
                    d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                  />
                </svg>
                <span className="showcase-ring-text">{pct}%</span>
              </div>

              <div className="showcase-info">
                <h3 className="showcase-song-title">{song.title}</h3>
                <p className="showcase-artist">{song.artist}</p>

                <div className="showcase-meta">
                  <span className="showcase-genre-tag" style={{ background: color }}>
                    {song.genre}
                  </span>
                  {song.year && <span className="showcase-year">{song.year}</span>}
                  {song.album && <span className="showcase-album">{song.album}</span>}
                </div>

                {song.lyrics_snippet && (
                  <p className="showcase-lyrics">«{song.lyrics_snippet}»</p>
                )}
              </div>

              {/* Glow border on hover */}
              <div className="showcase-glow" style={{ '--glow-color': color }} />
            </div>
          )
        })}
      </div>
    </div>
  )
}
