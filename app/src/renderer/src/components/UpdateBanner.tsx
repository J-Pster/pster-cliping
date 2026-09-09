import { useEffect, useState } from 'react'
import type { UpdateStatus } from '@shared/ipc-contract'

export default function UpdateBanner(): React.JSX.Element | null {
  const [status, setStatus] = useState<UpdateStatus | null>(null)

  useEffect(() => {
    return window.api.app.onUpdateStatus(setStatus)
  }, [])

  if (!status || status.state === 'checking' || status.state === 'not-available') return null

  if (status.state === 'downloading') {
    return (
      <div className="lu-banner lu-banner--info">
        Baixando atualizacao... {status.percent}%
      </div>
    )
  }

  if (status.state === 'downloaded') {
    return (
      <div
        className="lu-banner lu-banner--info"
        style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}
      >
        <span>Atualizacao {status.version} pronta.</span>
        <button
          type="button"
          className="btn btn-secondary"
          onClick={() => window.api.app.quitAndInstall()}
        >
          Reiniciar e atualizar
        </button>
      </div>
    )
  }

  if (status.state === 'error') {
    return <div className="lu-banner lu-banner--error">Falha ao checar atualizacao: {status.message}</div>
  }

  return null
}
