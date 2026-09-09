import { useEffect, useRef, useState } from 'react'
import type { WatermarkFormatState } from '@shared/ipc-contract'
import {
  clampToFrame,
  maxWidthFractionAt,
  resolveDragPosition,
  WATERMARK_SIZE_BOUNDS,
  type SafeZoneExclusion
} from '@shared/watermarkSafeZone'

const CANVAS_MAX_WIDTH = 260
const ZONE_FILL = 'rgba(239, 68, 68, 0.16)'
const ZONE_STROKE = 'rgba(239, 68, 68, 0.6)'
const ZONE_MARKER = 'rgba(239, 68, 68, 0.9)'
const CORNER_TRIANGLE_SIZE = 12

interface DragStart {
  pointerId: number
  cssX: number
  cssY: number
  state: WatermarkFormatState
}

interface Props {
  label: string
  frameWidth: number
  frameHeight: number
  sourceImageUrl: string | null
  state: WatermarkFormatState
  onStateChange: (next: WatermarkFormatState) => void
  bakedPreviewUrl: string | null
  onSave: (pngBytes: ArrayBuffer) => Promise<void>
  saving: boolean
  safeZone: SafeZoneExclusion
}

function drawCheckerboard(ctx: CanvasRenderingContext2D, width: number, height: number): void {
  const cell = 8
  for (let y = 0; y < height; y += cell) {
    for (let x = 0; x < width; x += cell) {
      const isEven = (Math.floor(x / cell) + Math.floor(y / cell)) % 2 === 0
      ctx.fillStyle = isEven ? '#e8e8e8' : '#d8d8d8'
      ctx.fillRect(x, y, cell, cell)
    }
  }
}

/** Marcador de canto triangular (nao arredondado): um triangulo solido apontando pra
 * dentro da zona reservada, nas duas pontas da borda superior dela. */
function drawCornerTriangle(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  pointsRight: boolean
): void {
  const size = CORNER_TRIANGLE_SIZE
  const dx = pointsRight ? size : -size
  ctx.fillStyle = ZONE_MARKER
  ctx.beginPath()
  ctx.moveTo(x, y)
  ctx.lineTo(x + dx, y)
  ctx.lineTo(x, y + size)
  ctx.closePath()
  ctx.fill()
}

function drawSafeZone(
  ctx: CanvasRenderingContext2D,
  zone: SafeZoneExclusion,
  canvasWidth: number,
  canvasHeight: number
): void {
  for (const rect of zone.rects) {
    const rectX = rect.left * canvasWidth
    const rectY = rect.top * canvasHeight
    const rectWidth = (rect.right - rect.left) * canvasWidth
    const rectHeight = (rect.bottom - rect.top) * canvasHeight

    ctx.fillStyle = ZONE_FILL
    ctx.fillRect(rectX, rectY, rectWidth, rectHeight)
    ctx.strokeStyle = ZONE_STROKE
    ctx.setLineDash([4, 3])
    ctx.strokeRect(rectX, rectY, rectWidth, rectHeight)
    ctx.setLineDash([])

    // Marcadores nas duas pontas da borda SUPERIOR do retangulo (onde a zona comeca,
    // vindo de cima): a direita e a esquerda coincidem com a borda do quadro quando o
    // retangulo vai ate la, e o desenho so fica parcialmente cortado, o que ainda
    // comunica bem "a zona comeca aqui".
    drawCornerTriangle(ctx, rectX, rectY, true)
    drawCornerTriangle(ctx, rectX + rectWidth, rectY, false)
  }
}

export default function WatermarkFormatEditor({
  label,
  frameWidth,
  frameHeight,
  sourceImageUrl,
  state,
  onStateChange,
  bakedPreviewUrl,
  onSave,
  saving,
  safeZone
}: Props): React.JSX.Element {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const imageRef = useRef<HTMLImageElement | null>(null)
  const dragRef = useRef<DragStart | null>(null)
  const [imageLoaded, setImageLoaded] = useState(false)
  const [baking, setBaking] = useState(false)
  const [bakeError, setBakeError] = useState<string | null>(null)
  const [dragging, setDragging] = useState(false)

  const frameAspect = frameHeight / frameWidth
  const canvasCssWidth = CANVAS_MAX_WIDTH
  const canvasCssHeight = Math.round(CANVAS_MAX_WIDTH * frameAspect)

  useEffect(() => {
    if (!sourceImageUrl) {
      imageRef.current = null
      setImageLoaded(false)
      return
    }
    const img = new Image()
    img.onload = () => {
      imageRef.current = img
      setImageLoaded(true)
    }
    img.onerror = () => {
      imageRef.current = null
      setImageLoaded(false)
    }
    img.src = sourceImageUrl
    return () => {
      img.onload = null
      img.onerror = null
    }
  }, [sourceImageUrl])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    ctx.clearRect(0, 0, canvasCssWidth, canvasCssHeight)
    drawCheckerboard(ctx, canvasCssWidth, canvasCssHeight)
    drawSafeZone(ctx, safeZone, canvasCssWidth, canvasCssHeight)

    const img = imageRef.current
    if (img && imageLoaded) {
      const renderedWidth = state.widthFraction * canvasCssWidth
      const renderedHeight = renderedWidth * (img.naturalHeight / img.naturalWidth)
      const left = state.x * canvasCssWidth - renderedWidth / 2
      const top = state.y * canvasCssHeight - renderedHeight / 2
      ctx.drawImage(img, left, top, renderedWidth, renderedHeight)
    }
  }, [state, imageLoaded, canvasCssWidth, canvasCssHeight, safeZone])

  function imageAspect(): number | null {
    const img = imageRef.current
    return img ? img.naturalHeight / img.naturalWidth : null
  }

  function handlePointerDown(event: React.PointerEvent<HTMLCanvasElement>): void {
    if (!sourceImageUrl) return
    const canvas = canvasRef.current
    if (!canvas) return
    canvas.setPointerCapture(event.pointerId)
    dragRef.current = {
      pointerId: event.pointerId,
      cssX: event.clientX,
      cssY: event.clientY,
      state
    }
    setDragging(true)
  }

  function handlePointerMove(event: React.PointerEvent<HTMLCanvasElement>): void {
    const drag = dragRef.current
    if (!drag || drag.pointerId !== event.pointerId) return
    const deltaCssX = event.clientX - drag.cssX
    const deltaCssY = event.clientY - drag.cssY
    const proposed: WatermarkFormatState = {
      ...drag.state,
      x: drag.state.x + deltaCssX / canvasCssWidth,
      y: drag.state.y + deltaCssY / canvasCssHeight
    }

    const aspect = imageAspect()
    const nextState = aspect
      ? resolveDragPosition(drag.state, proposed, aspect, frameWidth, frameHeight, safeZone)
      : proposed

    dragRef.current = { ...drag, cssX: event.clientX, cssY: event.clientY, state: nextState }
    onStateChange(nextState)
  }

  function endDrag(event: React.PointerEvent<HTMLCanvasElement>): void {
    const canvas = canvasRef.current
    if (canvas && canvas.hasPointerCapture(event.pointerId)) {
      canvas.releasePointerCapture(event.pointerId)
    }
    dragRef.current = null
    setDragging(false)
  }

  function handleWidthFractionChange(event: React.ChangeEvent<HTMLInputElement>): void {
    const requested = Number(event.target.value)
    const aspect = imageAspect()
    if (!aspect) {
      onStateChange({ ...state, widthFraction: requested })
      return
    }
    const nextWidthFraction = maxWidthFractionAt(
      state.x,
      state.y,
      aspect,
      frameWidth,
      frameHeight,
      safeZone,
      requested
    )
    const nextState = clampToFrame(
      { ...state, widthFraction: nextWidthFraction },
      aspect,
      frameWidth,
      frameHeight
    )
    onStateChange(nextState)
  }

  async function handleSave(): Promise<void> {
    const img = imageRef.current
    if (!img) return
    setBakeError(null)
    setBaking(true)
    try {
      const offscreen = document.createElement('canvas')
      offscreen.width = frameWidth
      offscreen.height = frameHeight
      const ctx = offscreen.getContext('2d')
      if (!ctx) {
        throw new Error('Não foi possível criar o contexto de renderização')
      }
      const renderedWidth = state.widthFraction * frameWidth
      const renderedHeight = renderedWidth * (img.naturalHeight / img.naturalWidth)
      const left = state.x * frameWidth - renderedWidth / 2
      const top = state.y * frameHeight - renderedHeight / 2
      ctx.drawImage(img, left, top, renderedWidth, renderedHeight)

      const pngBytes = await new Promise<ArrayBuffer>((resolve, reject) => {
        offscreen.toBlob((blob) => {
          if (!blob) {
            reject(new Error('Falha ao gerar o PNG final'))
            return
          }
          blob.arrayBuffer().then(resolve, reject)
        }, 'image/png')
      })

      await onSave(pngBytes)
    } catch (error) {
      setBakeError(error instanceof Error ? error.message : String(error))
    } finally {
      setBaking(false)
    }
  }

  const isSaving = saving || baking

  return (
    <div className="lu-watermark-editor">
      <h3 className="lu-watermark-editor__label">{label}</h3>
      <div className="lu-watermark-editor__body">
        <canvas
          ref={canvasRef}
          width={canvasCssWidth}
          height={canvasCssHeight}
          className="lu-watermark-editor__canvas"
          style={{ cursor: dragging ? 'grabbing' : 'grab' }}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={endDrag}
          onPointerLeave={endDrag}
        />
        <div className="lu-watermark-editor__controls">
          <div className="lu-field">
            <label className="lu-label">Tamanho da logo</label>
            <input
              type="range"
              min={WATERMARK_SIZE_BOUNDS.min}
              max={WATERMARK_SIZE_BOUNDS.max}
              step={0.01}
              value={state.widthFraction}
              onChange={handleWidthFractionChange}
              className="lu-watermark-editor__range"
            />
            <p className="lu-hint">Arraste a logo dentro do quadro para posicionar.</p>
            <p className="lu-hint">
              A área marcada em vermelho é onde fica {safeZone.label}: a logo não entra
              nela.
            </p>
          </div>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={handleSave}
            disabled={isSaving || !sourceImageUrl}
          >
            {isSaving ? 'Salvando...' : 'Salvar posição'}
          </button>
          {bakeError && <p className="lu-error">{bakeError}</p>}
          {bakedPreviewUrl && (
            <div className="lu-watermark-editor__preview">
              <p className="lu-hint">Prévia final:</p>
              <img
                src={bakedPreviewUrl}
                alt={`Prévia final da marca d'água - ${label}`}
                className="lu-watermark-editor__preview-image"
              />
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
