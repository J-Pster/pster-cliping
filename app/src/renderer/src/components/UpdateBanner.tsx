import { useEffect, useState } from 'react'
import { ArrowUpCircle, TriangleAlert, X } from 'lucide-react'
import type { UpdateStatus } from '@shared/ipc-contract'

/** Barra fixa no rodape, por cima de tudo (Header/Sidebar/conteudo): so aparece
 * quando ha algo acionavel (atualizacao disponivel, baixando, pronta, ou erro).
 * 'checking' e 'not-available' ficam silenciosos aqui, o feedback deles mora na
 * tela Settings (botao "Verificar atualizacoes"). */
export default function UpdateBanner({
  onVisibleChange
}: {
  onVisibleChange?: (visible: boolean) => void
}): React.JSX.Element | null {
  const [status, setStatus] = useState<UpdateStatus | null>(null)
  const [dismissedFor, setDismissedFor] = useState<string | null>(null)

  useEffect(() => {
    return window.api.app.onUpdateStatus((next) => {
      setStatus(next)
      setDismissedFor(null)
    })
  }, [])

  const visible =
    !!status &&
    status.state !== 'checking' &&
    status.state !== 'not-available' &&
    dismissedFor !== status.state

  useEffect(() => {
    onVisibleChange?.(visible)
  }, [visible, onVisibleChange])

  if (!visible || !status) return null

  const dismissible = status.state !== 'downloading'

  return (
    <div className="lu-update-bar" role="status">
      <span className="lu-update-bar__icon" aria-hidden="true">
        {status.state === 'error' ? (
          <TriangleAlert size={18} strokeWidth={2} />
        ) : (
          <ArrowUpCircle size={18} strokeWidth={2} />
        )}
      </span>

      <div className="lu-update-bar__body">
        {status.state === 'downloading' && (
          <>
            <span className="lu-update-bar__text">Baixando atualizacao... {status.percent}%</span>
            <div className="lu-update-bar__track">
              <div className="lu-update-bar__fill" style={{ width: `${status.percent}%` }} />
            </div>
          </>
        )}
        {status.state === 'available' && (
          <span className="lu-update-bar__text">
            Atualizacao {status.version} disponivel, baixando em segundo plano...
          </span>
        )}
        {status.state === 'downloaded' && (
          <span className="lu-update-bar__text">
            Atualizacao {status.version} pronta pra instalar.
          </span>
        )}
        {status.state === 'error' && (
          <span className="lu-update-bar__text">Falha ao verificar atualizacao: {status.message}</span>
        )}
      </div>

      <div className="lu-update-bar__actions">
        {status.state === 'downloaded' && (
          <button
            type="button"
            className="btn btn-primary btn-sm"
            onClick={() => window.api.app.quitAndInstall()}
          >
            Reiniciar e atualizar
          </button>
        )}
        {dismissible && (
          <button
            type="button"
            className="lu-update-bar__dismiss"
            onClick={() => setDismissedFor(status.state)}
            aria-label="Dispensar"
            title="Dispensar"
          >
            <X size={16} strokeWidth={2} />
          </button>
        )}
      </div>
    </div>
  )
}
