import { useRef, useEffect, useCallback } from 'react'
import { genreColor, GENRE_COLORS, hexToRgb } from './genreColors'

/**
 * 2D Scatter — design-style rendering inspired by Cançoner.html.
 *
 * All songs are always visible. Filtering/similarity only changes opacity.
 * Active songs: full opacity. Inactive songs: dimmed (opacity 0.18).
 * No size scaling — all nodes same size.
 *
 * Visual style from the design reference:
 *   - Outer glow halo when active/hovered
 *   - Genre-colored filled circle with subtle stroke
 *   - White inner dot when selected/focal
 *   - Labels: title above, artist·year below (visible on hover or focal)
 */
export default function Scatter2D({
  points, activeIds, scoreMap, focalId,
  highlightedId, onPointHover, onPointClick, onPointDoubleClick,
}) {
  const canvasRef = useRef(null)
  const viewRef = useRef({ panX: 0, panY: 0, zoom: 1 })
  const baseTransformRef = useRef({ scale: 1, offsetX: 0, offsetY: 0 })
  const dragRef = useRef({ dragging: false, startX: 0, startY: 0, startPanX: 0, startPanY: 0 })
  const initedRef = useRef(false)
  const drawRef = useRef(null)
  const dblClickTimerRef = useRef(null)

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
    // Dots scale with zoom on a sqrt curve: visibly responsive but tapers off
    // so they don't dominate the canvas at high zoom levels.
    const NODE_R = 1.25 * Math.sqrt(viewRef.current.zoom)

    // Read theme-aware label colors from CSS tokens so canvas matches the page.
    const cs = getComputedStyle(document.documentElement)
    const labelInk = cs.getPropertyValue('--ink').trim() || '#15151A'
    const labelMute = cs.getPropertyValue('--ink-soft').trim() || '#5D6D7E'

    // Helper to draw a node in the design style
    function drawNode(p, opacity, isHovered, isFocal) {
      const { x: px, y: py } = pointToScreen(p, bt)
      const color = genreColor(p.genre)
      const r = NODE_R

      if (isFocal) {
        // Diamond shape for focal song
        ctx.globalAlpha = 1

        // Outer ring
        ctx.beginPath()
        ctx.arc(px, py, r * 2.4, 0, Math.PI * 2)
        ctx.strokeStyle = color
        ctx.globalAlpha = 0.35
        ctx.lineWidth = 1.5
        ctx.stroke()
        ctx.globalAlpha = 1

        // Diamond
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

        // Label (constant size)
        const labelSz = 13
        ctx.font = `600 ${labelSz}px Inter, system-ui, sans-serif`
        ctx.textAlign = 'center'
        ctx.fillStyle = color
        ctx.fillText(p.title, px, py - r * 2.8 - 4)
        const subSz = 11
        ctx.font = `${subSz}px Inter, system-ui, sans-serif`
        ctx.fillStyle = labelMute
        ctx.fillText(`${p.artist}`, px, py - r * 2.8 - 4 - labelSz - 2)
        ctx.globalAlpha = 1
        return
      }

      if (isHovered) {
        ctx.globalAlpha = 1

        // Glow halo
        ctx.beginPath()
        ctx.arc(px, py, r * 3, 0, Math.PI * 2)
        ctx.fillStyle = color
        ctx.globalAlpha = 0.14
        ctx.fill()

        // Outer soft ring
        ctx.beginPath()
        ctx.arc(px, py, r * 2, 0, Math.PI * 2)
        ctx.fillStyle = color
        ctx.globalAlpha = 0.28
        ctx.fill()

        // Main circle (slightly larger on hover)
        ctx.beginPath()
        ctx.arc(px, py, r * 1.2, 0, Math.PI * 2)
        ctx.fillStyle = color
        ctx.globalAlpha = 1
        ctx.fill()
        ctx.strokeStyle = '#fff'
        ctx.lineWidth = 2
        ctx.stroke()

        // Label (constant size)
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
        return
      }

      // Normal node — design style: outer halo + inner fill + stroke
      const isActive = opacity > 0.5

      if (isActive) {
        // Soft outer ring for active nodes
        ctx.beginPath()
        ctx.arc(px, py, r * 1.6, 0, Math.PI * 2)
        ctx.fillStyle = color
        ctx.globalAlpha = 0.08
        ctx.fill()
      }

      // Main circle — always genre-colored
      ctx.beginPath()
      ctx.arc(px, py, r, 0, Math.PI * 2)
      ctx.fillStyle = color
      ctx.globalAlpha = isActive ? 0.88 : 0.35
      ctx.fill()
      ctx.strokeStyle = color
      ctx.lineWidth = isActive ? 1.5 : 1
      ctx.globalAlpha = isActive ? 0.65 : 0.4
      ctx.stroke()

      ctx.globalAlpha = 1
    }

    // ── Layer 1: Dimmed nodes ──
    if (hasFilter) {
      for (const p of points) {
        if (activeIds.has(p.id)) continue
        if (p.id === highlightedId) continue
        drawNode(p, 0.35, false, false)
      }
    }

    // ── Layer 2: Active nodes (or all if no filter) ──
    for (const p of points) {
      if (p.id === highlightedId) continue
      if (p.id === focalId) continue
      if (hasFilter && !activeIds.has(p.id)) continue
      drawNode(p, hasFilter ? 0.9 : 0.75, false, false)
    }

    // ── Layer 3: Focal (diamond) ──
    if (focalId != null) {
      const fp = points.find(p => p.id === focalId)
      if (fp && fp.id !== highlightedId) {
        drawNode(fp, 1, false, true)
      }
    }

    // ── Layer 4: Hovered ──
    if (highlightedId != null) {
      const hp = points.find(p => p.id === highlightedId)
      if (hp) {
        drawNode(hp, 1, true, hp.id === focalId)
      }
    }
  }, [points, activeIds, scoreMap, focalId, highlightedId, getBaseTransform])

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
    // Hit radius tracks the current dot size (zoom-dependent) with a floor so
    // tiny dots remain clickable when zoomed out.
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
      const closest = findClosestPoint(mx, my)

      if (closest) {
        if (dblClickTimerRef.current && dblClickTimerRef.current.id === closest.id) {
          clearTimeout(dblClickTimerRef.current.timer)
          dblClickTimerRef.current = null
          onPointDoubleClick?.(closest.id)
        } else {
          if (dblClickTimerRef.current) clearTimeout(dblClickTimerRef.current.timer)
          const timer = setTimeout(() => {
            dblClickTimerRef.current = null
            onPointClick(closest.id)
          }, 250)
          dblClickTimerRef.current = { id: closest.id, timer }
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
        <span className="legend-item legend-hint">
          clic = similars | doble clic = detall
        </span>
      </div>
    </div>
  )
}
