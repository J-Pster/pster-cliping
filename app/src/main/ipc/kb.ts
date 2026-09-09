import { existsSync } from 'node:fs'
import { copyFile, mkdir, readdir, readFile, rm, stat, writeFile } from 'node:fs/promises'
import { basename, join } from 'node:path'
import { dialog, type BrowserWindow } from 'electron'
import type { ClipadorCategory, KbDoc, KbSection, KbSnapshot, KbSourceFile } from '../../shared/ipc-contract'
import { getEngineDir } from './settings'

const CORE_DIRNAME = 'core'
const TOPICS_DIRNAME = 'topics'
const SOURCES_DIRNAME = 'sources'

/** Mesma regra de nome de arquivo aceita pelo engine (ver kb/knowledge.py): sem
 * caminho, so o nome. Aqui restringimos ainda mais, a slug seguro pra evitar
 * qualquer travessia de diretorio a partir de input da UI. */
function sanitizeFilename(filename: string): string {
  const base = basename(filename).replace(/\.md$/i, '')
  const cleaned = base
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9-_]+/g, '-')
    .replace(/^-+|-+$/g, '')
  if (!cleaned) {
    throw new Error('Nome de arquivo invalido')
  }
  return cleaned
}

function titleOf(content: string, fallback: string): string {
  for (const line of content.split(/\r?\n/)) {
    const trimmed = line.trim()
    if (trimmed.startsWith('# ')) {
      return trimmed.slice(2).trim()
    }
  }
  return fallback
}

async function readDocsFrom(dir: string): Promise<KbDoc[]> {
  if (!existsSync(dir)) return []
  const entries = await readdir(dir, { withFileTypes: true })
  const mdFiles = entries
    .filter((entry) => entry.isFile() && entry.name.toLowerCase().endsWith('.md'))
    .map((entry) => entry.name)
    .sort()

  const docs: KbDoc[] = []
  for (const name of mdFiles) {
    const filename = name.replace(/\.md$/i, '')
    const content = (await readFile(join(dir, name), 'utf-8')).trim()
    docs.push({ filename, title: titleOf(content, filename), content })
  }
  return docs
}

async function readSourcesFrom(dir: string): Promise<KbSourceFile[]> {
  if (!existsSync(dir)) return []
  const entries = await readdir(dir, { withFileTypes: true })
  const files = entries.filter((entry) => entry.isFile())
  const sources: KbSourceFile[] = []
  for (const entry of files) {
    const info = await stat(join(dir, entry.name))
    sources.push({ filename: entry.name, sizeBytes: info.size })
  }
  return sources.sort((a, b) => a.filename.localeCompare(b.filename))
}

async function categoryRoot(category: ClipadorCategory): Promise<string> {
  const engineDir = await getEngineDir()
  return join(engineDir, 'kb', category)
}

export async function listCategory(category: ClipadorCategory): Promise<KbSnapshot> {
  const root = await categoryRoot(category)
  const [core, topics, sources] = await Promise.all([
    readDocsFrom(join(root, CORE_DIRNAME)),
    readDocsFrom(join(root, TOPICS_DIRNAME)),
    readSourcesFrom(join(root, SOURCES_DIRNAME))
  ])
  return { root, core, topics, sources }
}

export async function saveDoc(
  category: ClipadorCategory,
  section: KbSection,
  filename: string,
  content: string
): Promise<void> {
  const root = await categoryRoot(category)
  const dir = join(root, section === 'core' ? CORE_DIRNAME : TOPICS_DIRNAME)
  await mkdir(dir, { recursive: true })
  const safeName = sanitizeFilename(filename)
  await writeFile(join(dir, `${safeName}.md`), content, 'utf-8')
}

export async function deleteDoc(
  category: ClipadorCategory,
  section: KbSection,
  filename: string
): Promise<void> {
  const root = await categoryRoot(category)
  const dir = join(root, section === 'core' ? CORE_DIRNAME : TOPICS_DIRNAME)
  const safeName = sanitizeFilename(filename)
  const filePath = join(dir, `${safeName}.md`)
  if (existsSync(filePath)) {
    await rm(filePath)
  }
}

export async function addSource(
  mainWindow: BrowserWindow,
  category: ClipadorCategory
): Promise<string | null> {
  const result = await dialog.showOpenDialog(mainWindow, {
    title: 'Adicionar arquivo de referencia',
    properties: ['openFile']
  })
  if (result.canceled || result.filePaths.length === 0) return null

  const sourcePath = result.filePaths[0]
  const root = await categoryRoot(category)
  const dir = join(root, SOURCES_DIRNAME)
  await mkdir(dir, { recursive: true })
  const filename = basename(sourcePath)
  await copyFile(sourcePath, join(dir, filename))
  return filename
}

export async function removeSource(category: ClipadorCategory, filename: string): Promise<void> {
  const root = await categoryRoot(category)
  const filePath = join(root, SOURCES_DIRNAME, basename(filename))
  if (existsSync(filePath)) {
    await rm(filePath)
  }
}
