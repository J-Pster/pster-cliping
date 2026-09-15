import { USD_BRL_FALLBACK_RATE } from '../shared/pricing'

/** API publica, gratuita, sem chave, mantida pelo mesmo ecossistema brasileiro do
 * projeto - devolve a cotacao comercial USD/BRL mais recente do Banco Central. */
const EXCHANGE_RATE_URL = 'https://economia.awesomeapi.com.br/json/last/USD-BRL'

const FETCH_TIMEOUT_MS = 4000
const CACHE_TTL_MS = 60 * 60 * 1000 // 1h: cotacao nao muda rapido o bastante pra justificar buscar de novo a cada evento de consumo.

interface AwesomeApiUsdBrlResponse {
  USDBRL?: { bid?: string }
}

let cachedRate: { rate: number; fetchedAt: number } | null = null

async function fetchLiveRate(): Promise<number> {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS)
  try {
    const response = await fetch(EXCHANGE_RATE_URL, { signal: controller.signal })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const payload = (await response.json()) as AwesomeApiUsdBrlResponse
    const bid = Number(payload.USDBRL?.bid)
    if (!Number.isFinite(bid) || bid <= 0) throw new Error('resposta sem "bid" valido')
    return bid
  } finally {
    clearTimeout(timeout)
  }
}

/** Cotacao USD/BRL pra converter o custo estimado do TokenUsagePanel. Cacheada por
 * `CACHE_TTL_MS` (sucesso OU fallback, pra nao martelar a API a cada chamada de IPC
 * se ela estiver fora do ar). Nunca rejeita: uma cotacao desatualizada e melhor que
 * um painel de custo quebrado. */
export async function getUsdBrlRate(): Promise<number> {
  if (cachedRate && Date.now() - cachedRate.fetchedAt < CACHE_TTL_MS) {
    return cachedRate.rate
  }
  try {
    const rate = await fetchLiveRate()
    cachedRate = { rate, fetchedAt: Date.now() }
    return rate
  } catch (exc) {
    console.warn(
      'Nao foi possivel obter a cotacao USD/BRL em tempo real; usando fallback estatico.',
      exc
    )
    cachedRate = { rate: USD_BRL_FALLBACK_RATE, fetchedAt: Date.now() }
    return USD_BRL_FALLBACK_RATE
  }
}
