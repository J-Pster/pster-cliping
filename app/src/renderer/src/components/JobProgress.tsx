import type { EngineProgressEvent } from '@shared/ipc-contract'

const PHASE_LABEL: Record<string, string> = {
  download: 'Baixando video...',
  download_done: 'Video baixado',
  transcribe: 'Transcrevendo audio...',
  transcribe_done: 'Transcricao concluida',
  select: 'Selecionando trechos com IA...',
  main_thumbnail: 'Gerando thumbnail do video principal...'
}

interface Props {
  event: EngineProgressEvent | null
  /** Rotulo do que esta sendo contado na barra (ex. "clipe", "video"). */
  unitLabel?: string
}

export default function JobProgress({ event, unitLabel = 'clipe' }: Props): React.JSX.Element | null {
  if (!event) return null

  const total = event.total
  const index = event.index
  const hasCount = typeof total === 'number' && total > 0

  const message =
    event.message ??
    (event.phase ? PHASE_LABEL[event.phase] : undefined) ??
    (event.event === 'clip_failed' ? `Falhou: ${event.stage ?? 'etapa desconhecida'}` : undefined)

  const percent = hasCount
    ? Math.min(100, Math.round(((event.event === 'clip_done' ? index ?? 0 : (index ?? 1) - 1) / total!) * 100))
    : null

  return (
    <div className="lu-job-progress">
      {hasCount && (
        <div className="lu-progress-track">
          <div className="lu-progress-fill" style={{ width: `${percent}%` }} />
        </div>
      )}
      <p className="lu-job-progress__label">
        {hasCount && (
          <span className="lu-job-progress__count">
            {Math.min(index ?? 0, total!)} de {total} {unitLabel}
            {total === 1 ? '' : 's'}
          </span>
        )}
        {message && <span>{hasCount ? ` - ${message}` : message}</span>}
      </p>
    </div>
  )
}
