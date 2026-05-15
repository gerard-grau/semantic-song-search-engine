import { useRef, useEffect, useState, useCallback } from 'react'
import { genreColor, GENRE_COLORS } from './genreColors'

/**
 * 2D Scatter — chip-driven filter visualization.
 *
 * All songs are always visible. Filtered-out items lose their genre colour
 * (rendered as a muted grey) and fade to low opacity; matched items keep the
 * genre colour at full opacity. A click on a point opens a small in-canvas
 * popover with "Cerca similars" / "Veure detall" actions.
 */
export default function Scatter2D({
  points, activeIds, focalId,
  highlightedId, onPointHover, onPointSearchSimilar, onPointOpenDetail,
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

  // Popover state — opens on point click, anchored to the point in screen space.
  const [popover, setPopover] = useState(null) // { id, x, y, title, artist }

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
    // Filtered-out points: softer, lighter — they should recede into the
    // background so the matched set can be read at a glance.
    const dimColor = cs.getPropertyValue('--ink-mute').trim() || '#6B6B75'

    function drawDimNode(p) {
      const { x: px, y: py } = pointToScreen(p, bt)
      const r = NODE_R
      ctx.beginPath()
      ctx.arc(px, py, r * 0.7, 0, Math.PI * 2)
      ctx.fillStyle = dimColor
      ctx.globalAlpha = 0.22
      ctx.fill()
      ctx.globalAlpha = 1
    }

    function drawActiveNode(p) {
      // Matched points: bigger halo + fully opaque core + dark outline.
      // The outline uses the theme's ink colour so each point reads as a
      // crisp, solid mark against the dimmed background — the eye snaps
      // to the active set instead of the noise of grey dots.
      const { x: px, y: py } = pointToScreen(p, bt)
      const color = genreColor(p.genre)
      const r = NODE_R

      ctx.beginPath()
      ctx.arc(px, py, r * 1.9, 0, Math.PI * 2)
      ctx.fillStyle = color
      ctx.globalAlpha = 0.18
      ctx.fill()

      ctx.beginPath()
      ctx.arc(px, py, r * 1.15, 0, Math.PI * 2)
      ctx.fillStyle = color
      ctx.globalAlpha = 1
      ctx.fill()
      ctx.strokeStyle = labelInk
      ctx.globalAlpha = 0.55
      ctx.lineWidth = 1
      ctx.stroke()
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

    // Layer 1 — dimmed (filtered-out) nodes, colour stripped.
    if (hasFilter) {
      for (const p of points) {
        if (activeIds.has(p.id)) continue
        if (p.id === highlightedId) continue
        drawDimNode(p)
      }
    }

    // Layer 2 — active nodes (or all if no filter), genre colour.
    for (const p of points) {
      if (p.id === highlightedId) continue
      if (p.id === focalId) continue
      if (hasFilter && !activeIds.has(p.id)) continue
      drawActiveNode(p)
    }

    // Layer 3 — focal (diamond).
    if (focalId != null) {
      const fp = points.find(p => p.id === focalId)
      if (fp && fp.id !== highlightedId) drawFocalNode(fp)
    }

    // Layer 4 — hovered.
    if (highlightedId != null) {
      const hp = points.find(p => p.id === highlightedId)
      if (hp) drawHoveredNode(hp)
    }
  }, [points, activeIds, focalId, highlightedId, getBaseTransform])

  useEffect(() => { drawRef.current = draw }, [draw])

  useEffect(() => {
    initedRef.current = false
    setPopover(null)
  }, [points])

  // Re-anchor the popover when the view changes (zoom/pan/resize).
  useEffect(() => {
    if (!popover) return
    const p = points.find(pt => pt.id === popover.id)
    if (!p) { setPopover(null); return }
    const { x, y } = pointToScreen(p, baseTransformRef.current)
    setPopover(prev => prev && (prev.x === x && prev.y === y ? prev : { ...prev, x, y }))
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
        if (popover) setPopover(null)
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
    if (!closest) {
      setPopover(null)
      return
    }

    const sp = getScreenPos(closest)
    setPopover({
      id: closest.id,
      x: sp.x,
      y: sp.y,
      title: closest.title,
      artist: closest.artist,
    })
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
    if (popover) setPopover(null)
    draw()
  }

  function closePopover() { setPopover(null) }

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
        style={{ cursor: dragRef.current?.dragging ? 'grabbing' : 'grab' }}
      />
      {popover && (
        <div
          className="viz-popover"
          style={{ left: popover.x, top: popover.y }}
          onMouseDown={e => e.stopPropagation()}
        >
          <div className="viz-popover-header">
            <div className="viz-popover-title" title={popover.title}>{popover.title}</div>
            <div className="viz-popover-artist" title={popover.artist}>{popover.artist}</div>
          </div>
          <div className="viz-popover-actions">
            <button
              className="viz-popover-btn viz-popover-btn--primary"
              onClick={() => {
                onPointSearchSimilar?.(popover.id, popover.title)
                closePopover()
              }}
            >
              Cerca similars
            </button>
            <button
              className="viz-popover-btn"
              onClick={() => {
                onPointOpenDetail?.(popover.id)
                closePopover()
              }}
            >
              Veure detall
            </button>
            <button
              className="viz-popover-btn viz-popover-btn--close"
              onClick={closePopover}
              aria-label="Tanca"
            >
              ×
            </button>
          </div>
        </div>
      )}
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
