import type { UsageProvider } from '@shared/ipc-contract'
import type { UsageTotals } from '../hooks/useTokenUsage'

const PROVIDER_LABELS: Record<UsageProvider, string> = {
  claude: 'Claude',
  gemini: 'Gemini',
  elevenlabs: 'ElevenLabs'
}

// Ordem fixa (nao a ordem de chegada do primeiro evento): mantem o painel estavel
// visualmente entre execucoes diferentes, em vez de reordenar a cada rodada.
const PROVIDER_ORDER: UsageProvider[] = ['claude', 'gemini', 'elevenlabs']

function formatNumber(value: number): string {
  return Math.round(value).toLocaleString('pt-BR')
}

interface TokenUsagePanelProps {
  totals: UsageTotals
}

export default function TokenUsagePanel({ totals }: TokenUsagePanelProps): React.JSX.Element {
  const providers = PROVIDER_ORDER.filter((provider) => totals[provider])

  return (
    <div className="lu-usage-panel">
      <h3 className="lu-usage-panel__title">Consumo</h3>
      {providers.length === 0 && (
        <p className="lu-usage-panel__empty">Nenhuma chamada registrada ainda.</p>
      )}
      {providers.map((provider) => {
        const usage = totals[provider]
        if (!usage) return null
        const totalTokens = usage.inputTokens + usage.outputTokens
        return (
          <div key={provider} className="lu-usage-panel__provider">
            <div className="lu-usage-panel__provider-name">{PROVIDER_LABELS[provider]}</div>
            {totalTokens > 0 && (
              <div className="lu-usage-panel__line">
                {formatNumber(totalTokens)} tokens
                <span className="lu-usage-panel__fine">
                  {' '}
                  ({formatNumber(usage.inputTokens)} in / {formatNumber(usage.outputTokens)} out)
                </span>
              </div>
            )}
            {usage.images > 0 && (
              <div className="lu-usage-panel__line">{formatNumber(usage.images)} imagem(ns)</div>
            )}
            {usage.audioSeconds > 0 && (
              <div className="lu-usage-panel__line">
                {formatNumber(usage.audioSeconds)}s de audio
              </div>
            )}
            <div className="lu-usage-panel__fine">{usage.calls} chamada(s)</div>
          </div>
        )
      })}
    </div>
  )
}
