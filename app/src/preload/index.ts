import { contextBridge, ipcRenderer } from 'electron'
import { IpcChannel } from '../shared/ipc-channels'
import type {
  AppInfo,
  ClipadorApi,
  ClipadorCategory,
  ClipJobArgs,
  EngineExitEvent,
  EngineLogEvent,
  EngineProgressEvent,
  EngineSettings,
  FeaturesConfig,
  JobHandle,
  KbSection,
  RebrandJobArgs,
  Unsubscribe,
  UpdateStatus,
  WatermarkFormat
} from '../shared/ipc-contract'

/**
 * Implementacao real do lado do preload: so encaminha para ipcRenderer.
 * Os handlers do lado main (ipcMain.handle) ainda nao existem, worker-2
 * os implementa em src/main usando os mesmos canais de ../shared/ipc-channels.
 */
const api: ClipadorApi = {
  settings: {
    get: () => ipcRenderer.invoke(IpcChannel.settingsGet),
    save: (settings: EngineSettings) => ipcRenderer.invoke(IpcChannel.settingsSave, settings)
  },
  dialogs: {
    pickVideoFile: () => ipcRenderer.invoke(IpcChannel.dialogsPickVideoFile),
    pickFolder: () => ipcRenderer.invoke(IpcChannel.dialogsPickFolder),
    pickPngFile: () => ipcRenderer.invoke(IpcChannel.dialogsPickPngFile),
    openInFileManager: (path: string) =>
      ipcRenderer.invoke(IpcChannel.dialogsOpenInFileManager, path)
  },
  engine: {
    runClip: (args: ClipJobArgs): Promise<JobHandle> =>
      ipcRenderer.invoke(IpcChannel.engineRunClip, args),
    runRebrand: (args: RebrandJobArgs): Promise<JobHandle> =>
      ipcRenderer.invoke(IpcChannel.engineRunRebrand, args),
    cancel: (jobId: string) => ipcRenderer.invoke(IpcChannel.engineCancel, jobId),
    onLog: (jobId: string, callback: (event: EngineLogEvent) => void): Unsubscribe => {
      const listener = (_event: Electron.IpcRendererEvent, payload: EngineLogEvent): void => {
        if (payload.jobId === jobId) callback(payload)
      }
      ipcRenderer.on(IpcChannel.engineLogEvent, listener)
      return () => ipcRenderer.removeListener(IpcChannel.engineLogEvent, listener)
    },
    onExit: (jobId: string, callback: (event: EngineExitEvent) => void): Unsubscribe => {
      const listener = (_event: Electron.IpcRendererEvent, payload: EngineExitEvent): void => {
        if (payload.jobId === jobId) callback(payload)
      }
      ipcRenderer.on(IpcChannel.engineExitEvent, listener)
      return () => ipcRenderer.removeListener(IpcChannel.engineExitEvent, listener)
    },
    onProgress: (jobId: string, callback: (event: EngineProgressEvent) => void): Unsubscribe => {
      const listener = (_event: Electron.IpcRendererEvent, payload: EngineProgressEvent): void => {
        if (payload.jobId === jobId) callback(payload)
      }
      ipcRenderer.on(IpcChannel.engineProgressEvent, listener)
      return () => ipcRenderer.removeListener(IpcChannel.engineProgressEvent, listener)
    }
  },
  kb: {
    list: (category: ClipadorCategory) => ipcRenderer.invoke(IpcChannel.kbList, category),
    saveDoc: (category: ClipadorCategory, section: KbSection, filename: string, content: string) =>
      ipcRenderer.invoke(IpcChannel.kbSaveDoc, category, section, filename, content),
    deleteDoc: (category: ClipadorCategory, section: KbSection, filename: string) =>
      ipcRenderer.invoke(IpcChannel.kbDeleteDoc, category, section, filename),
    addSource: (category: ClipadorCategory) => ipcRenderer.invoke(IpcChannel.kbAddSource, category),
    removeSource: (category: ClipadorCategory, filename: string) =>
      ipcRenderer.invoke(IpcChannel.kbRemoveSource, category, filename)
  },
  features: {
    get: () => ipcRenderer.invoke(IpcChannel.featuresGet),
    save: (config: FeaturesConfig) => ipcRenderer.invoke(IpcChannel.featuresSave, config)
  },
  watermark: {
    pickSourceImage: () => ipcRenderer.invoke(IpcChannel.watermarkPickSourceImage),
    readSourceImage: () => ipcRenderer.invoke(IpcChannel.watermarkReadSourceImage),
    removeSourceImage: () => ipcRenderer.invoke(IpcChannel.watermarkRemoveSourceImage),
    saveBakedImage: (format: WatermarkFormat, pngBytes: ArrayBuffer) =>
      ipcRenderer.invoke(IpcChannel.watermarkSaveBakedImage, format, pngBytes),
    readBakedImage: (format: WatermarkFormat) =>
      ipcRenderer.invoke(IpcChannel.watermarkReadBakedImage, format)
  },
  app: {
    getInfo: (): Promise<AppInfo> => ipcRenderer.invoke(IpcChannel.appGetInfo),
    checkForUpdates: () => ipcRenderer.invoke(IpcChannel.appCheckForUpdates),
    quitAndInstall: () => ipcRenderer.invoke(IpcChannel.appQuitAndInstall),
    onUpdateStatus: (callback: (status: UpdateStatus) => void): Unsubscribe => {
      const listener = (_event: Electron.IpcRendererEvent, payload: UpdateStatus): void => callback(payload)
      ipcRenderer.on(IpcChannel.appUpdateStatusEvent, listener)
      return () => ipcRenderer.removeListener(IpcChannel.appUpdateStatusEvent, listener)
    }
  }
}

contextBridge.exposeInMainWorld('api', api)
