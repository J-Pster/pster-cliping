import { existsSync } from 'node:fs'
import { mkdir, readdir, readFile, rm, writeFile, copyFile } from 'node:fs/promises'
import { dirname, extname, join } from 'node:path'
import { app, dialog, type BrowserWindow } from 'electron'
import type {
  WatermarkBakeResult,
  WatermarkFormat,
  WatermarkSourceImageResult
} from '../../shared/ipc-contract'

const SOURCE_FILE_STEM = 'source'

export function bakedImagePath(format: WatermarkFormat): string {
  return join(app.getPath('userData'), 'watermark', format === 'short' ? 'short.png' : 'long.png')
}

function watermarkDir(): string {
  return join(app.getPath('userData'), 'watermark')
}

function mimeForExtension(ext: string): string {
  const normalized = ext.toLowerCase()
  return normalized === '.jpg' || normalized === '.jpeg' ? 'image/jpeg' : 'image/png'
}

async function dataUrlFor(filePath: string): Promise<string> {
  const buffer = await readFile(filePath)
  return `data:${mimeForExtension(extname(filePath))};base64,${buffer.toString('base64')}`
}

/** Acha o arquivo "source.*" ja copiado, se existir. So pode haver um por vez: uma nova
 * escolha SUBSTITUI a copia anterior, mesmo que a extensao mude (png -> jpg etc). */
async function findExistingSourceFile(): Promise<string | null> {
  const dir = watermarkDir()
  if (!existsSync(dir)) return null
  const entries = await readdir(dir)
  const match = entries.find((name) => name.startsWith(`${SOURCE_FILE_STEM}.`))
  return match ? join(dir, match) : null
}

/** Abre o seletor nativo, COPIA o arquivo escolhido pra dentro da pasta gerenciada do
 * app (nunca referencia o caminho original do usuario - ele pode mover ou apagar o
 * arquivo depois) e devolve o caminho novo + uma data: URL pronta pra preview.
 *
 * Usar file:// pra pre-visualizar a imagem-fonte (versao anterior desta tela) causava
 * "tainted canvas": o Chromium trata file:// como origem diferente da pagina do app, e
 * um canvas que desenhou uma imagem de origem diferente nao pode ser lido de volta via
 * toBlob/toDataURL (SecurityError) - exatamente o passo que "asssa" a imagem final no
 * tamanho do quadro. data: URL nao tem essa restricao, por isso a copia + leitura aqui,
 * em vez de so devolver o caminho original. */
export async function pickSourceImage(mainWindow: BrowserWindow): Promise<WatermarkSourceImageResult | null> {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openFile'],
    filters: [{ name: 'Imagem', extensions: ['png', 'jpg', 'jpeg'] }]
  })
  if (result.canceled || result.filePaths.length === 0) return null

  const pickedPath = result.filePaths[0]
  const dir = watermarkDir()
  await mkdir(dir, { recursive: true })

  const existing = await findExistingSourceFile()
  if (existing) {
    await rm(existing)
  }

  const targetPath = join(dir, `${SOURCE_FILE_STEM}${extname(pickedPath).toLowerCase()}`)
  await copyFile(pickedPath, targetPath)

  return { path: targetPath, previewDataUrl: await dataUrlFor(targetPath) }
}

export async function readSourceImage(): Promise<string | null> {
  const existing = await findExistingSourceFile()
  if (!existing) return null
  return dataUrlFor(existing)
}

export async function removeSourceImage(): Promise<void> {
  const existing = await findExistingSourceFile()
  if (existing) {
    await rm(existing)
  }
}

export async function saveBakedImage(
  format: WatermarkFormat,
  pngBytes: ArrayBuffer
): Promise<WatermarkBakeResult> {
  const filePath = bakedImagePath(format)
  await mkdir(dirname(filePath), { recursive: true })
  const buffer = Buffer.from(pngBytes)
  await writeFile(filePath, buffer)
  return {
    path: filePath,
    previewDataUrl: 'data:image/png;base64,' + buffer.toString('base64')
  }
}

export async function readBakedImage(format: WatermarkFormat): Promise<string | null> {
  const filePath = bakedImagePath(format)
  if (!existsSync(filePath)) return null
  const buffer = await readFile(filePath)
  return 'data:image/png;base64,' + buffer.toString('base64')
}
