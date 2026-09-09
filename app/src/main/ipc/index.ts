import { ipcMain, type BrowserWindow } from 'electron'
import { IpcChannel } from '../../shared/ipc-channels'
import type {
  ClipadorCategory,
  ClipJobArgs,
  EngineSettings,
  FeaturesConfig,
  KbSection,
  RebrandJobArgs,
  WatermarkFormat
} from '../../shared/ipc-contract'
import { openInFileManager, pickFolder, pickPngFile, pickVideoFile } from './dialogs'
import { cancelJob, runClip, runRebrand } from './engine'
import { getSettings, saveSettings } from './settings'
import { addSource, deleteDoc, listCategory, removeSource, saveDoc } from './kb'
import { getFeatures, saveFeatures } from './features'
import {
  pickSourceImage,
  readBakedImage,
  readSourceImage,
  removeSourceImage,
  saveBakedImage
} from './watermark'
import { checkForUpdates, getAppInfo, quitAndInstall } from '../updater'

export function registerIpcHandlers(mainWindow: BrowserWindow): void {
  ipcMain.handle(IpcChannel.appGetInfo, () => getAppInfo())
  ipcMain.handle(IpcChannel.appCheckForUpdates, () => checkForUpdates())
  ipcMain.handle(IpcChannel.appQuitAndInstall, () => quitAndInstall())

  ipcMain.handle(IpcChannel.settingsGet, () => getSettings())
  ipcMain.handle(IpcChannel.settingsSave, (_event, settings: EngineSettings) => saveSettings(settings))

  ipcMain.handle(IpcChannel.dialogsPickVideoFile, () => pickVideoFile(mainWindow))
  ipcMain.handle(IpcChannel.dialogsPickFolder, () => pickFolder(mainWindow))
  ipcMain.handle(IpcChannel.dialogsPickPngFile, () => pickPngFile(mainWindow))
  ipcMain.handle(IpcChannel.dialogsOpenInFileManager, (_event, path: string) => openInFileManager(path))

  ipcMain.handle(IpcChannel.engineRunClip, (_event, args: ClipJobArgs) => runClip(mainWindow, args))
  ipcMain.handle(IpcChannel.engineRunRebrand, (_event, args: RebrandJobArgs) =>
    runRebrand(mainWindow, args)
  )
  ipcMain.handle(IpcChannel.engineCancel, (_event, jobId: string) => cancelJob(jobId))

  ipcMain.handle(IpcChannel.kbList, (_event, category: ClipadorCategory) => listCategory(category))
  ipcMain.handle(
    IpcChannel.kbSaveDoc,
    (_event, category: ClipadorCategory, section: KbSection, filename: string, content: string) =>
      saveDoc(category, section, filename, content)
  )
  ipcMain.handle(
    IpcChannel.kbDeleteDoc,
    (_event, category: ClipadorCategory, section: KbSection, filename: string) =>
      deleteDoc(category, section, filename)
  )
  ipcMain.handle(IpcChannel.kbAddSource, (_event, category: ClipadorCategory) =>
    addSource(mainWindow, category)
  )
  ipcMain.handle(IpcChannel.kbRemoveSource, (_event, category: ClipadorCategory, filename: string) =>
    removeSource(category, filename)
  )

  ipcMain.handle(IpcChannel.featuresGet, () => getFeatures())
  ipcMain.handle(IpcChannel.featuresSave, (_event, config: FeaturesConfig) => saveFeatures(config))

  ipcMain.handle(IpcChannel.watermarkPickSourceImage, () => pickSourceImage(mainWindow))
  ipcMain.handle(IpcChannel.watermarkReadSourceImage, () => readSourceImage())
  ipcMain.handle(IpcChannel.watermarkRemoveSourceImage, () => removeSourceImage())
  ipcMain.handle(
    IpcChannel.watermarkSaveBakedImage,
    (_event, format: WatermarkFormat, pngBytes: ArrayBuffer) => saveBakedImage(format, pngBytes)
  )
  ipcMain.handle(IpcChannel.watermarkReadBakedImage, (_event, format: WatermarkFormat) =>
    readBakedImage(format)
  )
}
