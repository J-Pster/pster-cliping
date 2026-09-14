import { useEffect, useState } from 'react'
import { Brain, Cpu, Eye, EyeOff, Info, Mic, Wrench, type LucideIcon } from 'lucide-react'
import type { AppInfo, EngineSettings, UpdateStatus } from '@shared/ipc-contract'
import Disclosure from '../components/Disclosure'

type SaveState = 'idle' | 'saving' | 'saved' | 'error'

const EMPTY_SETTINGS: EngineSettings = {
  engineDir: '',
  pythonPath: '',
  CLIPADOR_TEXT_LLM_PROVIDER: 'claude',
  // So API key: sem OAuth (nao tem como usar a assinatura Claude Pro/Max por aqui).
  // Campo continua existindo no contrato/engine, so nao aparece mais editavel na UI.
  CLIPADOR_LLM_AUTH_MODE: 'api_key',
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

function Card({
  icon: Icon,
  title,
  desc,
  children
}: {
  icon: LucideIcon
  title: string
  desc?: string
  children: React.ReactNode
}): React.JSX.Element {
  return (
    <div className="lu-card">
      <div className="lu-card__header">
        <span className="lu-card__icon" aria-hidden="true">
          <Icon size={18} strokeWidth={2} />
        </span>
        <div className="lu-card__heading">
          <h2 className="lu-card__title">{title}</h2>
          {desc && <p className="lu-card__desc">{desc}</p>}
        </div>
      </div>
      {children}
    </div>
  )
}

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
          {visible ? <EyeOff size={16} strokeWidth={2} /> : <Eye size={16} strokeWidth={2} />}
        </button>
      </div>
      {hint && <p className="lu-hint">{hint}</p>}
    </div>
  )
}

function updateStatusLabel(status: UpdateStatus): string {
  switch (status.state) {
    case 'checking':
      return 'Verificando...'
    case 'not-available':
      return 'Voce ja esta na versao mais recente.'
    case 'available':
      return `Atualizacao ${status.version} disponivel, baixando...`
    case 'downloading':
      return `Baixando atualizacao... ${status.percent}%`
    case 'downloaded':
      return `Atualizacao ${status.version} pronta. Reinicie pelo aviso no rodape.`
    case 'error':
      return `Falha ao verificar: ${status.message}`
    default:
      return ''
  }
}

export default function SettingsRoute(): React.JSX.Element {
  const [settings, setSettings] = useState<EngineSettings>(EMPTY_SETTINGS)
  const [appInfo, setAppInfo] = useState<AppInfo | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [saveState, setSaveState] = useState<SaveState>('idle')
  const [saveError, setSaveError] = useState<string | null>(null)
  const [updateStatus, setUpdateStatus] = useState<UpdateStatus | null>(null)
  const [checkingUpdate, setCheckingUpdate] = useState(false)

  useEffect(() => {
    let cancelled = false
    Promise.all([window.api.settings.get(), window.api.app.getInfo()])
      .then(([loaded, info]) => {
        if (!cancelled) {
          // Forca api_key mesmo se um .env antigo ainda tiver oauth salvo: a UI nao
          // oferece mais essa escolha (ver comentario em EMPTY_SETTINGS).
          setSettings({ ...loaded, CLIPADOR_LLM_AUTH_MODE: 'api_key' })
          setAppInfo(info)
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

  useEffect(() => {
    return window.api.app.onUpdateStatus(setUpdateStatus)
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

  async function handleCheckUpdate(): Promise<void> {
    setCheckingUpdate(true)
    try {
      await window.api.app.checkForUpdates()
    } catch {
      // o evento 'error' do autoUpdater ja chega via onUpdateStatus
    } finally {
      setCheckingUpdate(false)
    }
  }

  if (loading) {
    return <p className="lu-hint">Carregando configuracoes...</p>
  }

  return (
    <div className="lu-stack">
      {loadError && <div className="lu-banner lu-banner--error">Falha ao carregar: {loadError}</div>}

      <Card icon={Brain} title="LLM de texto" desc="Provedor usado na selecao, rerank, titulo/descricao/hashtags.">
        <div className="lu-field">
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
        <PasswordField
          label="ANTHROPIC_API_KEY"
          value={settings.ANTHROPIC_API_KEY}
          onChange={(value) => updateEnv('ANTHROPIC_API_KEY', value)}
          hint="console.anthropic.com. Usada quando o provedor de texto e Claude."
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
      </Card>

      <Card icon={Mic} title="Transcricao" desc="ElevenLabs Scribe v2 e o backend padrao do projeto.">
        <PasswordField
          label="ELEVENLABS_API_KEY"
          value={settings.ELEVENLABS_API_KEY}
          onChange={(value) => updateEnv('ELEVENLABS_API_KEY', value)}
          hint="Obrigatoria: e o unico backend de transcricao usado. elevenlabs.io > perfil > API Keys."
        />
      </Card>

      {appInfo && !appInfo.isPackaged && (
        <Card icon={Cpu} title="Engine" desc="So em desenvolvimento: em producao ja vem embutido.">
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
        </Card>
      )}

      {appInfo?.isPackaged && (
        <Disclosure title="Avancado" subtitle="Engine/Python usados, so para depuracao" icon={Wrench}>
          <p className="lu-hint">
            O Clipador ja vem com o engine e o Python embutidos, nao precisa configurar nada aqui.
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
        </Disclosure>
      )}

      <Card icon={Info} title="Sobre" desc="Pster Clipping">
        <div className="lu-about-row">
          <div>
            <p className="lu-about-row__label">Versao instalada</p>
            <p className="lu-about-row__value">{appInfo?.version ?? '...'}</p>
          </div>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={handleCheckUpdate}
            disabled={checkingUpdate || !appInfo?.isPackaged}
          >
            {checkingUpdate ? 'Verificando...' : 'Verificar atualizacoes'}
          </button>
        </div>
        {!appInfo?.isPackaged && (
          <p className="lu-hint">Auto-update so funciona no app instalado, nao em desenvolvimento.</p>
        )}
        {appInfo?.isPackaged && updateStatus && (
          <p className="lu-hint">{updateStatusLabel(updateStatus)}</p>
        )}
      </Card>

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
