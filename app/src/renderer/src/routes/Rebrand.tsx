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
import Stepper, { type StepDef } from '../components/Stepper'
import TokenUsagePanel from '../components/TokenUsagePanel'
import { useTokenUsage } from '../hooks/useTokenUsage'

const CATEGORY_OPTIONS: { value: ClipadorCategory; label: string }[] = [
  { value: 'politico_pessoa', label: 'Politico / pessoa publica' },
  { value: 'jogos', label: 'Jogos' },
  { value: 'livro_audiobook', label: 'Livro / audiobook' }
]

// 3 passos: nem tudo largado de uma vez, nem passo demais pra chegar no botao final.
const STEPS: StepDef[] = [
  { id: 'entrada', label: 'Entrada' },
  { id: 'lote', label: 'Lote e encerramento' },
  { id: 'avancado', label: 'Avancado' }
]

export default function RebrandRoute(): React.JSX.Element {
  const [step, setStep] = useState(0)
  const [furthestStep, setFurthestStep] = useState(0)

  const [inputDir, setInputDir] = useState('')
  const [category, setCategory] = useState<ClipadorCategory>('politico_pessoa')

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
  const tokenUsage = useTokenUsage()

  // Lembra a ultima pasta de saida informada (New Clip e Rebrand compartilham a mesma
  // memoria: e a mesma nocao de "onde meus clipes vao parar").
  useEffect(() => {
    let cancelled = false
    window.api.preferences.getLastOutputDir().then((lastOutputDir) => {
      if (!cancelled && lastOutputDir) {
        setOutput(lastOutputDir)
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
    const unsubscribeProgress = window.api.engine.onProgress(jobId, (event) => {
      setProgress(event)
      tokenUsage.onProgressEvent(event)
    })
    return () => {
      unsubscribeLog()
      unsubscribeExit()
      unsubscribeProgress()
    }
  }, [jobId])

  const outroRequired = category !== 'politico_pessoa'
  const isLastStep = step === STEPS.length - 1
  const canRun = inputDir.trim().length > 0 && !running && (!outroRequired || outroImage.length > 0)

  const stepErrors: Record<number, string | null> = {
    0: inputDir.trim().length === 0 ? 'Escolha a pasta com os videos curtos a rebrandear.' : null,
    1: outroRequired && !outroImage ? 'Escolha a imagem de outro para poder rodar nesta categoria.' : null,
    2: null
  }

  function handleNext(): void {
    if (stepErrors[step]) return
    const next = Math.min(step + 1, STEPS.length - 1)
    setStep(next)
    setFurthestStep((current) => Math.max(current, next))
  }

  function handleBack(): void {
    setStep((current) => Math.max(current - 1, 0))
  }

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
    tokenUsage.reset()
    void window.api.preferences.saveLastOutputDir(output)

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
        <Stepper
          steps={STEPS}
          current={STEPS[step].id}
          furthestIndex={furthestStep}
          onSelect={(id) => setStep(STEPS.findIndex((candidate) => candidate.id === id))}
        />

        {step === 0 && (
          <div className="lu-stack">
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
          </div>
        )}

        {step === 1 && (
          <div className="lu-stack">
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

            <div className="lu-field-row">
              <div className="lu-field lu-field--half">
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
              <label className="lu-label">Pasta de trabalho (opcional)</label>
              <input
                className="lu-control"
                type="text"
                value={workDir}
                onChange={(event) => setWorkDir(event.target.value)}
                placeholder="default: .clipador"
              />
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
                Obrigatoria para categorias diferentes de "Politico / pessoa publica". O seletor de
                arquivo aceita PNG; para JPG, cole o caminho diretamente no campo.
              </p>
            </div>

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
          </div>
        )}

        {step === 2 && (
          <div className="lu-stack">
            <div className="lu-field-row">
              <div className="lu-field lu-field--half">
                <label className="lu-label">Caminho do modelo de deteccao de rosto (opcional)</label>
                <input
                  className="lu-control"
                  type="text"
                  value={faceModelPath}
                  onChange={(event) => setFaceModelPath(event.target.value)}
                  placeholder="blaze_face_short_range.tflite"
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

            <label className="lu-choice-pill">
              <input
                type="checkbox"
                checked={disableThumbnailComposition}
                onChange={(event) => setDisableThumbnailComposition(event.target.checked)}
              />
              Desligar composicao de thumbnail (usar frame cru)
            </label>{' '}
            <label className="lu-choice-pill">
              <input
                type="checkbox"
                checked={verbose}
                onChange={(event) => setVerbose(event.target.checked)}
              />
              Modo detalhado (log completo)
            </label>
          </div>
        )}

        <div className="lu-wizard-nav">
          {step > 0 ? (
            <button type="button" className="btn btn-secondary" onClick={handleBack}>
              Voltar
            </button>
          ) : (
            <span className="lu-wizard-nav__spacer" />
          )}

          {!isLastStep && (
            <button
              type="button"
              className="btn btn-primary"
              onClick={handleNext}
              disabled={!!stepErrors[step]}
            >
              Proximo
            </button>
          )}

          {isLastStep && (
            <button type="button" className="btn btn-primary" onClick={handleRun} disabled={!canRun}>
              {running ? 'Rebrandeando...' : 'Rebrandear'}
            </button>
          )}
        </div>

        {stepErrors[step] && <p className="lu-hint">{stepErrors[step]}</p>}
        {isLastStep && runError && <div className="lu-banner lu-banner--error">{runError}</div>}
        {isLastStep && running && (
          <div className="lu-banner lu-banner--info">
            <span className="lu-spinner" aria-hidden="true" />
            Processando...
          </div>
        )}
        {isLastStep && <JobProgress event={progress} unitLabel="video" />}
      </div>

      {(jobId || logs.length > 0) && (
        <div className="lu-card">
          <h2 className="lu-section-title">Registro de execucao</h2>
          <div className="lu-log-row">
            <LogConsole lines={logs} exitCode={exitEvent?.code} exited={exitEvent !== null} />
            <TokenUsagePanel totals={tokenUsage.totals} />
          </div>
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
