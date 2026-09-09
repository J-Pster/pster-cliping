import { useEffect, useState } from 'react'
import type {
  ClipadorCategory,
  EngineExitEvent,
  EngineLogEvent,
  EngineProgressEvent,
  RebrandJobArgs
} from '@shared/ipc-contract'
import LogConsole from '../components/LogConsole'
import ClipResultsList from '../components/ClipResultsList'
import JobProgress from '../components/JobProgress'

const CATEGORY_OPTIONS: { value: ClipadorCategory; label: string }[] = [
  { value: 'politico_pessoa', label: 'Politico / pessoa publica' },
  { value: 'jogos', label: 'Jogos' },
  { value: 'livro_audiobook', label: 'Livro / audiobook' }
]

export default function RebrandRoute(): React.JSX.Element {
  const [inputDir, setInputDir] = useState('')
  const [category, setCategory] = useState<ClipadorCategory>('politico_pessoa')

  const [advancedOpen, setAdvancedOpen] = useState(false)
  const [kb, setKb] = useState('')
  const [movement, setMovement] = useState('')
  const [output, setOutput] = useState('output')
  const [workDir, setWorkDir] = useState('')
  const [batchName, setBatchName] = useState('')
  const [outroImage, setOutroImage] = useState('')
  const [outroDuration, setOutroDuration] = useState(5)
  const [disableThumbnailComposition, setDisableThumbnailComposition] = useState(false)
  const [faceModelPath, setFaceModelPath] = useState('')
  const [limit, setLimit] = useState<number | ''>('')
  const [verbose, setVerbose] = useState(false)

  const [jobId, setJobId] = useState<string | null>(null)
  const [running, setRunning] = useState(false)
  const [logs, setLogs] = useState<EngineLogEvent[]>([])
  const [exitEvent, setExitEvent] = useState<EngineExitEvent | null>(null)
  const [progress, setProgress] = useState<EngineProgressEvent | null>(null)
  const [runError, setRunError] = useState<string | null>(null)

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

  const outroRequired = category !== 'politico_pessoa'
  const canRun = inputDir.trim().length > 0 && !running && (!outroRequired || outroImage.length > 0)

  async function handlePickInputDir(): Promise<void> {
    const picked = await window.api.dialogs.pickFolder()
    if (picked) {
      setInputDir(picked)
    }
  }

  async function handlePickOutput(): Promise<void> {
    const picked = await window.api.dialogs.pickFolder()
    if (picked) {
      setOutput(picked)
    }
  }

  async function handlePickOutroImage(): Promise<void> {
    const picked = await window.api.dialogs.pickPngFile()
    if (picked) {
      setOutroImage(picked)
    }
  }

  async function handleRun(): Promise<void> {
    setRunError(null)
    setLogs([])
    setExitEvent(null)
    setProgress(null)

    const args: RebrandJobArgs = {
      inputDir: inputDir.trim(),
      category,
      kb: kb.trim() || undefined,
      movement: movement.trim() || undefined,
      output,
      workDir: workDir.trim() || undefined,
      batchName: batchName.trim() || undefined,
      outroImage: outroImage || undefined,
      outroDuration,
      disableThumbnailComposition,
      faceModelPath: faceModelPath.trim() || undefined,
      limit: limit === '' ? undefined : limit,
      verbose
    }

    try {
      const jobHandle = await window.api.engine.runRebrand(args)
      setJobId(jobHandle.jobId)
      setRunning(true)
    } catch (error) {
      setRunError(error instanceof Error ? error.message : String(error))
    }
  }

  return (
    <div className="lu-stack">
      <div className="lu-card">
        <h2 className="lu-section-title">Pasta de entrada</h2>
        <div className="lu-field">
          <label className="lu-label">Pasta com os videos curtos a rebrandear</label>
          <div className="lu-field-with-browse">
            <input
              className="lu-control"
              type="text"
              value={inputDir}
              onChange={(event) => setInputDir(event.target.value)}
              placeholder="C:\videos\lote-para-rebrand"
            />
            <button type="button" className="btn btn-secondary" onClick={handlePickInputDir}>
              Escolher pasta
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
              <div className="lu-field-row">
                <div className="lu-field lu-field--half">
                  <label className="lu-label">Base de conhecimento (kb, opcional)</label>
                  <input
                    className="lu-control"
                    type="text"
                    value={kb}
                    onChange={(event) => setKb(event.target.value)}
                    placeholder="default: kb/<categoria>"
                  />
                </div>
                <div className="lu-field lu-field--half">
                  <label className="lu-label">Movimento (opcional)</label>
                  <input
                    className="lu-control"
                    type="text"
                    value={movement}
                    onChange={(event) => setMovement(event.target.value)}
                  />
                </div>
              </div>

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
                  <label className="lu-label">Pasta de trabalho (opcional)</label>
                  <input
                    className="lu-control"
                    type="text"
                    value={workDir}
                    onChange={(event) => setWorkDir(event.target.value)}
                    placeholder="default: .clipador"
                  />
                </div>
                <div className="lu-field lu-field--half">
                  <label className="lu-label">Nome do lote (opcional)</label>
                  <input
                    className="lu-control"
                    type="text"
                    value={batchName}
                    onChange={(event) => setBatchName(event.target.value)}
                    placeholder="default: rebrand_<pasta-de-entrada>"
                  />
                </div>
              </div>

              <div className="lu-field">
                <label className="lu-label">Imagem de outro/encerramento</label>
                <div className="lu-field-with-browse">
                  <input
                    className="lu-control"
                    type="text"
                    value={outroImage}
                    onChange={(event) => setOutroImage(event.target.value)}
                  />
                  <button type="button" className="btn btn-secondary" onClick={handlePickOutroImage}>
                    Escolher imagem
                  </button>
                </div>
                <p className="lu-hint">
                  Obrigatoria para categorias diferentes de "Politico / pessoa publica". O seletor
                  de arquivo aceita PNG; para JPG, cole o caminho diretamente no campo.
                </p>
              </div>

              <div className="lu-field-row">
                <div className="lu-field lu-field--half">
                  <label className="lu-label">Duracao do outro (segundos)</label>
                  <input
                    className="lu-control"
                    type="number"
                    min={0}
                    step={0.5}
                    value={outroDuration}
                    onChange={(event) => setOutroDuration(Number(event.target.value))}
                  />
                </div>
                <div className="lu-field lu-field--half">
                  <label className="lu-label">Limite de videos (opcional)</label>
                  <input
                    className="lu-control"
                    type="number"
                    min={0}
                    value={limit}
                    onChange={(event) =>
                      setLimit(event.target.value === '' ? '' : Number(event.target.value))
                    }
                    placeholder="processa todos"
                  />
                </div>
              </div>

              <div className="lu-field">
                <label className="lu-label">Caminho do modelo de deteccao de rosto (opcional)</label>
                <input
                  className="lu-control"
                  type="text"
                  value={faceModelPath}
                  onChange={(event) => setFaceModelPath(event.target.value)}
                  placeholder="blaze_face_short_range.tflite"
                />
              </div>

              <label className="lu-choice-pill">
                <input
                  type="checkbox"
                  checked={disableThumbnailComposition}
                  onChange={(event) => setDisableThumbnailComposition(event.target.checked)}
                />
                Desligar composicao de thumbnail
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
            {running ? 'Rebrandeando...' : 'Rebrandear'}
          </button>
          {outroRequired && !outroImage && (
            <p className="lu-hint">Escolha a imagem de outro para poder rodar nesta categoria.</p>
          )}
          {runError && <div className="lu-banner lu-banner--error">{runError}</div>}
          {running && (
            <div className="lu-banner lu-banner--info">
              <span className="lu-spinner" aria-hidden="true" />
              Processando...
            </div>
          )}
          <JobProgress event={progress} unitLabel="video" />
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
