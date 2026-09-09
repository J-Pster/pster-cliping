import { useEffect, useState } from 'react'
import type {
  ClipJobArgs,
  ClipadorCategory,
  EngineExitEvent,
  EngineLogEvent,
  EngineProgressEvent,
  FeaturesConfig,
  OnOff,
  SubtitlePreset,
  TranscriberBackend
} from '@shared/ipc-contract'
import LogConsole from '../components/LogConsole'
import ClipResultsList from '../components/ClipResultsList'
import JobProgress from '../components/JobProgress'

type ClipMode = 'both' | 'short' | 'long'

const CATEGORY_OPTIONS: { value: ClipadorCategory; label: string }[] = [
  { value: 'politico_pessoa', label: 'Politico / pessoa publica' },
  { value: 'jogos', label: 'Jogos' },
  { value: 'livro_audiobook', label: 'Livro / audiobook' }
]

const SUBTITLE_PRESET_OPTIONS: SubtitlePreset[] = ['impacto', 'anton', 'neon', 'classico']

// whisperx/faster-whisper (transcricao LOCAL) nao vem no app: o projeto so usa
// transcricao em nuvem (ver engine/CLAUDE.md), entao o runtime embutido nao carrega
// torch/whisperx pra manter o instalador pequeno (ver scripts/build-python-runtime.ps1).
const TRANSCRIBER_OPTIONS: TranscriberBackend[] = ['elevenlabs', 'assemblyai']

export default function NewClipRoute(): React.JSX.Element {
  const [input, setInput] = useState('')
  const [category, setCategory] = useState<ClipadorCategory>('politico_pessoa')
  const [featuresConfig, setFeaturesConfig] = useState<FeaturesConfig | null>(null)

  const [clipMode, setClipMode] = useState<ClipMode>('both')
  const [generateThumbnails, setGenerateThumbnails] = useState<OnOff>('on')
  const [minShortClips, setMinShortClips] = useState(5)
  const [minLongClips, setMinLongClips] = useState(5)

  const [advancedOpen, setAdvancedOpen] = useState(false)
  const [output, setOutput] = useState('output')
  const [handle, setHandle] = useState('')
  const [subtitlePreset, setSubtitlePreset] = useState<SubtitlePreset>('impacto')
  const [subtitleUppercase, setSubtitleUppercase] = useState<'' | OnOff>('')
  const [subtitleEmphasis, setSubtitleEmphasis] = useState(false)
  const [transcriber, setTranscriber] = useState<TranscriberBackend>('elevenlabs')
  const [generateMainThumbnail, setGenerateMainThumbnail] = useState(false)
  const [cookiesFromBrowser, setCookiesFromBrowser] = useState('')
  const [verbose, setVerbose] = useState(false)

  const [jobId, setJobId] = useState<string | null>(null)
  const [running, setRunning] = useState(false)
  const [logs, setLogs] = useState<EngineLogEvent[]>([])
  const [exitEvent, setExitEvent] = useState<EngineExitEvent | null>(null)
  const [progress, setProgress] = useState<EngineProgressEvent | null>(null)
  const [runError, setRunError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    window.api.features.get().then((loaded) => {
      if (!cancelled) {
        setFeaturesConfig(loaded)
      }
    })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (!jobId) {
      return
    }
    const unsubscribeLog = window.api.engine.onLog(jobId, (event) => {
      setLogs((current) => [...current, event])
    })
    const unsubscribeExit = window.api.engine.onExit(jobId, (event) => {
      setExitEvent(event)
      setRunning(false)
    })
    const unsubscribeProgress = window.api.engine.onProgress(jobId, setProgress)
    return () => {
      unsubscribeLog()
      unsubscribeExit()
      unsubscribeProgress()
    }
  }, [jobId])

  const effectiveMinShortClips = clipMode === 'long' ? 0 : minShortClips
  const effectiveMinLongClips = clipMode === 'short' ? 0 : minLongClips
  const nothingToGenerate = effectiveMinShortClips <= 0 && effectiveMinLongClips <= 0
  const canRun = input.trim().length > 0 && !nothingToGenerate && !running

  async function handlePickLocalFile(): Promise<void> {
    const picked = await window.api.dialogs.pickVideoFile()
    if (picked) {
      setInput(picked)
    }
  }

  async function handlePickOutput(): Promise<void> {
    const picked = await window.api.dialogs.pickFolder()
    if (picked) {
      setOutput(picked)
    }
  }

  async function handleRun(): Promise<void> {
    setRunError(null)
    setLogs([])
    setExitEvent(null)
    setProgress(null)

    const args: ClipJobArgs = {
      input: input.trim(),
      category,
      // O main process resolve o valor real a partir da configuracao global de Marca d'agua
      // (aba Marca d'agua / features config); o que mandamos aqui e ignorado quando a marca
      // d'agua global esta ligada.
      watermark: 'off',
      watermarkShort: undefined,
      watermarkLong: undefined,
      minShortClips: effectiveMinShortClips,
      minLongClips: effectiveMinLongClips,
      output,
      handle,
      subtitlePreset,
      subtitleUppercase: subtitleUppercase === '' ? undefined : subtitleUppercase,
      subtitleEmphasis,
      transcriber,
      generateThumbnails,
      generateMainThumbnail,
      cookiesFromBrowser: cookiesFromBrowser.trim() || undefined,
      verbose
    }

    try {
      const jobHandle = await window.api.engine.runClip(args)
      setJobId(jobHandle.jobId)
      setRunning(true)
    } catch (error) {
      setRunError(error instanceof Error ? error.message : String(error))
    }
  }

  return (
    <div className="lu-stack">
      <div className="lu-card">
        <h2 className="lu-section-title">Video de entrada</h2>
        <div className="lu-field">
          <label className="lu-label">URL do YouTube ou arquivo local</label>
          <div className="lu-field-with-browse">
            <input
              className="lu-control"
              type="text"
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder="https://youtube.com/watch?v=... ou C:\videos\entrada.mp4"
            />
            <button type="button" className="btn btn-secondary" onClick={handlePickLocalFile}>
              Escolher arquivo local
            </button>
          </div>
        </div>

        <div className="lu-field">
          <label className="lu-label">Categoria</label>
          <select
            className="lu-control"
            value={category}
            onChange={(event) => setCategory(event.target.value as ClipadorCategory)}
          >
            {CATEGORY_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>

        <div className="lu-field">
          <label className="lu-label">Clipes a gerar</label>
          <div className="lu-choice-row">
            <label className="lu-choice-pill">
              <input
                type="radio"
                name="clip-mode"
                checked={clipMode === 'both'}
                onChange={() => setClipMode('both')}
              />
              Curtos e longos
            </label>
            <label className="lu-choice-pill">
              <input
                type="radio"
                name="clip-mode"
                checked={clipMode === 'short'}
                onChange={() => setClipMode('short')}
              />
              So curtos (9:16)
            </label>
            <label className="lu-choice-pill">
              <input
                type="radio"
                name="clip-mode"
                checked={clipMode === 'long'}
                onChange={() => setClipMode('long')}
              />
              So longos (16:9)
            </label>
          </div>

          <div className="lu-field-row" style={{ marginTop: 'var(--space-3)' }}>
            {clipMode !== 'long' && (
              <div className="lu-field lu-field--half">
                <label className="lu-label">Quantos clipes curtos (9:16)</label>
                <input
                  className="lu-control"
                  type="number"
                  min={1}
                  value={minShortClips}
                  onChange={(event) => setMinShortClips(Number(event.target.value))}
                />
              </div>
            )}
            {clipMode !== 'short' && (
              <div className="lu-field lu-field--half">
                <label className="lu-label">Quantos clipes longos (16:9)</label>
                <input
                  className="lu-control"
                  type="number"
                  min={1}
                  value={minLongClips}
                  onChange={(event) => setMinLongClips(Number(event.target.value))}
                />
              </div>
            )}
          </div>
          <p className="lu-hint">
            Meta de melhor esforco: o engine tenta chegar nesse numero de clipes NOVOS, mas um
            video sem material suficiente pode gerar menos.
          </p>
        </div>

        <div className="lu-field">
          <label className="lu-label">Thumbnails</label>
          <div className="lu-choice-row">
            <label className="lu-choice-pill">
              <input
                type="radio"
                name="generate-thumbnails"
                checked={generateThumbnails === 'on'}
                onChange={() => setGenerateThumbnails('on')}
              />
              Gerar todas
            </label>
            <label className="lu-choice-pill">
              <input
                type="radio"
                name="generate-thumbnails"
                checked={generateThumbnails === 'off'}
                onChange={() => setGenerateThumbnails('off')}
              />
              Nao gerar nenhuma
            </label>
          </div>
          <p className="lu-hint">
            "Nao gerar nenhuma" tambem pula prender a capa como 1o frame do clipe curto.
          </p>
        </div>

        <p className="lu-hint">
          {featuresConfig
            ? featuresConfig.watermark.enabled
              ? "Marca d'agua: Ligada (configurada na aba Marca d'agua)"
              : "Marca d'agua: Desligada (configure na aba Marca d'agua)"
            : "Marca d'agua: carregando..."}
        </p>

        <div className={`lu-collapsible${advancedOpen ? ' lu-collapsible--open' : ''}`}>
          <button
            type="button"
            className="lu-collapsible__trigger"
            onClick={() => setAdvancedOpen((current) => !current)}
          >
            <span className="lu-collapsible__chevron" aria-hidden="true">
              ▶
            </span>
            Opcoes avancadas
          </button>

          {advancedOpen && (
            <div className="lu-collapsible__body">
              <div className="lu-field">
                <label className="lu-label">Pasta de saida</label>
                <div className="lu-field-with-browse">
                  <input
                    className="lu-control"
                    type="text"
                    value={output}
                    onChange={(event) => setOutput(event.target.value)}
                  />
                  <button type="button" className="btn btn-secondary" onClick={handlePickOutput}>
                    Escolher...
                  </button>
                </div>
              </div>

              <div className="lu-field-row">
                <div className="lu-field lu-field--half">
                  <label className="lu-label">Handle (@ do canal)</label>
                  <input
                    className="lu-control"
                    type="text"
                    value={handle}
                    onChange={(event) => setHandle(event.target.value)}
                    placeholder="@meucanal"
                  />
                </div>
                <div className="lu-field lu-field--half">
                  <label className="lu-label">Preset de legenda</label>
                  <select
                    className="lu-control"
                    value={subtitlePreset}
                    onChange={(event) => setSubtitlePreset(event.target.value as SubtitlePreset)}
                  >
                    {SUBTITLE_PRESET_OPTIONS.map((preset) => (
                      <option key={preset} value={preset}>
                        {preset}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="lu-field-row">
                <div className="lu-field lu-field--half">
                  <label className="lu-label">Caixa alta da legenda</label>
                  <select
                    className="lu-control"
                    value={subtitleUppercase}
                    onChange={(event) =>
                      setSubtitleUppercase(event.target.value as '' | OnOff)
                    }
                  >
                    <option value="">Usar padrao do preset</option>
                    <option value="on">Ligada</option>
                    <option value="off">Desligada</option>
                  </select>
                </div>
                <div className="lu-field lu-field--half">
                  <label className="lu-label">Transcricao</label>
                  <select
                    className="lu-control"
                    value={transcriber}
                    onChange={(event) => setTranscriber(event.target.value as TranscriberBackend)}
                  >
                    {TRANSCRIBER_OPTIONS.map((option) => (
                      <option key={option} value={option}>
                        {option}
                      </option>
                    ))}
                  </select>
                  <p className="lu-hint">
                    elevenlabs e o padrao do projeto e exige ELEVENLABS_API_KEY configurada em
                    Settings.
                  </p>
                </div>
              </div>

              <div className="lu-field">
                <label className="lu-label">Navegador para cookies (opcional)</label>
                <input
                  className="lu-control"
                  type="text"
                  value={cookiesFromBrowser}
                  onChange={(event) => setCookiesFromBrowser(event.target.value)}
                  placeholder="firefox, chrome, edge..."
                />
              </div>

              <label className="lu-choice-pill">
                <input
                  type="checkbox"
                  checked={subtitleEmphasis}
                  onChange={(event) => setSubtitleEmphasis(event.target.checked)}
                />
                Emphase de palavras-chave na legenda
              </label>{' '}
              <label className="lu-choice-pill">
                <input
                  type="checkbox"
                  checked={generateMainThumbnail}
                  onChange={(event) => setGenerateMainThumbnail(event.target.checked)}
                />
                Gerar thumbnail do video principal
              </label>{' '}
              <label className="lu-choice-pill">
                <input
                  type="checkbox"
                  checked={verbose}
                  onChange={(event) => setVerbose(event.target.checked)}
                />
                Verbose
              </label>
            </div>
          )}
        </div>

        <div style={{ marginTop: 'var(--space-5)' }}>
          <button type="button" className="btn btn-primary" onClick={handleRun} disabled={!canRun}>
            {running ? 'Gerando clipes...' : 'Gerar clipes'}
          </button>
          {nothingToGenerate && (
            <p className="lu-hint">Peca pelo menos 1 clipe curto ou longo.</p>
          )}
          {runError && <div className="lu-banner lu-banner--error">{runError}</div>}
          {running && (
            <div className="lu-banner lu-banner--info">
              <span className="lu-spinner" aria-hidden="true" />
              Processando...
            </div>
          )}
          <JobProgress event={progress} unitLabel="clipe" />
        </div>
      </div>

      {(jobId || logs.length > 0) && (
        <div className="lu-card">
          <h2 className="lu-section-title">Log</h2>
          <LogConsole lines={logs} exitCode={exitEvent?.code} exited={exitEvent !== null} />
        </div>
      )}

      {(jobId || logs.length > 0) && (
        <div className="lu-card">
          <h2 className="lu-section-title">Resultados</h2>
          <ClipResultsList lines={logs} />
        </div>
      )}
    </div>
  )
}
