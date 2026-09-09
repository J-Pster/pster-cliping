import { randomUUID } from 'node:crypto'
import { existsSync } from 'node:fs'
import { delimiter } from 'node:path'
import { spawn, type ChildProcess } from 'node:child_process'
import type { BrowserWindow } from 'electron'
import { IpcChannel } from '../../shared/ipc-channels'
import type {
  ClipJobArgs,
  EngineExitEvent,
  EngineLogEvent,
  EngineProgressEvent,
  JobHandle,
  RebrandJobArgs
} from '../../shared/ipc-contract'
import { buildClipArgv, buildRebrandArgv } from './argv-builder'
import { getSettings } from './settings'
import { getFeatures } from './features'
import { bakedImagePath } from './watermark'
import { bundledFfmpegDir, defaultFontsDir, hasBundledFfmpeg } from '../runtime-paths'

/** No build empacotado o ffmpeg embutido nao esta no PATH do sistema (o app nao
 * instala nada globalmente): prefixa o PATH so deste processo filho, sem tocar no
 * PATH do usuario. Em dev, mantem o comportamento de sempre (ffmpeg do PATH real).
 * PYTHONDONTWRITEBYTECODE evita que o Python grave .pyc novos a cada execucao: alem
 * de inutil (o runtime embutido e substituido inteiro a cada update, .pyc nao
 * sobrevive), cada arquivo novo custa tempo real por causa do scan do Windows
 * Defender em cada arquivo criado. */
function childEnv(): NodeJS.ProcessEnv {
  const base: NodeJS.ProcessEnv = { ...process.env, PYTHONDONTWRITEBYTECODE: '1' }
  if (!hasBundledFfmpeg()) return base
  const pathKey = process.platform === 'win32' ? 'Path' : 'PATH'
  const currentPath = base[pathKey] ?? ''
  return { ...base, [pathKey]: `${bundledFfmpegDir()}${delimiter}${currentPath}` }
}

const runningJobs = new Map<string, ChildProcess>()

/** Marcador impresso por `clipador.progress.print_progress` (engine, stdout). Uma
 * linha "PROGRESS_MARKERjson" vira um EngineProgressEvent em vez de uma linha de log
 * humana: quem quer acompanhar clipe a clipe usa o evento estruturado, nao regex no log. */
const PROGRESS_MARKER = 'CLIPADOR_PROGRESS '

function sendLog(window: BrowserWindow, jobId: string, stream: 'stdout' | 'stderr', line: string): void {
  const event: EngineLogEvent = { jobId, stream, line, timestamp: Date.now() }
  window.webContents.send(IpcChannel.engineLogEvent, event)
}

/** O engine imprime chaves snake_case (clip_id); o resto do contrato de IPC e
 * camelCase, entao a traducao acontece aqui, na fronteira, uma vez so. */
function toProgressEvent(
  jobId: string,
  raw: Record<string, unknown>
): EngineProgressEvent {
  return {
    jobId,
    timestamp: Date.now(),
    event: raw.event as EngineProgressEvent['event'],
    phase: raw.phase as string | undefined,
    message: raw.message as string | undefined,
    index: raw.index as number | undefined,
    total: raw.total as number | undefined,
    clipId: raw.clip_id as string | undefined,
    format: raw.format as string | undefined,
    directory: raw.directory as string | undefined,
    status: raw.status as string | undefined,
    stage: raw.stage as string | undefined
  }
}

function sendProgress(window: BrowserWindow, jobId: string, payload: Record<string, unknown>): void {
  window.webContents.send(IpcChannel.engineProgressEvent, toProgressEvent(jobId, payload))
}

function sendExit(window: BrowserWindow, jobId: string, code: number | null, signal: string | null): void {
  const event: EngineExitEvent = { jobId, code, signal, timestamp: Date.now() }
  window.webContents.send(IpcChannel.engineExitEvent, event)
}

/** Acumula bytes de um stream ate ter linha(s) completa(s); um `data` do Node pode
 * cortar uma linha ao meio, e um JSON de progresso partido ao meio nao parseia. */
function createLineSplitter(onLine: (line: string) => void): {
  push(chunk: Buffer): void
  flush(): void
} {
  let buffer = ''
  return {
    push(chunk: Buffer): void {
      buffer += chunk.toString('utf-8')
      const lines = buffer.split(/\r?\n/)
      buffer = lines.pop() ?? ''
      for (const line of lines) {
        if (line.length > 0) onLine(line)
      }
    },
    flush(): void {
      if (buffer.length > 0) onLine(buffer)
      buffer = ''
    }
  }
}

function handleStdoutLine(window: BrowserWindow, jobId: string, line: string): void {
  if (line.startsWith(PROGRESS_MARKER)) {
    try {
      const payload = JSON.parse(line.slice(PROGRESS_MARKER.length)) as Record<string, unknown>
      sendProgress(window, jobId, payload)
      return
    } catch {
      // JSON malformado (nao deveria acontecer com o engine real): cai para log normal
      // em vez de descartar silenciosamente a linha.
    }
  }
  sendLog(window, jobId, 'stdout', line)
}

function runEngine(window: BrowserWindow, pythonPath: string, engineDir: string, argv: string[]): JobHandle {
  const jobId = randomUUID()

  const child = spawn(pythonPath, argv, {
    cwd: engineDir,
    env: childEnv()
  })
  runningJobs.set(jobId, child)

  const stdoutSplitter = createLineSplitter((line) => handleStdoutLine(window, jobId, line))
  const stderrSplitter = createLineSplitter((line) => sendLog(window, jobId, 'stderr', line))

  child.stdout.on('data', (chunk: Buffer) => stdoutSplitter.push(chunk))
  child.stderr.on('data', (chunk: Buffer) => stderrSplitter.push(chunk))

  child.on('exit', (code, signal) => {
    stdoutSplitter.flush()
    stderrSplitter.flush()
    runningJobs.delete(jobId)
    sendExit(window, jobId, code, signal)
  })

  return { jobId }
}

export async function runClip(window: BrowserWindow, args: ClipJobArgs): Promise<JobHandle> {
  const settings = await getSettings()
  const features = await getFeatures()

  const withWatermark: ClipJobArgs =
    features.watermark.enabled && existsSync(bakedImagePath('short')) && existsSync(bakedImagePath('long'))
      ? {
          ...args,
          watermark: 'on',
          watermarkShort: bakedImagePath('short'),
          watermarkLong: bakedImagePath('long')
        }
      : { ...args, watermark: 'off', watermarkShort: undefined, watermarkLong: undefined }

  const effectiveArgs: ClipJobArgs = { ...withWatermark, fontsDir: args.fontsDir ?? defaultFontsDir() }

  return runEngine(window, settings.pythonPath, settings.engineDir, buildClipArgv(effectiveArgs, features))
}

export async function runRebrand(window: BrowserWindow, args: RebrandJobArgs): Promise<JobHandle> {
  const settings = await getSettings()
  const features = await getFeatures()
  return runEngine(window, settings.pythonPath, settings.engineDir, buildRebrandArgv(args, features))
}

export function cancelJob(jobId: string): void {
  runningJobs.get(jobId)?.kill()
}
