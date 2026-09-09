import { useMemo } from 'react'
import type { EngineLogEvent } from '@shared/ipc-contract'

interface ClipResult {
  clipId: string
  format: string
  directory: string
  reviewStatus: string
}

interface ClipResultsListProps {
  lines: EngineLogEvent[]
}

const RESULT_LINE = /^(.+?) \[(.+?)\] -> (.+?) \((.+?)\)$/

function parseResults(lines: EngineLogEvent[]): ClipResult[] {
  const results: ClipResult[] = []
  for (const event of lines) {
    const match = RESULT_LINE.exec(event.line.trim())
    if (match) {
      results.push({
        clipId: match[1],
        format: match[2],
        directory: match[3],
        reviewStatus: match[4]
      })
    }
  }
  return results
}

export default function ClipResultsList({ lines }: ClipResultsListProps): React.JSX.Element {
  const results = useMemo(() => parseResults(lines), [lines])

  if (results.length === 0) {
    return <p className="lu-results-empty">Nenhum clipe exportado ainda.</p>
  }

  return (
    <div className="lu-results-list">
      {results.map((result, index) => (
        <div className="lu-results-row" key={`${result.clipId}-${index}`}>
          <div className="lu-results-row__info">
            <span className="lu-results-row__id">
              {result.clipId} [{result.format}]
            </span>
            <span className="lu-results-row__meta">
              {result.directory} · {result.reviewStatus}
            </span>
          </div>
          <button
            type="button"
            className="btn btn-outline btn-sm"
            onClick={() => window.api.dialogs.openInFileManager(result.directory)}
          >
            Abrir pasta
          </button>
        </div>
      ))}
    </div>
  )
}
