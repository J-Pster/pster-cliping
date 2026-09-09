import { useEffect, useRef } from 'react'
import type { EngineLogEvent } from '@shared/ipc-contract'

interface LogConsoleProps {
  lines: EngineLogEvent[]
  exitCode: number | null | undefined
  exited: boolean
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
        <div
          key={index}
          className={event.stream === 'stderr' ? 'lu-log-line--stderr' : undefined}
        >
          {event.line}
        </div>
      ))}
      {exited && (
        <div className="lu-log-line--exit">Processo encerrado (codigo {exitCode ?? 'desconhecido'})</div>
      )}
    </div>
  )
}
