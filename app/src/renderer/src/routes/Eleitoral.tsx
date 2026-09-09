import { useEffect, useState } from 'react'
import type { EleitoralConfig, FeaturesConfig } from '@shared/ipc-contract'

type SaveState = 'idle' | 'saving' | 'saved' | 'error'

export default function EleitoralRoute(): React.JSX.Element {
  const [config, setConfig] = useState<FeaturesConfig | null>(null)
  const [enabled, setEnabled] = useState(false)
  const [text, setText] = useState('')
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [saveState, setSaveState] = useState<SaveState>('idle')
  const [saveError, setSaveError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    window.api.features
      .get()
      .then((loaded) => {
        if (!cancelled) {
          setConfig(loaded)
          setEnabled(loaded.eleitoral.enabled)
          setText(loaded.eleitoral.text)
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setLoadError(error instanceof Error ? error.message : String(error))
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [])

  const textMissing = text.trim().length === 0

  async function handleSave(): Promise<void> {
    if (!config) {
      return
    }
    setSaveState('saving')
    setSaveError(null)
    const eleitoral: EleitoralConfig = { enabled, text }
    try {
      await window.api.features.save({ ...config, eleitoral })
      setConfig((current) => (current ? { ...current, eleitoral } : current))
      setSaveState('saved')
    } catch (error) {
      setSaveState('error')
      setSaveError(error instanceof Error ? error.message : String(error))
    }
  }

  if (loading) {
    return <p className="lu-hint">Carregando configuracoes...</p>
  }

  return (
    <div className="lu-stack">
      {loadError && (
        <div className="lu-banner lu-banner--error">Falha ao carregar: {loadError}</div>
      )}

      <div className="lu-card">
        <h2 className="lu-section-title">Propaganda eleitoral</h2>
        <p className="lu-hint">
          Liga, escreve o texto, pronto. A partir daí todo clipe curto e longo sai com esse
          texto rotacionado 90 graus numa faixa na lateral, fonte 10px. New Clip e Rebrand
          aplicam sozinhos, sem perguntar de novo a cada rodada.
        </p>

        <div className="lu-field">
          <label className="lu-label">Estado</label>
          <div className="lu-choice-row">
            <label className="lu-choice-pill">
              <input
                type="radio"
                name="eleitoral-enabled"
                checked={!enabled}
                onChange={() => setEnabled(false)}
              />
              Desligada
            </label>
            <label className="lu-choice-pill">
              <input
                type="radio"
                name="eleitoral-enabled"
                checked={enabled}
                disabled={textMissing}
                onChange={() => setEnabled(true)}
              />
              Ligada
            </label>
          </div>
          {textMissing && (
            <p className="lu-hint">Escreva o texto antes de poder ligar.</p>
          )}
        </div>

        <div className="lu-field">
          <label className="lu-label">Texto da propaganda eleitoral</label>
          <textarea
            className="lu-control"
            rows={4}
            value={text}
            onChange={(event) => setText(event.target.value)}
          />
        </div>

        <div style={{ marginTop: 'var(--space-5)' }}>
          <button
            type="button"
            className="btn btn-primary"
            onClick={handleSave}
            disabled={saveState === 'saving'}
          >
            {saveState === 'saving' ? 'Salvando...' : 'Salvar'}
          </button>
          {saveState === 'saved' && <p className="lu-hint">Configuracoes salvas.</p>}
          {saveState === 'error' && <p className="lu-error">Falha ao salvar: {saveError}</p>}
        </div>
      </div>
    </div>
  )
}
