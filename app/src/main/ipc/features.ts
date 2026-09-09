import { existsSync } from 'node:fs'
import { readFile, rm, writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { app } from 'electron'
import type { FeaturesConfig, WatermarkFormatState } from '../../shared/ipc-contract'
import { bakedImagePath } from './watermark'

const FEATURES_FILE_NAME = 'clipador-features.json'

// Canto superior esquerdo sempre por padrao: e onde a interface da propria plataforma
// (icones do TikTok/Shorts, controles do YouTube) NUNCA aparece, ao contrario do inferior
// direito/faixa de baixo (ver watermarkSafeZone.ts).
const DEFAULT_SHORT_STATE: WatermarkFormatState = { x: 0.15, y: 0.1, widthFraction: 0.18 }
const DEFAULT_LONG_STATE: WatermarkFormatState = { x: 0.12, y: 0.1, widthFraction: 0.12 }

/** Sobe este numero sempre que o default/zona reservada da marca d'agua mudar de um
 * jeito que invalida posicao (e PNG ja assado) gravados por uma versao anterior. Um
 * arquivo sem este campo (ou com valor menor) e de ANTES da mudanca: a posicao antiga
 * pode estar dentro da zona agora reservada, e o PNG ja assado com aquela posicao
 * continua sendo o que o engine realmente usa (a UI so mostra onde a logo fica, ela
 * nao re-assa sozinha) - so trocar o default no codigo nao corrige um arquivo ja
 * gravado no disco do usuario. Ver o bug real: usuario relatou marca d'agua do formato
 * longo aparecendo no canto errado mesmo depois do default ter virado canto superior
 * esquerdo, porque o PNG velho (assado com a posicao antiga) continuava intacto. */
const WATERMARK_LAYOUT_VERSION = 1

interface StoredFeaturesFile extends Partial<FeaturesConfig> {
  _watermarkLayoutVersion?: number
}

function featuresFilePath(): string {
  return join(app.getPath('userData'), FEATURES_FILE_NAME)
}

function defaultFeaturesConfig(): FeaturesConfig {
  return {
    watermark: {
      enabled: false,
      sourceImagePath: null,
      short: DEFAULT_SHORT_STATE,
      long: DEFAULT_LONG_STATE
    },
    eleitoral: {
      enabled: false,
      text: ''
    }
  }
}

async function deleteBakedImageIfExists(format: 'short' | 'long'): Promise<void> {
  const path = bakedImagePath(format)
  if (existsSync(path)) {
    await rm(path)
  }
}

/** Reseta posicao/tamanho pro default atual e apaga os PNGs ja assados (que ainda
 * carregam a posicao velha) - forca o usuario a reposicionar e salvar de novo antes de
 * poder ligar a marca d'agua, em vez de continuar aplicando silenciosamente um PNG
 * gerado com layout que a UI ja nao mostra mais como valido. */
async function migrateWatermarkLayout(config: FeaturesConfig): Promise<FeaturesConfig> {
  await Promise.all([deleteBakedImageIfExists('short'), deleteBakedImageIfExists('long')])
  return {
    ...config,
    watermark: {
      ...config.watermark,
      enabled: false,
      short: DEFAULT_SHORT_STATE,
      long: DEFAULT_LONG_STATE
    }
  }
}

export async function getFeatures(): Promise<FeaturesConfig> {
  const defaults = defaultFeaturesConfig()

  const filePath = featuresFilePath()
  if (!existsSync(filePath)) return defaults

  try {
    const raw = await readFile(filePath, 'utf-8')
    const parsed = JSON.parse(raw) as StoredFeaturesFile
    let config: FeaturesConfig = {
      watermark: { ...defaults.watermark, ...parsed.watermark },
      eleitoral: { ...defaults.eleitoral, ...parsed.eleitoral }
    }

    if ((parsed._watermarkLayoutVersion ?? 0) < WATERMARK_LAYOUT_VERSION) {
      config = await migrateWatermarkLayout(config)
      await writeStoredFile(config)
    }

    return config
  } catch {
    return defaults
  }
}

async function writeStoredFile(config: FeaturesConfig): Promise<void> {
  const stored: StoredFeaturesFile = { ...config, _watermarkLayoutVersion: WATERMARK_LAYOUT_VERSION }
  await writeFile(featuresFilePath(), JSON.stringify(stored, null, 2), 'utf-8')
}

export async function saveFeatures(config: FeaturesConfig): Promise<void> {
  await writeStoredFile(config)
}
