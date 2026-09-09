import { dialog, shell, type BrowserWindow } from 'electron'

const VIDEO_EXTENSIONS = ['mp4', 'mkv', 'mov', 'avi', 'webm', 'm4v']

export async function pickVideoFile(window: BrowserWindow): Promise<string | null> {
  const result = await dialog.showOpenDialog(window, {
    properties: ['openFile'],
    filters: [{ name: 'Video', extensions: VIDEO_EXTENSIONS }]
  })
  if (result.canceled || result.filePaths.length === 0) return null
  return result.filePaths[0]
}

export async function pickFolder(window: BrowserWindow): Promise<string | null> {
  const result = await dialog.showOpenDialog(window, {
    properties: ['openDirectory']
  })
  if (result.canceled || result.filePaths.length === 0) return null
  return result.filePaths[0]
}

export async function pickPngFile(window: BrowserWindow): Promise<string | null> {
  const result = await dialog.showOpenDialog(window, {
    properties: ['openFile'],
    filters: [{ name: 'PNG', extensions: ['png'] }]
  })
  if (result.canceled || result.filePaths.length === 0) return null
  return result.filePaths[0]
}

export function openInFileManager(path: string): void {
  shell.showItemInFolder(path)
}
