import { useRef, useEffect, useCallback } from 'react'
import { genreColor, GENRE_COLORS } from './genreColors'

/**
 * 2D Scatter — chip-driven salience visualization.
 *
 * Every point is rendered with visual properties (size, opacity, colour
 * blend, halo, outline) driven continuously by its salience score sv ∈ [0, 1]:
 *
 *   sv ≈ 0    →  small faded grey, no halo, no outline (clearly filtered out)
 *   sv ≈ 0.5  →  near-normal size, mostly colour, faint halo + outline
 *   sv ≈ 1    →  big saturated dot, full halo + outline (strong match)
 *
 * Two design choices to keep in mind:
 *
 * 1. The salience / rank gammas are linear (= 1.0) so the visual reads
 *    the score directly. Sharper curves (gamma > 1) bury vague matches;
 *    gentler curves (gamma < 1) make non-related songs look "in" for
 *    specific queries like "txarango". Linear is the honest middle.
 *
 * 2. HALO_ONSET and OUTLINE_ONSET are both tiny (0.05) so the halo and
 *    outline scale *continuously* from sv ≈ 0 to 1 — no threshold to
 *    cross, no "this dot has a black border, that one doesn't" jitter.
 *
 * Genre legend still hard-filters via `activeIds`: a song excluded by
 * the legend is forced to sv = rv = 0 regardless of its chip score.
 */
const SALIENCE_GAMMA = 1.0   // colour contrast curve. Linear keeps the
                             // mapping honest: sv reads the score
                             // directly so a bottom-tail song never
                             // gets lifted into the "highlighted" range.
const RANK_GAMMA     = 1.0   // same for size.
const GHOST_SIZE     = 0.7   // size multiplier at rank 0 (worst under
                             // filter / legend-excluded). Clearly
                             // smaller than NORMAL so the bottom of the
                             // distribution reads as faded.
const NORMAL_SIZE    = 1.15  // size multiplier with no filter active
const FILTER_TOP     = 1.65  // size multiplier at rank 1 under a filter.
                             // Big enough that a clear top match
                             // dominates the scatter visually.
const HALO_ONSET     = 0.05  // salience above which a halo starts. Kept
                             // tiny so the halo scales continuously
                             // (alpha = 0.20 × (sv − onset) / (1 − onset))
                             // instead of switching on at a threshold.
const OUTLINE_ONSET  = 0.05  // same idea for the dark outline — without
                             // this, songs whose sv sits just below
                             // 0.5 would lose the outline while songs
                             // just above kept it, looking jittery.

function lerp(a, b, t) { return a + (b - a) * t }

function parseHexColor(hex) {
  let h = hex.trim()
  if (h.startsWith('rgb')) {
    const m = h.match(/(\d+(\.\d+)?)/g)
    return m ? [Number(m[0]), Number(m[1]), Number(m[2])] : [128, 128, 128]
  }
  if (h.startsWith('#')) h = h.slice(1)
  if (h.length === 3) h = h.split('').map(c => c + c).join('')
  const n = parseInt(h, 16)
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255]
}

function lerpColor(a, b, t) {
  const [r1, g1, b1] = parseHexColor(a)
  const [r2, g2, b2] = parseHexColor(b)
  return `rgb(${Math.round(lerp(r1, r2, t))},${Math.round(lerp(g1, g2, t))},${Math.round(lerp(b1, b2, t))})`
}

export default function Scatter2D({
  points, activeIds, filterScores, focalId,
  highlightedId, onPointHover, onPointOpenDetail,
  // Legend doubles as the genre filter: clicking an item toggles a genre
  // chip in the parent's chip list. ``activeGenres`` is the list of slugs
  // currently in the genre chip (length 0 if no genre filter is active);
  // a legend item is highlighted iff its slug is in that list. Plain click
  // calls ``onAddGenreChip(slug, false)`` for single-select replace; ctrl-
  // or ⌘-click calls it with ``true`` to toggle the slug additively.
  onAddGenreChip, activeGenres = [],
}) {
  const canvasRef = useRef(null)
  const containerRef = useRef(null)
  const viewRef = useRef({ panX: 0, panY: 0, zoom: 1 })
  const baseTransformRef = useRef({ scale: 1, offsetX: 0, offsetY: 0 })
  // Cache key for `baseTransformRef` so getBaseTransform only re-scans the
  // ~5000 points when the catalog or canvas size actually changes — not on
  // every redraw triggered by hover, pan, or zoom.
  const baseTransformKeyRef = useRef({ pts: null, w: 0, h: 0 })
  const dragRef = useRef({ dragging: false, startX: 0, startY: 0, startPanX: 0, startPanY: 0, moved: false })
  const initedRef = useRef(false)
  const drawRef = useRef(null)

  const getBaseTransform = useCallback((w, h, pts) => {
    const key = baseTransformKeyRef.current
    if (key.pts === pts && key.w === w && key.h === h) {
      return baseTransformRef.current
    }
    const pad = 60
    let value
    if (!pts.length) {
      value = { scale: 1, offsetX: 0, offsetY: 0 }
    } else {
      // Plain min/max loop rather than Math.min(...xs) — the spread creates
      // a temporary array of 5000 args, which is both slower and at risk
      // of hitting engine arg-count limits.
      let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity
      for (const p of pts) {
        if (p.x < minX) minX = p.x
        if (p.x > maxX) maxX = p.x
        if (p.y < minY) minY = p.y
        if (p.y > maxY) maxY = p.y
      }
      const rangeX = maxX - minX || 1
      const rangeY = maxY - minY || 1
      const usableW = w - pad * 2
      const usableH = h - pad * 2
      const scale = Math.min(usableW / rangeX, usableH / rangeY)
      const offsetX = pad + (usableW - rangeX * scale) / 2 - minX * scale
      const offsetY = pad + (usableH - rangeY * scale) / 2 - minY * scale
      value = { scale, offsetX, offsetY }
    }
    baseTransformRef.current = value
    baseTransformKeyRef.current = { pts, w, h }
    return value
  }, [])

  function toWorld(p, bt) {
    return { x: p.x * bt.scale + bt.offsetX, y: p.y * bt.scale + bt.offsetY }
  }

  function worldToScreen(wx, wy) {
    const { panX, panY, zoom } = viewRef.current
    return { x: wx * zoom + panX, y: wy * zoom + panY }
  }

  function pointToScreen(p, bt) {
    const w = toWorld(p, bt)
    return worldToScreen(w.x, w.y)
  }

  const draw = useCallback(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const rect = canvas.getBoundingClientRect()
    const dpr = window.devicePixelRatio || 1
    canvas.width = rect.width * dpr
    canvas.height = rect.height * dpr
    const ctx = canvas.getContext('2d')
    ctx.scale(dpr, dpr)
    ctx.clearRect(0, 0, rect.width, rect.height)

    const bt = getBaseTransform(rect.width, rect.height, points)

    if (!initedRef.current) {
      viewRef.current = { panX: 0, panY: 0, zoom: 1 }
      initedRef.current = true
    }

    const hasFilter = activeIds != null
    const NODE_R = 1.25 * Math.sqrt(viewRef.current.zoom)

    const cs = getComputedStyle(document.documentElement)
    const labelInk = cs.getPropertyValue('--ink').trim() || '#15151A'
    const labelMute = cs.getPropertyValue('--ink-soft').trim() || '#5D6D7E'
    // Ghost colour + alpha: how a salience-0 point looks. Low enough
    // that the bottom of the distribution clearly reads as "filtered
    // out" — for a specific query (e.g. "txarango") most songs end up
    // here and we want them out of the way visually. Dark mode needs a
    // lighter base colour and a slightly higher alpha because --ink-mute
    // on near-black is barely visible.
    const isDark = document.documentElement.dataset.theme === 'dark'
    const dimColor = isDark
      ? (cs.getPropertyValue('--ink-soft').trim() || '#B5AFA0')
      : (cs.getPropertyValue('--ink-mute').trim() || '#6B6B75')
    const dimAlpha = isDark ? 0.4 : 0.3

    // Resolve effective salience + rank for a song. Three filter
    // dimensions stack:
    //   1. No filter at all → everyone gets 1.0 (current "all colourful")
    //   2. Legend filter only → in/out is boolean (1.0 or 0.0)
    //   3. Chips active → salience and rank come from `filterScores`;
    //      the legend still gates via `activeIds` as a 0/1 multiplier.
    //
    // `sal` drives colour/opacity (dimmed when the query is uninformative);
    // `rank` drives size (always full range) so weak queries still show
    // their relative ordering at a glance.
    function getScores(p) {
      if (!hasFilter) return { sal: 1.0, rank: 1.0 }
      if (!activeIds.has(p.id)) return { sal: 0.0, rank: 0.0 }
      // Legend-only filter ⇒ no filterScores ⇒ full colour + size.
      const s = filterScores && filterScores[p.id]
      return s ? s : { sal: 1.0, rank: 1.0 }
    }

    // Bigger top size only under a *similarity* filter (chips). The genre
    // legend is a boolean categorical filter — its surviving points should
    // still read at the normal scale, not balloon up to 1.75 NODE_R.
    const topSize = filterScores ? FILTER_TOP : NORMAL_SIZE

    function drawPoint(p, sal, rank) {
      const sv = Math.pow(Math.max(0, Math.min(1, sal)),  SALIENCE_GAMMA)
      const rv = Math.pow(Math.max(0, Math.min(1, rank)), RANK_GAMMA)

      const { x: px, y: py } = pointToScreen(p, bt)
      const genre = genreColor(p.genre)
      const coreR = NODE_R * lerp(GHOST_SIZE, topSize, rv)

      // Halo — ramps in above HALO_ONSET on *salience* (we want the
      // halo to convey confidence, not just relative position).
      if (sv > HALO_ONSET) {
        const haloT = (sv - HALO_ONSET) / (1 - HALO_ONSET)
        ctx.beginPath()
        ctx.arc(px, py, coreR * (1.4 + 0.55 * haloT), 0, Math.PI * 2)
        ctx.fillStyle = genre
        ctx.globalAlpha = 0.20 * haloT
        ctx.fill()
      }

      // Core: blend grey ↔ genre colour driven by salience. The ×1.8
      // multiplier saturates colour just before sv crosses the upper
      // half so a clearly highlighted song is fully coloured, while a
      // low-sv song stays mostly grey-tinted (the "filtered out" cue).
      const colour = lerpColor(dimColor, genre, Math.min(1, sv * 1.8))
      ctx.beginPath()
      ctx.arc(px, py, coreR, 0, Math.PI * 2)
      ctx.fillStyle = colour
      ctx.globalAlpha = lerp(dimAlpha, 1.0, sv)
      ctx.fill()

      // Outline only on confident matches.
      if (sv > OUTLINE_ONSET) {
        const outT = (sv - OUTLINE_ONSET) / (1 - OUTLINE_ONSET)
        ctx.strokeStyle = labelInk
        ctx.globalAlpha = 0.55 * outT
        ctx.lineWidth = 1
        ctx.stroke()
      }

      ctx.globalAlpha = 1
    }

    function drawHoveredNode(p) {
      const { x: px, y: py } = pointToScreen(p, bt)
      const color = genreColor(p.genre)
      const r = NODE_R

      ctx.beginPath()
      ctx.arc(px, py, r * 3, 0, Math.PI * 2)
      ctx.fillStyle = color
      ctx.globalAlpha = 0.14
      ctx.fill()

      ctx.beginPath()
      ctx.arc(px, py, r * 2, 0, Math.PI * 2)
      ctx.fillStyle = color
      ctx.globalAlpha = 0.28
      ctx.fill()

      ctx.beginPath()
      ctx.arc(px, py, r * 1.2, 0, Math.PI * 2)
      ctx.fillStyle = color
      ctx.globalAlpha = 1
      ctx.fill()
      ctx.strokeStyle = '#fff'
      ctx.lineWidth = 2
      ctx.stroke()

      const labelSz = 13
      ctx.font = `600 ${labelSz}px Inter, system-ui, sans-serif`
      ctx.textAlign = 'center'
      ctx.fillStyle = labelInk
      ctx.fillText(p.title, px, py - r - 12)
      const subSz = 11
      ctx.font = `${subSz}px Inter, system-ui, sans-serif`
      ctx.fillStyle = labelMute
      ctx.fillText(`${p.artist} · ${p.year || ''}`, px, py - r - 12 - labelSz - 2)
      ctx.globalAlpha = 1
    }

    function drawFocalNode(p) {
      const { x: px, y: py } = pointToScreen(p, bt)
      const color = genreColor(p.genre)
      const r = NODE_R

      ctx.beginPath()
      ctx.arc(px, py, r * 2.4, 0, Math.PI * 2)
      ctx.strokeStyle = color
      ctx.globalAlpha = 0.35
      ctx.lineWidth = 1.5
      ctx.stroke()
      ctx.globalAlpha = 1

      const s = r * 1.1
      ctx.save()
      ctx.translate(px, py)
      ctx.rotate(Math.PI / 4)
      ctx.beginPath()
      ctx.rect(-s, -s, s * 2, s * 2)
      ctx.fillStyle = color
      ctx.fill()
      ctx.strokeStyle = '#fff'
      ctx.lineWidth = 2
      ctx.stroke()
      ctx.restore()

      const labelSz = 13
      ctx.font = `600 ${labelSz}px Inter, system-ui, sans-serif`
      ctx.textAlign = 'center'
      ctx.fillStyle = color
      ctx.fillText(p.title, px, py - r * 2.8 - 4)
      const subSz = 11
      ctx.font = `${subSz}px Inter, system-ui, sans-serif`
      ctx.fillStyle = labelMute
      ctx.fillText(`${p.artist}`, px, py - r * 2.8 - 4 - labelSz - 2)
    }

    // Single pass sorted by salience ascending → high-salience points end
    // up drawn on top of the ghost cloud. Focal and hover overlays come
    // afterwards so they always win.
    const drawOrder = points
      .filter(p => p.id !== focalId && p.id !== highlightedId)
      .map(p => ({ p, sc: getScores(p) }))
      .sort((a, b) => a.sc.sal - b.sc.sal)

    for (const { p, sc } of drawOrder) {
      drawPoint(p, sc.sal, sc.rank)
    }

    if (focalId != null) {
      const fp = points.find(p => p.id === focalId)
      if (fp && fp.id !== highlightedId) drawFocalNode(fp)
    }

    if (highlightedId != null) {
      const hp = points.find(p => p.id === highlightedId)
      if (hp) drawHoveredNode(hp)
    }
  }, [points, activeIds, filterScores, focalId, highlightedId, getBaseTransform])

  useEffect(() => { drawRef.current = draw }, [draw])

  useEffect(() => {
    initedRef.current = false
  }, [points])

  useEffect(() => {
    draw()
    const onResize = () => draw()
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [draw])

  function getScreenPos(p) {
    return pointToScreen(p, baseTransformRef.current)
  }

  function findClosestPoint(mx, my) {
    let closest = null
    let closestDist = Math.max(10, 1.25 * Math.sqrt(viewRef.current.zoom) + 6)
    for (const p of points) {
      const sp = getScreenPos(p)
      const dist = Math.hypot(mx - sp.x, my - sp.y)
      if (dist < closestDist) {
        closestDist = dist
        closest = p
      }
    }
    return closest
  }

  function handleMouseMove(e) {
    const canvas = canvasRef.current
    if (!canvas) return

    if (dragRef.current.dragging) {
      const dx = e.clientX - dragRef.current.startX
      const dy = e.clientY - dragRef.current.startY
      if (Math.abs(dx) > 2 || Math.abs(dy) > 2) {
        dragRef.current.moved = true
      }
      viewRef.current.panX = dragRef.current.startPanX + dx
      viewRef.current.panY = dragRef.current.startPanY + dy
      draw()
      return
    }

    const rect = canvas.getBoundingClientRect()
    const mx = e.clientX - rect.left
    const my = e.clientY - rect.top
    const closest = findClosestPoint(mx, my)
    onPointHover(closest ? closest.id : null)
  }

  function handleMouseDown(e) {
    // Only react to the primary button — right/middle clicks shouldn't
    // start a drag and shouldn't trigger a click on mouseup.
    if (e.button !== 0) return
    dragRef.current = {
      dragging: true,
      startX: e.clientX,
      startY: e.clientY,
      startPanX: viewRef.current.panX,
      startPanY: viewRef.current.panY,
      moved: false,
    }
  }

  function handleMouseUp(e) {
    if (e.button !== 0) return
    const wasDragging = dragRef.current.dragging
    const moved = dragRef.current.moved
    dragRef.current.dragging = false
    dragRef.current.moved = false

    if (!wasDragging || moved) return

    const canvas = canvasRef.current
    if (!canvas) return
    const rect = canvas.getBoundingClientRect()
    const mx = e.clientX - rect.left
    const my = e.clientY - rect.top
    const closest = findClosestPoint(mx, my)
    if (!closest) return
    onPointOpenDetail?.(closest.id)
  }

  function handleWheel(e) {
    e.preventDefault()
    const canvas = canvasRef.current
    if (!canvas) return
    const rect = canvas.getBoundingClientRect()
    const mx = e.clientX - rect.left
    const my = e.clientY - rect.top
    const oldZoom = viewRef.current.zoom
    const factor = e.deltaY > 0 ? 0.9 : 1.1
    const newZoom = Math.max(0.2, Math.min(15, oldZoom * factor))
    const worldX = (mx - viewRef.current.panX) / oldZoom
    const worldY = (my - viewRef.current.panY) / oldZoom
    viewRef.current.zoom = newZoom
    viewRef.current.panX = mx - worldX * newZoom
    viewRef.current.panY = my - worldY * newZoom
    draw()
  }

  // Cursor: 'pointer' when hovering a point (it's clickable),
  // otherwise the CSS default of 'grab' applies — and ``.viz-canvas:active``
  // already handles the 'grabbing' state while a drag is in flight.
  const cursor = highlightedId != null ? 'pointer' : undefined

  return (
    <div className="viz-container" ref={containerRef}>
      <canvas
        ref={canvasRef}
        className="viz-canvas"
        onMouseMove={handleMouseMove}
        onMouseDown={handleMouseDown}
        onMouseUp={handleMouseUp}
        onMouseLeave={() => { dragRef.current.dragging = false; onPointHover(null) }}
        onWheel={handleWheel}
        onContextMenu={e => e.preventDefault()}
        style={{ cursor }}
      />
      <div className="viz-legend" role="group" aria-label="Filtra per gènere (Ctrl/⌘-clic per a múltiples)">
        {Object.entries(GENRE_COLORS).map(([g, c]) => {
          const isActive = activeGenres.includes(g)
          // No callback ⇒ the legend stays a passive swatch row (back-compat
          // for any future caller that doesn't wire up filtering).
          const clickable = typeof onAddGenreChip === 'function'
          const className = 'legend-item'
            + (clickable ? ' legend-item--clickable' : '')
            + (isActive  ? ' legend-item--active'    : '')
          const style = { '--legend-color': c, ...(isActive ? { background: c } : null) }
          return clickable
            ? (
              <button
                key={g}
                type="button"
                className={className}
                style={style}
                onClick={(e) => onAddGenreChip(g, e.ctrlKey || e.metaKey)}
                aria-pressed={isActive}
                title="Ctrl/⌘-clic per afegir-ne més d'un"
              >
                <span className="legend-dot" style={{ background: c }} />
                {g}
              </button>
            )
            : (
              <span key={g} className={className} style={style}>
                <span className="legend-dot" style={{ background: c }} />
                {g}
              </span>
            )
        })}
      </div>
    </div>
  )
}
