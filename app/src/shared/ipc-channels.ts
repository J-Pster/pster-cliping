/**
 * Nomes de canal IPC compartilhados entre preload (invoke) e main (handle).
 * Mantidos num arquivo separado do contrato de tipos para que os dois lados
 * (worker-2 no main, worker-3 no renderer) referenciem a mesma constante.
 */
export const IpcChannel = {
  settingsGet: 'settings:get',
  settingsSave: 'settings:save',
  dialogsPickVideoFile: 'dialogs:pick-video-file',
  dialogsPickFolder: 'dialogs:pick-folder',
  dialogsPickPngFile: 'dialogs:pick-png-file',
  dialogsOpenInFileManager: 'dialogs:open-in-file-manager',
  engineRunClip: 'engine:run-clip',
  engineRunRebrand: 'engine:run-rebrand',
  engineCancel: 'engine:cancel',
  /** Evento (main -> renderer) de log de um job; payload e EngineLogEvent. */
  engineLogEvent: 'engine:log-event',
  /** Evento (main -> renderer) de saida de um job; payload e EngineExitEvent. */
  engineExitEvent: 'engine:exit-event',
  /** Evento (main -> renderer) de progresso estruturado; payload e EngineProgressEvent. */
  engineProgressEvent: 'engine:progress-event',
  kbList: 'kb:list',
  kbSaveDoc: 'kb:save-doc',
  kbDeleteDoc: 'kb:delete-doc',
  kbAddSource: 'kb:add-source',
  kbRemoveSource: 'kb:remove-source',
  featuresGet: 'features:get',
  featuresSave: 'features:save',
  watermarkPickSourceImage: 'watermark:pick-source-image',
  watermarkReadSourceImage: 'watermark:read-source-image',
  watermarkRemoveSourceImage: 'watermark:remove-source-image',
  watermarkSaveBakedImage: 'watermark:save-baked-image',
  watermarkReadBakedImage: 'watermark:read-baked-image',
  appGetInfo: 'app:get-info',
  appCheckForUpdates: 'app:check-for-updates',
  appQuitAndInstall: 'app:quit-and-install',
  /** Evento (main -> renderer) de progresso do auto-update; payload e UpdateStatus. */
  appUpdateStatusEvent: 'app:update-status-event'
} as const
