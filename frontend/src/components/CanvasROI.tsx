/**
 * uriv-syncboard / frontend / src / components / CanvasROI.tsx
 * ─────────────────────────────────────────────────────────────
 * Renders the live video feed on an HTML5 <canvas>.
 * Lets the user click-and-drag to define a Region of Interest (ROI).
 *
 * Emits:
 *   onRoiSet(x, y, w, h)   — pixel coords in the *original frame* space
 *   onRoiClear()
 *
 * Visual layers (bottom → top)
 *   1. Live JPEG frame (drawn via drawImage)
 *   2. Confirmed ROI — green dashed rectangle
 *   3. Drag preview  — red dashed rectangle while drawing
 *   4. Flash overlay — white flash when BOARD_CLEARED fires
 */

import { useCallback, useEffect, useRef, useState } from 'react'

interface Props {
  frameDataUrl:  string | null
  boardCleared:  boolean
  onRoiSet:      (x: number, y: number, w: number, h: number) => void
  onRoiClear:    () => void
}

interface Rect { x: number; y: number; w: number; h: number }

const MIN_DRAG_PX = 20

export default function CanvasROI({
  frameDataUrl,
  boardCleared,
  onRoiSet,
  onRoiClear,
}: Props) {
  const canvasRef  = useRef<HTMLCanvasElement>(null)
  const imgRef     = useRef<HTMLImageElement>(new window.Image())

  // ROI state (canvas pixel coords)
  const [confirmedRoi, setConfirmedRoi] = useState<Rect | null>(null)
  const dragStart = useRef<{ x: number; y: number } | null>(null)
  const [dragRect, setDragRect]         = useState<Rect | null>(null)

  // Flash overlay on board-clear
  const [flash, setFlash] = useState(false)
  useEffect(() => {
    if (!boardCleared) return
    setFlash(true)
    const t = setTimeout(() => setFlash(false), 350)
    return () => clearTimeout(t)
  }, [boardCleared])

  // ── Update image whenever a new frame arrives ────────────────────────────
  useEffect(() => {
    if (!frameDataUrl) return
    imgRef.current.src = frameDataUrl
  }, [frameDataUrl])

  // ── Draw loop ────────────────────────────────────────────────────────────
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    let animId: number

    const draw = () => {
      animId = requestAnimationFrame(draw)
      const img = imgRef.current
      if (!img.complete || img.naturalWidth === 0) return

      const { width: cw, height: ch } = canvas

      // 1. Frame
      ctx.clearRect(0, 0, cw, ch)
      ctx.drawImage(img, 0, 0, cw, ch)

      // 2. Confirmed ROI (green dashed)
      if (confirmedRoi) {
        ctx.save()
        ctx.strokeStyle = '#4ade80'
        ctx.lineWidth   = 2
        ctx.setLineDash([6, 4])
        ctx.strokeRect(confirmedRoi.x, confirmedRoi.y, confirmedRoi.w, confirmedRoi.h)
        ctx.fillStyle = 'rgba(74,222,128,0.08)'
        ctx.fillRect(confirmedRoi.x, confirmedRoi.y, confirmedRoi.w, confirmedRoi.h)
        // Label
        ctx.setLineDash([])
        ctx.fillStyle   = '#4ade80'
        ctx.font        = 'bold 11px monospace'
        ctx.fillText('ROI', confirmedRoi.x + 4, confirmedRoi.y - 5)
        ctx.restore()
      }

      // 3. Drag preview (red dashed)
      if (dragRect) {
        ctx.save()
        ctx.strokeStyle = '#e94560'
        ctx.lineWidth   = 1.5
        ctx.setLineDash([5, 4])
        ctx.strokeRect(dragRect.x, dragRect.y, dragRect.w, dragRect.h)
        ctx.restore()
      }

      // 4. Board-clear flash
      if (flash) {
        ctx.save()
        ctx.fillStyle = 'rgba(255,255,255,0.35)'
        ctx.fillRect(0, 0, cw, ch)
        ctx.restore()
      }
    }

    draw()
    return () => cancelAnimationFrame(animId)
  }, [confirmedRoi, dragRect, flash])

  // ── Canvas size observer ──────────────────────────────────────────────────
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ro = new ResizeObserver(() => {
      canvas.width  = canvas.clientWidth
      canvas.height = canvas.clientHeight
    })
    ro.observe(canvas)
    return () => ro.disconnect()
  }, [])

  // ── Mouse event helpers ───────────────────────────────────────────────────
  const canvasToFrame = useCallback(
    (cx: number, cy: number): { x: number; y: number } => {
      const canvas = canvasRef.current!
      const img    = imgRef.current
      if (!img.naturalWidth) return { x: cx, y: cy }
      const sx = img.naturalWidth  / canvas.clientWidth
      const sy = img.naturalHeight / canvas.clientHeight
      return { x: Math.round(cx * sx), y: Math.round(cy * sy) }
    },
    [],
  )

  const onMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const rect = canvasRef.current!.getBoundingClientRect()
    dragStart.current = { x: e.clientX - rect.left, y: e.clientY - rect.top }
    setDragRect(null)
  }

  const onMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!dragStart.current) return
    const rect  = canvasRef.current!.getBoundingClientRect()
    const cx    = e.clientX - rect.left
    const cy    = e.clientY - rect.top
    const { x: sx, y: sy } = dragStart.current
    setDragRect({
      x: Math.min(sx, cx), y: Math.min(sy, cy),
      w: Math.abs(cx - sx), h: Math.abs(cy - sy),
    })
  }

  const onMouseUp = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!dragStart.current) return
    const rect = canvasRef.current!.getBoundingClientRect()
    const ex   = e.clientX - rect.left
    const ey   = e.clientY - rect.top
    const { x: sx, y: sy } = dragStart.current
    dragStart.current = null
    setDragRect(null)

    const cw = Math.abs(ex - sx)
    const ch = Math.abs(ey - sy)
    if (cw < MIN_DRAG_PX || ch < MIN_DRAG_PX) return  // too small — ignore

    const canvasRoi: Rect = {
      x: Math.min(sx, ex), y: Math.min(sy, ey), w: cw, h: ch,
    }
    setConfirmedRoi(canvasRoi)

    // Convert to frame space
    const tl = canvasToFrame(canvasRoi.x, canvasRoi.y)
    const br = canvasToFrame(canvasRoi.x + canvasRoi.w, canvasRoi.y + canvasRoi.h)
    onRoiSet(tl.x, tl.y, br.x - tl.x, br.y - tl.y)
  }

  const clearRoi = () => {
    setConfirmedRoi(null)
    setDragRect(null)
    dragStart.current = null
    onRoiClear()
  }

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="relative w-full h-full flex flex-col">
      {/* Canvas */}
      <canvas
        ref={canvasRef}
        className="flex-1 w-full cursor-crosshair rounded-md bg-black"
        onMouseDown={onMouseDown}
        onMouseMove={onMouseMove}
        onMouseUp={onMouseUp}
        onMouseLeave={() => {
          dragStart.current = null
          setDragRect(null)
        }}
      />

      {/* Toolbar */}
      <div className="flex items-center gap-2 mt-2">
        <span className="text-xs text-gray-400">
          {confirmedRoi
            ? `ROI: ${confirmedRoi.w}×${confirmedRoi.h}px (canvas)`
            : 'Drag to select board region'}
        </span>
        {confirmedRoi && (
          <button
            onClick={clearRoi}
            className="ml-auto text-xs bg-gray-700 hover:bg-gray-600 text-gray-200
                       px-3 py-1 rounded transition-colors"
          >
            ✂ Clear ROI
          </button>
        )}
      </div>

      {/* Board-cleared toast */}
      {boardCleared && (
        <div
          className="absolute top-3 left-1/2 -translate-x-1/2
                     bg-amber-500 text-black text-xs font-bold
                     px-4 py-1.5 rounded-full shadow-lg animate-bounce"
        >
          🧹 Board cleared — auto-saving page…
        </div>
      )}
    </div>
  )
}
