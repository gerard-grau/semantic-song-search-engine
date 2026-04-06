import { useState, useEffect } from 'react'
import { fetchSongDetail } from '../api/client'
import { GENRE_COLORS } from './visualizations/genreColors'

export default function SongDetail({ songId, onClose }) {
  const [song, setSong] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!songId) return
    setLoading(true)
    fetchSongDetail(songId)
      .then(data => setSong(data))
      .catch(err => console.error(err))
      .finally(() => setLoading(false))
  }, [songId])

  if (!songId) return null

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-content" onClick={e => e.stopPropagation()}>
        <button className="modal-close" onClick={onClose}>✕</button>

        {loading ? (
          <div className="modal-loading">Carregant...</div>
        ) : song ? (
          <>
            <div className="modal-header">
              <h2 className="modal-title">{song.title}</h2>
              <span className="modal-artist">{song.artist}</span>
            </div>

            <div className="modal-meta">
              <span className="modal-tag" style={{ background: GENRE_COLORS[song.genre] || '#888' }}>
                {song.genre}
              </span>
              <span>{song.album}</span>
              <span>{song.year}</span>
              {song.duration && <span>{song.duration}</span>}
              {song.language && <span>{song.language}</span>}
            </div>

            <div className="modal-lyrics">
              <h3>Lletra</h3>
              <pre>{song.full_lyrics}</pre>
            </div>

            {song.url && (
              <a href={song.url} target="_blank" rel="noopener noreferrer" className="modal-link">
                Veure a Viasona ↗
              </a>
            )}
          </>
        ) : (
          <div className="modal-loading">No s'ha trobat la cançó.</div>
        )}
      </div>
    </div>
  )
}
