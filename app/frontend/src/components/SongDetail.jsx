import { useState, useEffect } from 'react'
import { fetchSongDetail } from '../api/client'
import { GENRE_COLORS } from './visualizations/genreColors'

export default function SongDetail({ songId, onClose, onFilterSimilar }) {
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

  function handleSimilar() {
    if (!song || !onFilterSimilar) return
    onFilterSimilar(song.id, song.title)
    onClose?.()
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-content" onClick={e => e.stopPropagation()}>
        <button className="modal-close" onClick={onClose} aria-label="Tancar">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round">
            <path d="M18 6 6 18M6 6l12 12" />
          </svg>
        </button>

        {loading ? (
          <div className="modal-loading">Carregant...</div>
        ) : song ? (
          <>
            <div className="modal-header">
              <div className="modal-header-text">
                <h2 className="modal-title">{song.title}</h2>
                <span className="modal-artist">{song.artist}</span>
              </div>
              <div className="modal-header-actions">
                {onFilterSimilar && (
                  <button
                    type="button"
                    className="modal-action modal-action--similar"
                    onClick={handleSimilar}
                    title="Filtra el mapa per cançons semblants a aquesta"
                  >
                    <span aria-hidden="true">≈</span>
                    Cerca similars
                  </button>
                )}
                {song.url && (
                  <a
                    href={song.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="modal-action modal-action--viasona"
                    title="Obre aquesta cançó a Viasona"
                  >
                    Veure a Viasona
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M7 17 17 7M9 7h8v8" />
                    </svg>
                  </a>
                )}
              </div>
            </div>

            <div className="modal-meta">
              {song.genre && (
                <span className="modal-tag" style={{ background: GENRE_COLORS[song.genre] || '#888' }}>
                  {song.genre}
                </span>
              )}
              {song.album && <span>{song.album}</span>}
              {song.year > 0 && <span>{song.year}</span>}
              {song.duration && <span>{song.duration}</span>}
              {song.language && <span>{song.language}</span>}
            </div>

            <div className="modal-lyrics">
              <h3>Lletra</h3>
              <pre>{song.full_lyrics}</pre>
            </div>
          </>
        ) : (
          <div className="modal-loading">No s'ha trobat la cançó.</div>
        )}
      </div>
    </div>
  )
}
