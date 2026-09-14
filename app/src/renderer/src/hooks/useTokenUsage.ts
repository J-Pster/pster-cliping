import { useCallback, useState } from 'react'
import type { EngineProgressEvent, UsageProvider } from '@shared/ipc-contract'

export interface ProviderUsageTotals {
  inputTokens: number
  outputTokens: number
  characters: number
  audioSeconds: number
  images: number
  calls: number
}

export type UsageTotals = Partial<Record<UsageProvider, ProviderUsageTotals>>

function emptyTotals(): ProviderUsageTotals {
  return { inputTokens: 0, outputTokens: 0, characters: 0, audioSeconds: 0, images: 0, calls: 0 }
}

/** Acumula os eventos de progresso "usage" (ver engine/src/clipador/usage.py) num total
 * por provedor, pra alimentar o contador em tempo real (TokenUsagePanel). Os demais
 * eventos de progresso (phase/plan/clip_*) sao ignorados aqui de proposito. */
export function useTokenUsage(): {
  totals: UsageTotals
  onProgressEvent: (event: EngineProgressEvent) => void
  reset: () => void
} {
  const [totals, setTotals] = useState<UsageTotals>({})

  const onProgressEvent = useCallback((event: EngineProgressEvent) => {
    if (event.event !== 'usage' || !event.provider) return
    const provider = event.provider
    setTotals((current) => {
      const previous = current[provider] ?? emptyTotals()
      return {
        ...current,
        [provider]: {
          inputTokens: previous.inputTokens + (event.inputTokens ?? 0),
          outputTokens: previous.outputTokens + (event.outputTokens ?? 0),
          characters: previous.characters + (event.characters ?? 0),
          audioSeconds: previous.audioSeconds + (event.audioSeconds ?? 0),
          images: previous.images + (event.images ?? 0),
          calls: previous.calls + 1
        }
      }
    })
  }, [])

  const reset = useCallback(() => setTotals({}), [])

  return { totals, onProgressEvent, reset }
}
