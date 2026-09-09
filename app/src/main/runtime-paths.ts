import { existsSync } from 'node:fs'
import { cp, mkdir } from 'node:fs/promises'
import { join } from 'node:path'
import { app } from 'electron'

/**
 * Em producao (o .exe instalado), Python + engine + ffmpeg vem embutido nos
 * resources do app (extraResources no electron-builder.yml), gerado pelos scripts
 * `npm run runtime:python` / `npm run runtime:ffmpeg` antes do build (ver
 * scripts/build-python-runtime.ps1 e scripts/fetch-ffmpeg.ps1). Em dev (`npm run
 * dev`), usa o checkout do monorepo (../engine, com seu proprio .venv) como sempre
 * funcionou.
 *
 * A pasta de instalacao (resources/) e SUBSTITUIDA inteira a cada auto-update: nada
 * gravado la sobrevive a uma atualizacao. Por isso kb/ editavel, .env e output/
 * vivem em workDir(), dentro de userData, que o electron-updater nunca toca.
 */

export function isPackaged(): boolean {
  return app.isPackaged
}

function bundledResourcesDir(): string {
  return process.resourcesPath
}

/** Somente leitura: kb/ default e assets/fonts/, gerados no build. kb.ts nunca
 * escreve aqui, so le como origem do seed inicial de workDir()/kb. */
export function bundledEngineDir(): string {
  return join(bundledResourcesDir(), 'engine')
}

function bundledPythonExecutable(): string {
  return join(bundledResourcesDir(), 'python', 'python.exe')
}

export function bundledFfmpegDir(): string {
  return join(bundledResourcesDir(), 'ffmpeg')
}

function devEngineDir(): string {
  return join(app.getAppPath(), '..', 'engine')
}

function devPythonPath(engineDir: string): string {
  const relative = process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python'
  return join(engineDir, '.venv', relative)
}

/** Pasta de trabalho gravavel: kb/ (copia editavel), .env, output/. Em dev e o
 * proprio checkout do engine (ja gravavel, ja tem tudo). Em producao fica em
 * userData/engine-workspace, que sobrevive a updates. */
export function workDir(): string {
  if (!isPackaged()) return devEngineDir()
  return join(app.getPath('userData'), 'engine-workspace')
}

export function defaultPythonPath(): string {
  if (isPackaged()) return bundledPythonExecutable()
  return devPythonPath(devEngineDir())
}

/** assets/fonts nunca e editado pelo usuario: em producao aponta direto pra copia
 * somente-leitura dos resources, sem duplicar em userData. Undefined em dev deixa
 * o default do proprio CLI (assets/fonts relativo ao cwd) valer, como sempre foi. */
export function defaultFontsDir(): string | undefined {
  if (!isPackaged()) return undefined
  return join(bundledEngineDir(), 'assets', 'fonts')
}

export function hasBundledFfmpeg(): boolean {
  return isPackaged() && existsSync(bundledFfmpegDir())
}

/** Roda uma vez no boot do app empacotado: garante workDir() e semeia kb/ a partir
 * da copia bundled SE ainda nao existir (nunca sobrescreve edicoes do usuario). */
export async function ensureWorkDirSeeded(): Promise<void> {
  if (!isPackaged()) return

  const dir = workDir()
  await mkdir(dir, { recursive: true })

  const kbTarget = join(dir, 'kb')
  const kbSource = join(bundledEngineDir(), 'kb')
  if (!existsSync(kbTarget) && existsSync(kbSource)) {
    await cp(kbSource, kbTarget, { recursive: true })
  }
}
