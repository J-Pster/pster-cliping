/**
 * Estimativa de custo (USD e BRL) do consumo de tokens/API reportado pelo engine (ver
 * `engine/src/clipador/usage.py`). Os precos abaixo sao uma tabela estatica, mantida a
 * mao, dos modelos que o engine usa HOJE por (provider, operation) - nao ha API de
 * precos dos provedores para consultar em tempo real, entao isso e sempre uma
 * aproximacao ("~"), nunca uma fatura exata.
 *
 * Se o modelo de algum provider mudar (ver as constantes MODEL_ID citadas abaixo),
 * atualize os numeros aqui tambem - nada neste arquivo le o codigo do engine em
 * tempo de execucao.
 */

export type CostProvider = 'claude' | 'gemini' | 'elevenlabs'

export interface UsageUnits {
  inputTokens?: number
  outputTokens?: number
  images?: number
  audioSeconds?: number
}

const MILLION = 1_000_000

// claude-sonnet-5 (engine/src/clipador/llm/claude_client.py::MODEL_ID).
// Fonte: https://platform.claude.com/docs/en/about-claude/pricing (checado 2026-09-15).
const CLAUDE_TEXT_INPUT_PER_MTOK = 2.0
const CLAUDE_TEXT_OUTPUT_PER_MTOK = 10.0

// gemini-3.1-pro-preview, tier <=200k tokens de contexto (default; sobrescrevivel via
// CLIPADOR_GEMINI_TEXT_MODEL, ver engine/src/clipador/llm/gemini_client.py::MODEL_ID).
// Fonte: https://ai.google.dev/gemini-api/docs/pricing (checado 2026-09-15).
const GEMINI_TEXT_INPUT_PER_MTOK = 2.0
const GEMINI_TEXT_OUTPUT_PER_MTOK = 12.0

// gemini-3.1-flash-image-preview (engine/src/clipador/thumbnail/ai_thumbnail.py::MODEL_ID).
// Cobranca por token quando a resposta traz usage_metadata; per-image e o fallback pra
// quando o Gemini nao devolve contagem de token pra imagem (ocorre em parte das chamadas).
const GEMINI_IMAGE_INPUT_PER_MTOK = 0.5
const GEMINI_IMAGE_OUTPUT_PER_MTOK = 60.0
const GEMINI_IMAGE_FALLBACK_PER_IMAGE = 0.067

// scribe_v2 (engine/src/clipador/transcribe/elevenlabs_transcriber.py::MODEL_ID).
// Fonte: https://elevenlabs.io/pricing/api (checado 2026-09-15).
const ELEVENLABS_TRANSCRIBE_PER_HOUR = 0.22

/** Cotacao USD/BRL usada quando a consulta dinamica (ver `main/pricing.ts`) falha ou
 * demora demais. Atualizada a mao; nao precisa ser exata, so uma aproximacao razoavel
 * (cotacao de referencia: 2026-09-15). */
export const USD_BRL_FALLBACK_RATE = 5.15

/** Estima o custo em USD de UM evento "usage" (ver clipador.usage.record), a partir do
 * provider/operation/unidades exatos daquela chamada - nao de um total ja agregado,
 * porque gemini "text" e "thumbnail_image" tem precos bem diferentes e nao dao pra
 * misturar num unico calculo. */
export function estimateCostUsd(
  provider: CostProvider,
  operation: string | undefined,
  units: UsageUnits
): number {
  const inputTokens = units.inputTokens ?? 0
  const outputTokens = units.outputTokens ?? 0
  const images = units.images ?? 0
  const audioSeconds = units.audioSeconds ?? 0

  if (provider === 'claude') {
    return (
      (inputTokens / MILLION) * CLAUDE_TEXT_INPUT_PER_MTOK +
      (outputTokens / MILLION) * CLAUDE_TEXT_OUTPUT_PER_MTOK
    )
  }

  if (provider === 'gemini') {
    if (operation === 'thumbnail_image') {
      if (outputTokens > 0) {
        return (
          (inputTokens / MILLION) * GEMINI_IMAGE_INPUT_PER_MTOK +
          (outputTokens / MILLION) * GEMINI_IMAGE_OUTPUT_PER_MTOK
        )
      }
      return images * GEMINI_IMAGE_FALLBACK_PER_IMAGE
    }
    return (
      (inputTokens / MILLION) * GEMINI_TEXT_INPUT_PER_MTOK +
      (outputTokens / MILLION) * GEMINI_TEXT_OUTPUT_PER_MTOK
    )
  }

  return (audioSeconds / 3600) * ELEVENLABS_TRANSCRIBE_PER_HOUR
}
