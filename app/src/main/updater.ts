import { app, type BrowserWindow } from 'electron'
import electronUpdaterPkg from 'electron-updater'
import { IpcChannel } from '../shared/ipc-channels'
import type { AppInfo, UpdateStatus } from '../shared/ipc-contract'

// electron-updater e CommonJS: em build empacotado (Node ESM real, nao o transform do
// Vite que o `npm run dev` usa) um `import { autoUpdater } from 'electron-updater'`
// nomeado falha em runtime ("Named export 'autoUpdater' not found") porque o loader ESM
// nativo do Node nao consegue extrair esse export estaticamente do CJS. Import default +
// destructure e o jeito que funciona nos dois casos.
const { autoUpdater } = electronUpdaterPkg

autoUpdater.autoDownload = true
autoUpdater.autoInstallOnAppQuit = true

function send(window: BrowserWindow, status: UpdateStatus): void {
  if (window.isDestroyed()) return
  window.webContents.send(IpcChannel.appUpdateStatusEvent, status)
}

/** So faz sentido no .exe instalado: em dev nao ha `latest.yml` publicado nem faz
 * sentido sobrescrever o checkout local. */
export function initAutoUpdater(window: BrowserWindow): void {
  if (!app.isPackaged) return

  autoUpdater.on('checking-for-update', () => send(window, { state: 'checking' }))
  autoUpdater.on('update-available', (info) => send(window, { state: 'available', version: info.version }))
  autoUpdater.on('update-not-available', () => send(window, { state: 'not-available' }))
  autoUpdater.on('download-progress', (progress) =>
    send(window, { state: 'downloading', percent: Math.round(progress.percent) })
  )
  autoUpdater.on('update-downloaded', (info) => send(window, { state: 'downloaded', version: info.version }))
  autoUpdater.on('error', (error) => send(window, { state: 'error', message: error.message }))

  // O evento 'error' acima ja reporta pra UI; so evita promise rejeitada sem handler
  // (checkForUpdates falha sempre que nao ha app-update.yml, ex: build --dir de teste,
  // ou sem internet - nenhum dos dois deve derrubar o processo).
  autoUpdater.checkForUpdates().catch((error: unknown) => {
    console.error('[updater] checkForUpdates falhou:', error)
  })
}

export async function checkForUpdates(): Promise<void> {
  if (!app.isPackaged) return
  await autoUpdater.checkForUpdates()
}

export function quitAndInstall(): void {
  autoUpdater.quitAndInstall()
}

export function getAppInfo(): AppInfo {
  return { version: app.getVersion(), isPackaged: app.isPackaged }
}
