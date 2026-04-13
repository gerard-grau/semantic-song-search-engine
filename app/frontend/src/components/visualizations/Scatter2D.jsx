import { useRef, useEffect, useCallback } from 'react'
import { genreColor, GENRE_COLORS } from './genreColors'

/**
 * 2D Scatter with free pan & zoom and role-aware rendering.
 *
 * Each point carries a `role` field from the backend:
 *   "focal"    — the song you clicked (diamond shape, prominent label)
 *   "neighbor" — a nearest neighbor (normal dot)
 *   "previous" — the song you came from (dashed-ring dot)
 *   "bridge"   — an anchor from the previous neighborhood (tiny, transparent)
 *
 * Layered draw order: bridges → neighbors → previous → focal → hovered
 *
 * centerOnId: when points change, centers the view on that song id.
 *
 * Bug-fix note: view reset is decoupled from hover redraws by putting
 * `initedRef.current = false` in its own useEffect([points]) instead
 * of inside the draw callback — this prevents hover from resetting pan/zoom.
 */
export default function Scatter2D({ points, highlightedId, onPointHover, onPointClick, faded, centerOnId }) {
  const canvasRef = useRef(null)
  const viewRef = useRef({ panX: 0, panY: 0, zoom: 1 })
  const baseTransformRef = useRef({ scale: 1, offsetX: 0, offsetY: 0 })
  const dragRef = useRef({ dragging: false, startX: 0, startY: 0, startPanX: 0, startPanY: 0 })
  const initedRef = useRef(false)
  const animFrameRef = useRef(null)
  const drawRef = useRef(null)
  const centerOnIdRef = useRef(centerOnId)
  const pendingFocalIdRef = useRef(null)

  useEffect(() => { centerOnIdRef.current = centerOnId }, [centerOnId])

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

    // Initialize view on first draw after points change
    if (!initedRef.current) {
      const focalPoint = centerOnIdRef.current != null
        ? points.find(p => p.id === centerOnIdRef.current)
        : null

      if (focalPoint) {
        const w = toWorld(focalPoint, bt)
        viewRef.current = {
          panX: rect.width / 2 - w.x,
          panY: rect.height / 2 - w.y,
          zoom: 1,
        }
      } else {
        viewRef.current = { panX: 0, panY: 0, zoom: 1 }
      }
      initedRef.current = true
    }

    const { zoom } = viewRef.current
    const textColor = getComputedStyle(document.documentElement)
      .getPropertyValue('--text-primary').trim() || '#333'

    // Partition by role for layered rendering
    const bridges  = points.filter(p => p.role === 'bridge')
    const neighbors = points.filter(p => !p.role || p.role === 'neighbor')
    const prevFocal = points.find(p => p.role === 'previous')
    const focalPt   = points.find(p => p.role === 'focal')

    // ── Layer 1: Bridge nodes (tiny, transparent anchors) ──
    for (const p of bridges) {
      if (p.id === highlightedId) continue
      const { x: px, y: py } = pointToScreen(p, bt)
      ctx.beginPath()
      ctx.arc(px, py, 4 * zoom, 0, Math.PI * 2)
      ctx.fillStyle = genreColor(p.genre)
      ctx.globalAlpha = 0.32
      ctx.fill()
      ctx.globalAlpha = 1
    }

    // ── Layer 2: Normal neighbor nodes ──
    const pendingFocalId = pendingFocalIdRef.current
    for (const p of neighbors) {
      if (p.id === highlightedId) continue
      if (p.id === pendingFocalId) continue
      const { x: px, y: py } = pointToScreen(p, bt)
      ctx.beginPath()
      ctx.arc(px, py, 7 * zoom, 0, Math.PI * 2)
      ctx.fillStyle = genreColor(p.genre)
      ctx.globalAlpha = faded ? 0.25 : 0.85
      ctx.fill()
      ctx.globalAlpha = 1
    }

    // ── Layer 3: Previous focal node (dashed ring) ──
    if (prevFocal && prevFocal.id !== highlightedId) {
      const { x: px, y: py } = pointToScreen(prevFocal, bt)
      const r = 8 * zoom
      const color = genreColor(prevFocal.genre)

      ctx.beginPath()
      ctx.arc(px, py, r, 0, Math.PI * 2)
      ctx.fillStyle = color
      ctx.globalAlpha = 0.45
      ctx.fill()
      ctx.globalAlpha = 1

      ctx.setLineDash([Math.max(2, 3 * zoom), Math.max(2, 3 * zoom)])
      ctx.beginPath()
      ctx.arc(px, py, r + 2 * zoom, 0, Math.PI * 2)
      ctx.strokeStyle = '#fff'
      ctx.lineWidth = 1.5
      ctx.stroke()
      ctx.setLineDash([])

      // Subtle label
      const labelSz = Math.round(Math.max(9, 10 * zoom))
      ctx.font = `${labelSz}px system-ui, sans-serif`
      ctx.textAlign = 'center'
      ctx.globalAlpha = 0.65
      ctx.fillStyle = textColor
      ctx.fillText(prevFocal.title, px, py - r - 4 * zoom)
      ctx.globalAlpha = 1
    }

    // ── Layer 4: Focal node (diamond + outer ring + bold label) ──
    if (focalPt) {
      const { x: px, y: py } = pointToScreen(focalPt, bt)
      const r = 13 * zoom
      const color = genreColor(focalPt.genre)

      // Outer ring
      ctx.beginPath()
      ctx.arc(px, py, r * 1.65, 0, Math.PI * 2)
      ctx.strokeStyle = color
      ctx.globalAlpha = 0.35
      ctx.lineWidth = 1.5
      ctx.stroke()
      ctx.globalAlpha = 1

      // Diamond (rotated square)
      const s = r * 0.75
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

      // Bold label above
      const labelSz = Math.round(Math.max(11, 13 * zoom))
      ctx.font = `bold ${labelSz}px system-ui, sans-serif`
      ctx.textAlign = 'center'
      ctx.fillStyle = textColor
      ctx.fillText(`${focalPt.title} — ${focalPt.artist}`, px, py - r * 1.85 - 6)
    }

    // ── Layer 5: Highlighted node (hover), unless it is the focal ──
    if (highlightedId != null) {
      const hp = points.find(p => p.id === highlightedId)
      if (hp && hp.role !== 'focal' && hp.id !== pendingFocalId) {
        const { x: px, y: py } = pointToScreen(hp, bt)
        const HR = hp.role === 'previous' ? 10 : 12

        ctx.beginPath()
        ctx.arc(px, py, (HR + 4) * zoom, 0, Math.PI * 2)
        ctx.fillStyle = genreColor(hp.genre)
        ctx.globalAlpha = 0.3
        ctx.fill()
        ctx.globalAlpha = 1

        ctx.beginPath()
        ctx.arc(px, py, HR * zoom, 0, Math.PI * 2)
        ctx.fillStyle = genreColor(hp.genre)
        ctx.fill()
        ctx.strokeStyle = '#fff'
        ctx.lineWidth = 2.5
        ctx.stroke()

        const labelSz = Math.round(Math.max(10, 13 * zoom))
        ctx.font = `bold ${labelSz}px system-ui, sans-serif`
        ctx.textAlign = 'center'
        ctx.fillStyle = textColor
        ctx.fillText(`${hp.title} — ${hp.artist}`, px, py - HR * zoom - 8)
      }
    }

    // ── Layer 6: Pending focal (clicked but not yet loaded) — diamond ──
    if (pendingFocalId != null) {
      const pp = points.find(p => p.id === pendingFocalId)
      if (pp) {
        const { x: px, y: py } = pointToScreen(pp, bt)
        const r = 13 * zoom
        const color = genreColor(pp.genre)

        ctx.beginPath()
        ctx.arc(px, py, r * 1.65, 0, Math.PI * 2)
        ctx.strokeStyle = color
        ctx.globalAlpha = 0.35
        ctx.lineWidth = 1.5
        ctx.stroke()
        ctx.globalAlpha = 1

        const s = r * 0.75
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

        const labelSz = Math.round(Math.max(11, 13 * zoom))
        ctx.font = `bold ${labelSz}px system-ui, sans-serif`
        ctx.textAlign = 'center'
        ctx.fillStyle = textColor
        ctx.fillText(`${pp.title} — ${pp.artist}`, px, py - r * 1.85 - 6)
      }
    }
  }, [points, highlightedId, faded, getBaseTransform])

  // Keep drawRef current so animateTo always calls the latest version
  useEffect(() => { drawRef.current = draw }, [draw])

  // Reset view flag ONLY when points change (not on hover/highlight changes).
  // Also cancel any in-flight animation and clear pending focal.
  useEffect(() => {
    if (animFrameRef.current) {
      cancelAnimationFrame(animFrameRef.current)
      animFrameRef.current = null
    }
    pendingFocalIdRef.current = null
    initedRef.current = false
  }, [points])

  // Redraw on any visual change (points, highlight, faded)
  useEffect(() => {
    draw()
    const onResize = () => draw()
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [draw])

  // Smooth pan animation toward targetPan (zoom stays fixed)
  function animateTo(targetPanX, targetPanY, duration = 1050, onComplete = null) {
    if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current)

    const startPanX = viewRef.current.panX
    const startPanY = viewRef.current.panY
    const startTime = performance.now()

    function step(now) {
      const t = Math.min((now - startTime) / duration, 1)
      // cubic ease-in-out: midpoint is exactly 50% done, motion distributes evenly
      const ease = t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2
      viewRef.current.panX = startPanX + (targetPanX - startPanX) * ease
      viewRef.current.panY = startPanY + (targetPanY - startPanY) * ease
      drawRef.current?.()
      if (t < 1) {
        animFrameRef.current = requestAnimationFrame(step)
      } else {
        animFrameRef.current = null
        onComplete?.()
      }
    }

    animFrameRef.current = requestAnimationFrame(step)
  }

  function getScreenPos(p) {
    return pointToScreen(p, baseTransformRef.current)
  }

  function handleMouseMove(e) {
    const canvas = canvasRef.current
    if (!canvas) return

    if (dragRef.current.dragging) {
      const dx = e.clientX - dragRef.current.startX
      const dy = e.clientY - dragRef.current.startY
      viewRef.current.panX = dragRef.current.startPanX + dx
      viewRef.current.panY = dragRef.current.startPanY + dy
      draw()
      return
    }

    const rect = canvas.getBoundingClientRect()
    const mx = e.clientX - rect.left
    const my = e.clientY - rect.top

    let closest = null
    let closestDist = 20 * viewRef.current.zoom

    for (const p of points) {
      const sp = getScreenPos(p)
      const dist = Math.hypot(mx - sp.x, my - sp.y)
      if (dist < closestDist) {
        closestDist = dist
        closest = p
      }
    }
    onPointHover(closest ? closest.id : null)
  }

  function handleMouseDown(e) {
    dragRef.current = {
      dragging: true,
      startX: e.clientX,
      startY: e.clientY,
      startPanX: viewRef.current.panX,
      startPanY: viewRef.current.panY,
    }
  }

  function handleMouseUp(e) {
    const wasDragging = dragRef.current.dragging
    const dx = Math.abs(e.clientX - dragRef.current.startX)
    const dy = Math.abs(e.clientY - dragRef.current.startY)
    dragRef.current.dragging = false

    if (wasDragging && dx < 4 && dy < 4) {
      const canvas = canvasRef.current
      if (!canvas) return
      const rect = canvas.getBoundingClientRect()
      const mx = e.clientX - rect.left
      const my = e.clientY - rect.top

      for (const p of points) {
        const sp = getScreenPos(p)
        if (Math.hypot(mx - sp.x, my - sp.y) < 15 * viewRef.current.zoom) {
          // Mark as pending immediately so it renders as a diamond during the pan
          pendingFocalIdRef.current = p.id
          drawRef.current?.()
          // Pan to centre, then trigger the neighborhood fetch
          const w = toWorld(p, baseTransformRef.current)
          const targetPanX = rect.width / 2 - w.x * viewRef.current.zoom
          const targetPanY = rect.height / 2 - w.y * viewRef.current.zoom
          animateTo(targetPanX, targetPanY, 1050, () => {
            pendingFocalIdRef.current = null
            onPointClick(p.id)
          })
          return
        }
      }
    }
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

  return (
    <div className="viz-container">
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
      <div className="viz-legend">
        {Object.entries(GENRE_COLORS).map(([g, c]) => (
          <span key={g} className="legend-item">
            <span className="legend-dot" style={{ background: c }} />
            {g}
          </span>
        ))}
      </div>
    </div>
  )
}
