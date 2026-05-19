import { useState, useEffect, useRef } from 'react'
import { fetchSongDetail } from '../api/client'
import { GENRE_COLORS } from './visualizations/genreColors'

// Source lyrics use ASCII ' and " which render as ugly ticks in the serif
// display font. Swap to typographic curly forms for display only; the data
// on disk is unchanged.
function prettifyTypography(s) {
  if (!s) return s
  return String(s)
    .replace(/(^|[\s(\[{])'/g, '$1‘')   // opening single
    .replace(/'/g, '’')                  // remaining → closing single
    .replace(/(^|[\s(\[{])"/g, '$1“')   // opening double
    .replace(/"/g, '”')                  // remaining → closing double
}

export default function SongDetail({ songId, onClose, onFilterSimilar, onAddQueryFilter }) {
  const [song, setSong] = useState(null)
  const [loading, setLoading] = useState(true)
  const [selection, setSelection] = useState(null) // { text, x, y }
  const contentRef = useRef(null)

  useEffect(() => {
    if (!songId) return
    setLoading(true)
    setSelection(null)
    fetchSongDetail(songId)
      .then(data => setSong(data))
      .catch(err => console.error(err))
      .finally(() => setLoading(false))
  }, [songId])

  // Read the current text selection and, if it's inside the selectable
  // region, anchor a floating "add as filter" action near the cursor.
  function handleSelectionChange() {
    const sel = window.getSelection?.()
    if (!sel || sel.isCollapsed) { setSelection(null); return }
    const text = sel.toString().trim()
    if (!text || text.length > 80) { setSelection(null); return }
    const anchor = sel.anchorNode
    const root = contentRef.current
    if (!root || !anchor || !root.contains(anchor.nodeType === 1 ? anchor : anchor.parentNode)) {
      setSelection(null); return
    }
    const range = sel.getRangeAt(0)
    const rect = range.getBoundingClientRect()
    if (rect.width === 0 && rect.height === 0) { setSelection(null); return }
    setSelection({
      text,
      // Anchor the chip just below the selection, centred horizontally.
      x: rect.left + rect.width / 2,
      y: rect.bottom + 8,
    })
  }

  if (!songId) return null

  function handleSimilar() {
    if (!song || !onFilterSimilar) return
    onFilterSimilar(song.id, song.title)
    onClose?.()
  }

  function handleAddSelectionAsFilter() {
    if (!selection || !onAddQueryFilter) return
    // Normalise back to ASCII apostrophes so the query matches the encoder's
    // tokenisation of the source text.
    const q = selection.text
      .replace(/[‘’]/g, "'")
      .replace(/[“”]/g, '"')
    onAddQueryFilter(q)
    setSelection(null)
    window.getSelection?.()?.removeAllRanges()
    onClose?.()
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal-content"
        ref={contentRef}
        onClick={e => e.stopPropagation()}
        onMouseUp={handleSelectionChange}
        onKeyUp={handleSelectionChange}
      >
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
                <h2 className="modal-title modal-selectable">{prettifyTypography(song.title)}</h2>
                <span className="modal-artist modal-selectable">{song.artist}</span>
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
              {song.album && String(song.album).split('|').map((s) => s.trim()).filter(Boolean).map((name) => (
                <span key={name}>{name}</span>
              ))}
              {song.year > 0 && <span>{song.year}</span>}
              {song.duration && <span>{song.duration}</span>}
              {song.language && <span>{song.language}</span>}
            </div>

            <div className="modal-lyrics">
              <h3>Lletra</h3>
              <p className="modal-lyrics-hint">
                Selecciona qualsevol fragment (o fes doble clic en una paraula) per afegir-lo com a filtre.
              </p>
              <pre className="modal-selectable">{prettifyTypography(song.full_lyrics)}</pre>
            </div>
          </>
        ) : (
          <div className="modal-loading">No s'ha trobat la cançó.</div>
        )}
      </div>

      {selection && onAddQueryFilter && (
        <button
          type="button"
          className="selection-action"
          style={{ left: selection.x, top: selection.y }}
          onClick={(e) => { e.stopPropagation(); handleAddSelectionAsFilter() }}
          onMouseDown={(e) => e.preventDefault()}
        >
          <span aria-hidden="true">+</span>
          Afegir «{selection.text.length > 24 ? selection.text.slice(0, 24) + '…' : selection.text}» com a filtre
        </button>
      )}
    </div>
  )
}
