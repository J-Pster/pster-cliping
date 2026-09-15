import { useEffect, useState } from 'react'
import { USD_BRL_FALLBACK_RATE } from '@shared/pricing'

/** Cotacao USD/BRL pra converter o custo estimado (ver useTokenUsage) na exibicao do
 * TokenUsagePanel. Busca uma vez por montagem via IPC (main tem cache proprio de 1h,
 * ver main/pricing.ts); comeca com o fallback estatico pra nunca deixar o painel sem
 * numero enquanto o IPC nao responde. */
export function useUsdBrlRate(): number {
  const [rate, setRate] = useState(USD_BRL_FALLBACK_RATE)

  useEffect(() => {
    let cancelled = false
    window.api.pricing
      .getUsdBrlRate()
      .then((value) => {
        if (!cancelled) setRate(value)
      })
      .catch(() => {
        // window.api.pricing.getUsdBrlRate ja tem fallback proprio no main; um reject
        // aqui so pode ser falha do canal IPC em si, nao da cotacao - fica no fallback.
      })
    return () => {
      cancelled = true
    }
  }, [])

  return rate
}
