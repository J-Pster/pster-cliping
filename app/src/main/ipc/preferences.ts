import { existsSync } from 'node:fs'
import { readFile, writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { app } from 'electron'

const PREFERENCES_FILE_NAME = 'clipador-preferences.json'

interface StoredPreferences {
  lastOutputDir?: string
}

function preferencesFilePath(): string {
  return join(app.getPath('userData'), PREFERENCES_FILE_NAME)
}

/** Compartilhada entre New Clip e Rebrand: e a mesma nocao de "onde meus clipes vao
 * parar", nao faz sentido cada tela lembrar uma pasta diferente. */
export async function getLastOutputDir(): Promise<string | null> {
  const filePath = preferencesFilePath()
  if (!existsSync(filePath)) return null

  try {
    const raw = await readFile(filePath, 'utf-8')
    const parsed = JSON.parse(raw) as StoredPreferences
    return parsed.lastOutputDir ?? null
  } catch {
    return null
  }
}

export async function saveLastOutputDir(path: string): Promise<void> {
  const stored: StoredPreferences = { lastOutputDir: path }
  await writeFile(preferencesFilePath(), JSON.stringify(stored, null, 2), 'utf-8')
}
