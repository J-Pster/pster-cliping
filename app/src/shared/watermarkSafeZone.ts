import type { WatermarkFormatState } from './ipc-contract'

/**
 * Zonas onde a interface da propria plataforma cobre o video, em fracao (0-1) do
 * quadro. Cada zona pode ter mais de um retangulo porque o layout real nao e um
 * unico canto: TikTok/Reels/Shorts tem uma FAIXA de legenda embaixo (largura toda) MAIS
 * uma COLUNA de icones na direita que comeca mais acima que a faixa.
 *
 * Valores aproximados a partir do layout documentado dessas plataformas (coluna de
 * icones ~12% da largura, faixa de legenda/usuario ~18-20% da altura; YouTube reserva
 * so a faixa fina de controles do player embaixo, ~10% da altura). Puramente pra guiar
 * o usuario e travar o arrasto, nao precisa ser pixel-perfect - ajustaveis aqui se as
 * plataformas mudarem o layout delas.
 */
export interface SafeZoneRect {
  left: number
  top: number
  right: number
  bottom: number
}

export interface SafeZoneExclusion {
  rects: SafeZoneRect[]
  label: string
}

/** TikTok/Reels/Shorts: coluna de icones (curtir/comentar/compartilhar/perfil) na
 * direita + faixa de legenda/usuario/som embaixo. */
export const SHORT_SAFE_ZONE: SafeZoneExclusion = {
  rects: [
    { left: 0, top: 0.82, right: 1, bottom: 1 }, // legenda, usuario, musica
    { left: 0.88, top: 0.42, right: 1, bottom: 1 } // coluna de icones
  ],
  label: 'icones e legenda do TikTok / Reels / Shorts'
}

/** YouTube: barra de progresso + controles do player, faixa fina embaixo. */
export const LONG_SAFE_ZONE: SafeZoneExclusion = {
  rects: [{ left: 0, top: 0.9, right: 1, bottom: 1 }],
  label: 'barra de controles do player do YouTube'
}

const MIN_WIDTH_FRACTION = 0.05
const MAX_WIDTH_FRACTION = 0.6

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

/** Altura renderizada da logo em fracao da altura do quadro. Os dois eixos usam escalas
 * absolutas diferentes quando o quadro nao e quadrado, entao a conversao passa por
 * pixel: largura em px = widthFraction * frameWidth, altura em px = largura em px *
 * aspect, e so entao volta pra fracao dividindo por frameHeight. */
function heightFraction(widthFraction: number, aspect: number, frameWidth: number, frameHeight: number): number {
  return (widthFraction * frameWidth * aspect) / frameHeight
}

export function logoBox(
  state: WatermarkFormatState,
  aspect: number,
  frameWidth: number,
  frameHeight: number
): SafeZoneRect {
  const heightFrac = heightFraction(state.widthFraction, aspect, frameWidth, frameHeight)
  return {
    left: state.x - state.widthFraction / 2,
    right: state.x + state.widthFraction / 2,
    top: state.y - heightFrac / 2,
    bottom: state.y + heightFrac / 2
  }
}

function rectsOverlap(a: SafeZoneRect, b: SafeZoneRect): boolean {
  return a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top
}

export function overlapsZone(box: SafeZoneRect, zone: SafeZoneExclusion): boolean {
  return zone.rects.some((rect) => rectsOverlap(box, rect))
}

/** Mantem a logo inteira dentro do quadro (nunca sai da area visivel do video). */
export function clampToFrame(
  state: WatermarkFormatState,
  aspect: number,
  frameWidth: number,
  frameHeight: number
): WatermarkFormatState {
  const heightFrac = heightFraction(state.widthFraction, aspect, frameWidth, frameHeight)
  return {
    ...state,
    x: clamp(state.x, state.widthFraction / 2, 1 - state.widthFraction / 2),
    y: clamp(state.y, heightFrac / 2, 1 - heightFrac / 2)
  }
}

/**
 * Resolve um movimento de arraste respeitando a zona reservada: tenta o movimento
 * inteiro, depois so a componente horizontal, depois so a vertical (permite "deslizar"
 * ao longo da borda da zona em vez de travar de vez), e so rejeita de fato (mantem a
 * posicao atual) se nenhuma das tres opcoes escapar de TODOS os retangulos da zona.
 */
export function resolveDragPosition(
  current: WatermarkFormatState,
  proposed: WatermarkFormatState,
  aspect: number,
  frameWidth: number,
  frameHeight: number,
  zone: SafeZoneExclusion
): WatermarkFormatState {
  const attempt = (candidate: WatermarkFormatState): WatermarkFormatState | null => {
    const clamped = clampToFrame(candidate, aspect, frameWidth, frameHeight)
    const box = logoBox(clamped, aspect, frameWidth, frameHeight)
    return overlapsZone(box, zone) ? null : clamped
  }

  return (
    attempt(proposed) ??
    attempt({ ...proposed, y: current.y }) ??
    attempt({ ...proposed, x: current.x }) ??
    current
  )
}

/** Maior widthFraction que ainda escapa de TODOS os retangulos da zona nesta posicao
 * (x,y fixos). Com multiplos retangulos nao ha formula fechada simples (o tamanho seguro
 * pra um retangulo pode nao ser seguro pra outro), entao desce de MAX_WIDTH_FRACTION em
 * passos pequenos ate achar um tamanho sem overlap - 56 passos no maximo, barato o
 * bastante pra rodar a cada evento de drag/slider. */
export function maxWidthFractionAt(
  x: number,
  y: number,
  aspect: number,
  frameWidth: number,
  frameHeight: number,
  zone: SafeZoneExclusion,
  requested: number = MAX_WIDTH_FRACTION
): number {
  const step = 0.01
  let candidate = clamp(requested, MIN_WIDTH_FRACTION, MAX_WIDTH_FRACTION)
  while (candidate > MIN_WIDTH_FRACTION) {
    const box = logoBox({ x, y, widthFraction: candidate }, aspect, frameWidth, frameHeight)
    if (!overlapsZone(box, zone)) {
      return candidate
    }
    candidate -= step
  }
  return MIN_WIDTH_FRACTION
}

export const WATERMARK_SIZE_BOUNDS = { min: MIN_WIDTH_FRACTION, max: MAX_WIDTH_FRACTION }
