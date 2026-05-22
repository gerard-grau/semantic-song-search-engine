import { useRef, useEffect, useCallback } from 'react'
import { genreColor, GENRE_COLORS } from './genreColors'

/**
 * 2D Scatter — chip-driven salience visualization.
 *
 * Every point is rendered with visual properties (size, opacity, colour
 * blend) driven continuously by its salience score in [0, 1]:
 *
 *   salience ≈ 0  →  small grey "ghost" (poor match)
 *   salience ≈ 1  →  big saturated genre dot with halo (strong match)
 *
 * The frontend doesn't filter anything — low-salience points just recede
 * visually. Without an active filter (no chips, no genre legend) every
 * point gets salience 1.0 so the scatter shows the full coloured catalog.
 *
 * The genre legend still hard-filters via `activeIds`: a song that is
 * excluded by the legend gets salience 0 regardless of its chip score.
 */
const SALIENCE_GAMMA = 1.4   // colour contrast curve (higher = punchier)
const RANK_GAMMA     = 1.3   // size contrast curve
const GHOST_SIZE     = 0.7   // size multiplier at rank 0 / unfiltered point
const NORMAL_SIZE    = 1.15  // size multiplier with no filter active
const FILTER_TOP     = 1.75  // size multiplier at rank 1 *under* a filter,
                             // intentionally bigger than NORMAL_SIZE so top
                             // matches read as standing out from the cloud
const HALO_ONSET     = 0.35  // salience above which a halo starts to grow
const OUTLINE_ONSET  = 0.50  // salience above which a dark outline appears

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
  points, activeIds, salienceMap, rankMap, focalId,
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
  const dragRef = useRef({ dragging: false, startX: 0, startY: 0, startPanX: 0, startPanY: 0, moved: false })
  const initedRef = useRef(false)
  const drawRef = useRef(null)

  const getBaseTransform = useCallback((w, h, pts) => {
    if (!pts.length) return { scale: 1, offsetX: 0, offsetY: 0 }
    const pad = 60
    const xs = pts.map(p => p.x)
    const ys = pts.map(p => p.y)
    const minX = Math.min(...xs), maxX = Math.max(...xs)
    const minY = Math.min(...ys), maxY = Math.max(...ys)
    const rangeX = maxX - minX || 1
    const rangeY = maxY - minY || 1
    const usableW = w - pad * 2
    const usableH = h - pad * 2
    const scale = Math.min(usableW / rangeX, usableH / rangeY)
    const offsetX = pad + (usableW - rangeX * scale) / 2 - minX * scale
    const offsetY = pad + (usableH - rangeY * scale) / 2 - minY * scale
    return { scale, offsetX, offsetY }
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
    baseTransformRef.current = bt

    if (!initedRef.current) {
      viewRef.current = { panX: 0, panY: 0, zoom: 1 }
      initedRef.current = true
    }

    const hasFilter = activeIds != null
    const NODE_R = 1.25 * Math.sqrt(viewRef.current.zoom)

    const cs = getComputedStyle(document.documentElement)
    const labelInk = cs.getPropertyValue('--ink').trim() || '#15151A'
    const labelMute = cs.getPropertyValue('--ink-soft').trim() || '#5D6D7E'
    // Ghost colour: what a salience-0 point looks like — the same muted
    // grey the scatter has always used for filtered-out points. Dark mode
    // needs a lighter base colour + higher alpha because --ink-mute on
    // near-black is essentially invisible.
    const isDark = document.documentElement.dataset.theme === 'dark'
    const dimColor = isDark
      ? (cs.getPropertyValue('--ink-soft').trim() || '#B5AFA0')
      : (cs.getPropertyValue('--ink-mute').trim() || '#6B6B75')
    const dimAlpha = isDark ? 0.38 : 0.22

    // Resolve effective salience + rank for a song. Three filter
    // dimensions stack:
    //   1. No filter at all → everyone gets 1.0 (current "all colourful")
    //   2. Legend filter only → in/out is boolean (1.0 or 0.0)
    //   3. Chips active → salience and rank come from their maps; legend
    //      still gates as a 0/1 multiplier on both.
    //
    // Returns {sal, rank}. `sal` drives colour/opacity (dimmed when the
    // query is uninformative); `rank` drives size (always full range)
    // so weak queries still show their relative ordering at a glance.
    function getScores(p) {
      if (!hasFilter) return { sal: 1.0, rank: 1.0 }
      if (!activeIds.has(p.id)) return { sal: 0.0, rank: 0.0 }
      const s = salienceMap?.get(p.id)
      const r = rankMap?.get(p.id)
      // Legend-only filter (no chips) ⇒ both default to 1: full colour, full size.
      return {
        sal:  s == null ? 1.0 : s,
        rank: r == null ? (s == null ? 1.0 : s) : r,
      }
    }

    // Bigger top size only under a *similarity* filter (chips). The genre
    // legend is a boolean categorical filter — its surviving points should
    // still read at the normal scale, not balloon up to 1.75 NODE_R.
    const topSize = salienceMap ? FILTER_TOP : NORMAL_SIZE

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

      // Core: blend grey ↔ genre colour driven by salience. The ×1.6
      // multiplier lets saturation catch up faster than opacity so
      // mid-salience points still read as "in the cluster".
      const colour = lerpColor(dimColor, genre, Math.min(1, sv * 1.6))
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
  }, [points, activeIds, salienceMap, rankMap, focalId, highlightedId, getBaseTransform])

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
