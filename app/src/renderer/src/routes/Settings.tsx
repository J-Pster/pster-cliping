import { useEffect, useState } from 'react'
import type { EngineSettings } from '@shared/ipc-contract'

type SaveState = 'idle' | 'saving' | 'saved' | 'error'

const EMPTY_SETTINGS: EngineSettings = {
  engineDir: '',
  pythonPath: '',
  CLIPADOR_TEXT_LLM_PROVIDER: 'claude',
  CLIPADOR_LLM_AUTH_MODE: 'oauth',
  CLAUDE_CODE_OAUTH_TOKEN: '',
  ANTHROPIC_API_KEY: '',
  HUGGINGFACE_TOKEN: '',
  ELEVENLABS_API_KEY: '',
  ASSEMBLYAI_API_KEY: '',
  GEMINI_API_KEY: '',
  CLIPADOR_GEMINI_TEXT_MODEL: '',
  BUFFER_API_KEY: '',
  BUFFER_CHANNEL_COMMIT_CIVICO_YOUTUBE: '',
  BUFFER_CHANNEL_COMMIT_CIVICO_INSTAGRAM: '',
  BUFFER_CHANNEL_COMMIT_CIVICO_TIKTOK: '',
  BUFFER_CHANNEL_PESSOAL_YOUTUBE: '',
  BUFFER_CHANNEL_PESSOAL_INSTAGRAM: '',
  BUFFER_CHANNEL_PESSOAL_TIKTOK: ''
}

type EnvField = keyof Omit<EngineSettings, 'engineDir' | 'pythonPath'>

function TextField({
  label,
  value,
  onChange,
  hint,
  placeholder
}: {
  label: string
  value: string
  onChange: (value: string) => void
  hint?: string
  placeholder?: string
}): React.JSX.Element {
  return (
    <div className="lu-field">
      <label className="lu-label">{label}</label>
      <input
        className="lu-control"
        type="text"
        value={value}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
      />
      {hint && <p className="lu-hint">{hint}</p>}
    </div>
  )
}

function PasswordField({
  label,
  value,
  onChange,
  hint
}: {
  label: string
  value: string
  onChange: (value: string) => void
  hint?: string
}): React.JSX.Element {
  const [visible, setVisible] = useState(false)

  return (
    <div className="lu-field">
      <label className="lu-label">{label}</label>
      <div className="lu-input-with-action">
        <input
          className="lu-control"
          type={visible ? 'text' : 'password'}
          value={value}
          autoComplete="off"
          onChange={(event) => onChange(event.target.value)}
        />
        <button
          type="button"
          className="lu-input-with-action__toggle"
          onClick={() => setVisible((current) => !current)}
          aria-label={visible ? 'Esconder valor' : 'Mostrar valor'}
          title={visible ? 'Esconder valor' : 'Mostrar valor'}
        >
          {visible ? '🙈' : '👁'}
        </button>
      </div>
      {hint && <p className="lu-hint">{hint}</p>}
    </div>
  )
}

export default function SettingsRoute(): React.JSX.Element {
  const [settings, setSettings] = useState<EngineSettings>(EMPTY_SETTINGS)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [saveState, setSaveState] = useState<SaveState>('idle')
  const [saveError, setSaveError] = useState<string | null>(null)
  const [transcriptionExtraOpen, setTranscriptionExtraOpen] = useState(false)
  const [bufferOpen, setBufferOpen] = useState(false)
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const [isPackaged, setIsPackaged] = useState(false)

  useEffect(() => {
    let cancelled = false
    Promise.all([window.api.settings.get(), window.api.app.getInfo()])
      .then(([loaded, info]) => {
        if (!cancelled) {
          setSettings(loaded)
          setIsPackaged(info.isPackaged)
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

  function update<K extends keyof EngineSettings>(key: K, value: EngineSettings[K]): void {
    setSettings((current) => ({ ...current, [key]: value }))
  }

  function updateEnv(key: EnvField, value: string): void {
    update(key, value)
  }

  async function handleSave(): Promise<void> {
    setSaveState('saving')
    setSaveError(null)
    try {
      await window.api.settings.save(settings)
      setSaveState('saved')
    } catch (error) {
      setSaveState('error')
      setSaveError(error instanceof Error ? error.message : String(error))
    }
  }

  async function browseEngineDir(): Promise<void> {
    const picked = await window.api.dialogs.pickFolder()
    if (picked) {
      update('engineDir', picked)
    }
  }

  if (loading) {
    return <p className="lu-hint">Carregando configuracoes...</p>
  }

  return (
    <div className="lu-stack">
      {loadError && <div className="lu-banner lu-banner--error">Falha ao carregar: {loadError}</div>}

      {!isPackaged && (
        <div className="lu-card">
          <h2 className="lu-section-title">Engine</h2>
          <div className="lu-field">
            <label className="lu-label">Pasta do engine</label>
            <div className="lu-field-with-browse">
              <input
                className="lu-control"
                type="text"
                value={settings.engineDir}
                onChange={(event) => update('engineDir', event.target.value)}
                placeholder="C:\caminho\para\engine"
              />
              <button type="button" className="btn btn-secondary" onClick={browseEngineDir}>
                Escolher...
              </button>
            </div>
          </div>
          <TextField
            label="Python (venv)"
            value={settings.pythonPath}
            onChange={(value) => update('pythonPath', value)}
            placeholder="C:\caminho\para\engine\.venv\Scripts\python.exe"
            hint="Executavel Python dentro do venv onde o pacote clipador foi instalado."
          />
        </div>
      )}

      {isPackaged && (
        <div className="lu-card">
          <div className={`lu-collapsible${advancedOpen ? ' lu-collapsible--open' : ''}`}>
            <button
              type="button"
              className="lu-collapsible__trigger"
              onClick={() => setAdvancedOpen((current) => !current)}
            >
              <span className="lu-collapsible__chevron" aria-hidden="true">
                ▶
              </span>
              Avancado: engine/Python usados
            </button>

            {advancedOpen && (
              <div className="lu-collapsible__body">
                <p className="lu-hint">
                  O Clipador ja vem com o engine e o Python embutidos, nao precisa configurar nada
                  aqui. Estes campos so existem para depuracao.
                </p>
                <div className="lu-field">
                  <label className="lu-label">Pasta de trabalho (kb, .env, output)</label>
                  <div className="lu-field-with-browse">
                    <input
                      className="lu-control"
                      type="text"
                      value={settings.engineDir}
                      onChange={(event) => update('engineDir', event.target.value)}
                    />
                    <button type="button" className="btn btn-secondary" onClick={browseEngineDir}>
                      Escolher...
                    </button>
                  </div>
                </div>
                <TextField
                  label="Python embutido"
                  value={settings.pythonPath}
                  onChange={(value) => update('pythonPath', value)}
                />
              </div>
            )}
          </div>
        </div>
      )}

      <div className="lu-card">
        <h2 className="lu-section-title">LLM de texto</h2>
        <div className="lu-field-row">
          <div className="lu-field lu-field--half">
            <label className="lu-label">Provedor</label>
            <select
              className="lu-control"
              value={settings.CLIPADOR_TEXT_LLM_PROVIDER}
              onChange={(event) => updateEnv('CLIPADOR_TEXT_LLM_PROVIDER', event.target.value)}
            >
              <option value="claude">Claude</option>
              <option value="gemini">Gemini</option>
            </select>
          </div>
          <div className="lu-field lu-field--half">
            <label className="lu-label">Modo de autenticacao</label>
            <select
              className="lu-control"
              value={settings.CLIPADOR_LLM_AUTH_MODE}
              onChange={(event) => updateEnv('CLIPADOR_LLM_AUTH_MODE', event.target.value)}
            >
              <option value="oauth">OAuth (assinatura Claude Pro/Max)</option>
              <option value="api_key">API key (pay per use)</option>
            </select>
          </div>
        </div>
        <PasswordField
          label="CLAUDE_CODE_OAUTH_TOKEN"
          value={settings.CLAUDE_CODE_OAUTH_TOKEN}
          onChange={(value) => updateEnv('CLAUDE_CODE_OAUTH_TOKEN', value)}
          hint="Gere com 'claude setup-token'. Usado quando o modo de autenticacao e OAuth."
        />
        <PasswordField
          label="ANTHROPIC_API_KEY"
          value={settings.ANTHROPIC_API_KEY}
          onChange={(value) => updateEnv('ANTHROPIC_API_KEY', value)}
          hint="console.anthropic.com. Usado quando o modo de autenticacao e API key."
        />
        <TextField
          label="Modelo Gemini de texto (opcional)"
          value={settings.CLIPADOR_GEMINI_TEXT_MODEL}
          onChange={(value) => updateEnv('CLIPADOR_GEMINI_TEXT_MODEL', value)}
          placeholder="gemini-3.1-pro-preview"
          hint="So usado quando o provedor de texto e Gemini. Vazio usa o default do codigo."
        />
        <PasswordField
          label="GEMINI_API_KEY"
          value={settings.GEMINI_API_KEY}
          onChange={(value) => updateEnv('GEMINI_API_KEY', value)}
          hint="aistudio.google.com/apikey. Tambem usada sempre para gerar a thumbnail (Nano Banana)."
        />
      </div>

      <div className="lu-card">
        <h2 className="lu-section-title">Transcricao</h2>
        <PasswordField
          label="ELEVENLABS_API_KEY"
          value={settings.ELEVENLABS_API_KEY}
          onChange={(value) => updateEnv('ELEVENLABS_API_KEY', value)}
          hint="Obrigatoria para o backend padrao (elevenlabs). elevenlabs.io > perfil > API Keys."
        />

        <div className={`lu-collapsible${transcriptionExtraOpen ? ' lu-collapsible--open' : ''}`}>
          <button
            type="button"
            className="lu-collapsible__trigger"
            onClick={() => setTranscriptionExtraOpen((current) => !current)}
          >
            <span className="lu-collapsible__chevron" aria-hidden="true">
              ▶
            </span>
            Chaves extras (nao usadas agora)
          </button>

          {transcriptionExtraOpen && (
            <div className="lu-collapsible__body">
              <PasswordField
                label="ASSEMBLYAI_API_KEY"
                value={settings.ASSEMBLYAI_API_KEY}
                onChange={(value) => updateEnv('ASSEMBLYAI_API_KEY', value)}
                hint="Usada apenas pelo backend de transcricao assemblyai (nao e o padrao)."
              />
              <PasswordField
                label="HUGGINGFACE_TOKEN"
                value={settings.HUGGINGFACE_TOKEN}
                onChange={(value) => updateEnv('HUGGINGFACE_TOKEN', value)}
                hint="So necessario para diarizacao real via WhisperX (nao e o backend padrao)."
              />
            </div>
          )}
        </div>
      </div>

      <div className="lu-card">
        <div className={`lu-collapsible${bufferOpen ? ' lu-collapsible--open' : ''}`}>
          <button
            type="button"
            className="lu-collapsible__trigger"
            onClick={() => setBufferOpen((current) => !current)}
          >
            <span className="lu-collapsible__chevron" aria-hidden="true">
              ▶
            </span>
            Postagem automatica (Buffer) - nao usada agora
          </button>

          {bufferOpen && (
            <div className="lu-collapsible__body">
              <PasswordField
                label="BUFFER_API_KEY"
                value={settings.BUFFER_API_KEY}
                onChange={(value) => updateEnv('BUFFER_API_KEY', value)}
                hint="buffer.com > Settings > API."
              />
              <div className="lu-field-row">
                <div className="lu-field lu-field--half">
                  <TextField
                    label="Commit Civico - YouTube"
                    value={settings.BUFFER_CHANNEL_COMMIT_CIVICO_YOUTUBE}
                    onChange={(value) => updateEnv('BUFFER_CHANNEL_COMMIT_CIVICO_YOUTUBE', value)}
                  />
                </div>
                <div className="lu-field lu-field--half">
                  <TextField
                    label="Commit Civico - Instagram"
                    value={settings.BUFFER_CHANNEL_COMMIT_CIVICO_INSTAGRAM}
                    onChange={(value) => updateEnv('BUFFER_CHANNEL_COMMIT_CIVICO_INSTAGRAM', value)}
                  />
                </div>
              </div>
              <div className="lu-field-row">
                <div className="lu-field lu-field--half">
                  <TextField
                    label="Commit Civico - TikTok"
                    value={settings.BUFFER_CHANNEL_COMMIT_CIVICO_TIKTOK}
                    onChange={(value) => updateEnv('BUFFER_CHANNEL_COMMIT_CIVICO_TIKTOK', value)}
                  />
                </div>
                <div className="lu-field lu-field--half">
                  <TextField
                    label="Pessoal - YouTube"
                    value={settings.BUFFER_CHANNEL_PESSOAL_YOUTUBE}
                    onChange={(value) => updateEnv('BUFFER_CHANNEL_PESSOAL_YOUTUBE', value)}
                  />
                </div>
              </div>
              <div className="lu-field-row">
                <div className="lu-field lu-field--half">
                  <TextField
                    label="Pessoal - Instagram"
                    value={settings.BUFFER_CHANNEL_PESSOAL_INSTAGRAM}
                    onChange={(value) => updateEnv('BUFFER_CHANNEL_PESSOAL_INSTAGRAM', value)}
                  />
                </div>
                <div className="lu-field lu-field--half">
                  <TextField
                    label="Pessoal - TikTok"
                    value={settings.BUFFER_CHANNEL_PESSOAL_TIKTOK}
                    onChange={(value) => updateEnv('BUFFER_CHANNEL_PESSOAL_TIKTOK', value)}
                  />
                </div>
              </div>
              <p className="lu-hint">
                Os IDs de canal saem de `clipador-publish buffer-channels` depois de configurar a
                BUFFER_API_KEY.
              </p>
            </div>
          )}
        </div>
      </div>

      <div>
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
  )
}
