import { useEffect, useRef } from 'react'
import type { EngineLogEvent } from '@shared/ipc-contract'

interface LogConsoleProps {
  lines: EngineLogEvent[]
  exitCode: number | null | undefined
  exited: boolean
}

// Formato do logging padrao do Python: "LEVELNAME:logger.name:mensagem" (ver
// logging.basicConfig no engine). A cor da linha segue esse nivel, nao o stream
// (stdout/stderr): o logging do Python manda INFO pra stderr por padrao, entao colorir
// por stream deixava todo log informativo vermelho, como se fosse erro.
const LOG_LEVEL_PATTERN = /^(DEBUG|INFO|WARNING|ERROR|CRITICAL):/

function lineClassName(event: EngineLogEvent): string | undefined {
  const level = event.line.match(LOG_LEVEL_PATTERN)?.[1]
  if (level === 'ERROR' || level === 'CRITICAL') return 'lu-log-line--error'
  if (level === 'WARNING') return 'lu-log-line--warn'
  if (level === 'DEBUG' || level === 'INFO') return undefined // cor padrao (texto claro)

  // stderr sem prefixo de nivel (traceback, excecao crua do Python): erro de verdade.
  return event.stream === 'stderr' ? 'lu-log-line--error' : undefined
}

export default function LogConsole({ lines, exitCode, exited }: LogConsoleProps): React.JSX.Element {
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const el = scrollRef.current
    if (el) {
      el.scrollTop = el.scrollHeight
    }
  }, [lines.length, exited])

  return (
    <div className="lu-log-console" ref={scrollRef}>
      {lines.length === 0 && !exited && (
        <div className="lu-log-console__empty">Aguardando inicio do processo...</div>
      )}
      {lines.map((event, index) => (
        <div key={index} className={lineClassName(event)}>
          {event.line}
        </div>
      ))}
      {exited && (
        <div className="lu-log-line--exit">Processo encerrado (codigo {exitCode ?? 'desconhecido'})</div>
      )}
    </div>
  )
}
