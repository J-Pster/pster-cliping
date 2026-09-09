import { existsSync } from 'node:fs'
import { readFile, writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { app } from 'electron'
import type { EngineEnvVars, EngineSettings } from '../../shared/ipc-contract'
import { defaultPythonPath, workDir } from '../runtime-paths'

const CONFIG_FILE_NAME = 'clipador-config.json'

const ENV_KEYS = [
  'CLIPADOR_TEXT_LLM_PROVIDER',
  'CLIPADOR_LLM_AUTH_MODE',
  'CLAUDE_CODE_OAUTH_TOKEN',
  'ANTHROPIC_API_KEY',
  'HUGGINGFACE_TOKEN',
  'ELEVENLABS_API_KEY',
  'ASSEMBLYAI_API_KEY',
  'GEMINI_API_KEY',
  'CLIPADOR_GEMINI_TEXT_MODEL',
  'BUFFER_API_KEY',
  'BUFFER_CHANNEL_COMMIT_CIVICO_YOUTUBE',
  'BUFFER_CHANNEL_COMMIT_CIVICO_INSTAGRAM',
  'BUFFER_CHANNEL_COMMIT_CIVICO_TIKTOK',
  'BUFFER_CHANNEL_PESSOAL_YOUTUBE',
  'BUFFER_CHANNEL_PESSOAL_INSTAGRAM',
  'BUFFER_CHANNEL_PESSOAL_TIKTOK'
] as const satisfies readonly (keyof EngineEnvVars)[]

interface AppConfig {
  engineDir: string
  pythonPath: string
}

function configFilePath(): string {
  return join(app.getPath('userData'), CONFIG_FILE_NAME)
}

async function readAppConfig(): Promise<AppConfig> {
  const defaults: AppConfig = {
    engineDir: workDir(),
    pythonPath: defaultPythonPath()
  }

  const filePath = configFilePath()
  if (!existsSync(filePath)) return defaults

  try {
    const raw = await readFile(filePath, 'utf-8')
    const parsed = JSON.parse(raw) as Partial<AppConfig>
    return {
      engineDir: parsed.engineDir ?? defaults.engineDir,
      pythonPath: parsed.pythonPath ?? defaults.pythonPath
    }
  } catch {
    return defaults
  }
}

async function writeAppConfig(config: AppConfig): Promise<void> {
  await writeFile(configFilePath(), JSON.stringify(config, null, 2), 'utf-8')
}

function parseDotenv(content: string): Map<string, string> {
  const entries = new Map<string, string>()
  for (const rawLine of content.split(/\r?\n/)) {
    const line = rawLine.trim()
    if (!line || line.startsWith('#')) continue
    const separatorIndex = line.indexOf('=')
    if (separatorIndex === -1) continue
    const key = line.slice(0, separatorIndex).trim()
    const value = line.slice(separatorIndex + 1).trim()
    entries.set(key, value)
  }
  return entries
}

function serializeDotenv(entries: Map<string, string>): string {
  return Array.from(entries.entries())
    .map(([key, value]) => `${key}=${value}`)
    .join('\n')
}

function envFilePath(engineDir: string): string {
  return join(engineDir, '.env')
}

async function readEngineEnv(engineDir: string): Promise<EngineEnvVars> {
  const filePath = envFilePath(engineDir)
  const entries = existsSync(filePath) ? parseDotenv(await readFile(filePath, 'utf-8')) : new Map()

  const result: Record<string, string> = {}
  for (const key of ENV_KEYS) {
    result[key] = entries.get(key) ?? ''
  }
  return result as unknown as EngineEnvVars
}

async function writeEngineEnv(engineDir: string, values: EngineEnvVars): Promise<void> {
  const filePath = envFilePath(engineDir)
  const entries = existsSync(filePath) ? parseDotenv(await readFile(filePath, 'utf-8')) : new Map()

  for (const key of ENV_KEYS) {
    entries.set(key, values[key] ?? '')
  }

  await writeFile(filePath, serializeDotenv(entries), 'utf-8')
}

export async function getEngineDir(): Promise<string> {
  return (await readAppConfig()).engineDir
}

export async function getSettings(): Promise<EngineSettings> {
  const appConfig = await readAppConfig()
  const envVars = await readEngineEnv(appConfig.engineDir)
  return { ...appConfig, ...envVars }
}

export async function saveSettings(settings: EngineSettings): Promise<void> {
  const { engineDir, pythonPath, ...envVars } = settings
  await writeAppConfig({ engineDir, pythonPath })
  await writeEngineEnv(engineDir, envVars)
}
