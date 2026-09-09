/// <reference types="vite/client" />

import type { ClipadorApi } from '@shared/ipc-contract'

declare global {
  interface Window {
    api: ClipadorApi
  }

  /** Injetado em build-time pelo electron.vite.config.ts a partir de package.json,
   * pra versao mostrada no cabecalho ficar sempre igual a versao real do app. */
  const __APP_VERSION__: string
}
