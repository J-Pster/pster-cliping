/**
 * Contrato de IPC entre main (worker-2) e renderer (worker-3). Ambos os lados
 * implementam contra este arquivo sem precisar tocar no codigo um do outro.
 *
 * `window.api` (exposto pelo preload via contextBridge) segue exatamente esta forma.
 */

// ---------------------------------------------------------------------------
// Configuracao do engine (settings screen)
// ---------------------------------------------------------------------------

export type TextLlmProvider = 'claude' | 'gemini'
export type LlmAuthMode = 'oauth' | 'api_key'

/** Espelha 1:1 as variaveis de engine/.env.example. */
export interface EngineEnvVars {
  CLIPADOR_TEXT_LLM_PROVIDER: TextLlmProvider
  CLIPADOR_LLM_AUTH_MODE: LlmAuthMode
  CLAUDE_CODE_OAUTH_TOKEN: string
  ANTHROPIC_API_KEY: string
  HUGGINGFACE_TOKEN: string
  ELEVENLABS_API_KEY: string
  ASSEMBLYAI_API_KEY: string
  GEMINI_API_KEY: string
  CLIPADOR_GEMINI_TEXT_MODEL: string
  BUFFER_API_KEY: string
  BUFFER_CHANNEL_COMMIT_CIVICO_YOUTUBE: string
  BUFFER_CHANNEL_COMMIT_CIVICO_INSTAGRAM: string
  BUFFER_CHANNEL_COMMIT_CIVICO_TIKTOK: string
  BUFFER_CHANNEL_PESSOAL_YOUTUBE: string
  BUFFER_CHANNEL_PESSOAL_INSTAGRAM: string
  BUFFER_CHANNEL_PESSOAL_TIKTOK: string
}

/** Configuracao completa persistida localmente (nao vai para engine/.env diretamente). */
export interface EngineSettings extends EngineEnvVars {
  /** Caminho absoluto para a pasta engine/ (repo do pipeline Python). */
  engineDir: string
  /** Caminho absoluto do executavel Python (venv) usado para rodar o engine. */
  pythonPath: string
}

// ---------------------------------------------------------------------------
// Dominio compartilhado do engine (categorias, presets, backends)
// ---------------------------------------------------------------------------

export type ClipadorCategory = 'politico_pessoa' | 'jogos' | 'livro_audiobook'

export type SubtitlePreset = 'impacto' | 'anton' | 'neon' | 'classico'

// whisperx/faster-whisper (transcricao local) nao vem no runtime embutido do app: o
// projeto so usa transcricao em nuvem (ver engine/CLAUDE.md), e bundlar torch so pra
// isso inflava o instalador em dezenas de milhares de arquivos a toa. O engine em si
// ainda suporta esses backends via CLI direta (--transcriber whisperx), so o app
// empacotado nao os oferece nem os embute.
export type TranscriberBackend = 'assemblyai' | 'elevenlabs'

export type OnOff = 'on' | 'off'

// ---------------------------------------------------------------------------
// Argumentos de job (mirror 1:1 dos flags da CLI)
// ---------------------------------------------------------------------------

/** Mirror de `clipador.cli` (comando `clipador <input> --category ... --watermark ...`). */
export interface ClipJobArgs {
  /** URL do YouTube ou caminho de um arquivo de video local. */
  input: string
  category: ClipadorCategory
  /** Raiz da base de conhecimento; default kb/<category> quando omitido. */
  kb?: string
  movement?: string
  /** Raiz da pasta de saida; default "output". */
  output?: string
  /** Pasta de artefatos intermediarios; default ".clipador". */
  workDir?: string
  /** Meta de melhor esforco de clipes curtos NOVOS (9:16); default 5. */
  minShortClips?: number
  /** Meta de melhor esforco de clipes longos NOVOS (16:9); default 5. */
  minLongClips?: number
  /** Obrigatorio: liga/desliga a marca d'agua. */
  watermark: OnOff
  /** PNG da marca d'agua do formato curto (9:16). Exigido quando watermark = "on". */
  watermarkShort?: string
  /** PNG da marca d'agua do formato longo (16:9). Exigido quando watermark = "on". */
  watermarkLong?: string
  /** @ do canal no ready-to-post.txt; string vazia = nenhuma mencao. */
  handle?: string
  /** Look da legenda queimada; default "impacto". */
  subtitlePreset?: SubtitlePreset
  /** Diretorio das fontes .ttf embarcadas (default assets/fonts do engine). */
  fontsDir?: string
  /** Sobrescreve a caixa alta do preset quando definido. */
  subtitleUppercase?: OnOff
  /** Marca palavras-chave do trecho com cor propria na legenda, via LLM extra. */
  subtitleEmphasis?: boolean
  /** Backend de transcricao; default "elevenlabs". */
  transcriber?: TranscriberBackend
  /** Tamanho do modelo Whisper; default "large-v3"; ignorado por assemblyai. */
  transcriberModel?: string
  /** 'cuda' | 'cpu' | 'auto'; default "auto". */
  transcriberDevice?: string
  /** 'float16' | 'int8' | ... | 'auto'; default "auto". */
  transcriberComputeType?: string
  /** Liga a diarizacao (quem fala quando). */
  diarize?: boolean
  /** Obrigatorio: gera ("on") ou pula por completo ("off") a thumbnail de cada clipe,
   * curto e longo. Escolha por rodada, como watermark - sem default silencioso na UI. */
  generateThumbnails: OnOff
  /** Quando true, desliga a composicao de thumbnail (salva o frame cru). So importa
   * quando generateThumbnails = "on". */
  disableThumbnailComposition?: boolean
  /** Alem dos cortes, gera tambem a thumbnail do video principal inteiro. */
  generateMainThumbnail?: boolean
  /** Caminho do blaze_face_short_range.tflite. */
  faceModelPath?: string
  /** Navegador local logado para ler cookies de sessao ('firefox', 'chrome', 'edge', ...). */
  cookiesFromBrowser?: string
  verbose?: boolean
}

/** Mirror de `clipador.rebrand.cli` (comando `clipador-rebrand <input_dir> --category ...`). */
export interface RebrandJobArgs {
  /** Pasta contendo os videos curtos a re-brandear. */
  inputDir: string
  category: ClipadorCategory
  kb?: string
  movement?: string
  /** Raiz da pasta de saida; default "output". */
  output?: string
  /** Pasta de artefatos intermediarios; default ".clipador". */
  workDir?: string
  /** Nome da pasta de saida do lote; default rebrand_<nome-da-pasta-de-entrada>. */
  batchName?: string
  /** Imagem estatica do outro/encerramento. Exigido para categorias != politico_pessoa. */
  outroImage?: string
  /** Duracao em segundos do outro/encerramento; default 5.0. */
  outroDuration?: number
  /** Quando true, desliga a composicao de thumbnail (salva o frame cru). */
  disableThumbnailComposition?: boolean
  /** Caminho do blaze_face_short_range.tflite. */
  faceModelPath?: string
  /** Processa so os N primeiros videos (ordem alfabetica). */
  limit?: number
  verbose?: boolean
}

// ---------------------------------------------------------------------------
// Execucao de jobs e streaming de eventos
// ---------------------------------------------------------------------------

export interface JobHandle {
  jobId: string
}

export interface EngineLogEvent {
  jobId: string
  stream: 'stdout' | 'stderr'
  line: string
  timestamp: number
}

export interface EngineExitEvent {
  jobId: string
  code: number | null
  signal: string | null
  timestamp: number
}

/**
 * Progresso estruturado emitido pelo engine (ver engine/src/clipador/progress.py),
 * uma linha "CLIPADOR_PROGRESS <json>" no stdout por evento. `event` distingue o
 * formato do payload:
 * - "phase": mudanca de fase (download, transcribe, select, main_thumbnail); usa
 *   `phase` + `message`, sem indice/total.
 * - "plan": plano de clipes/videos calculado; `total` = quantos serao processados.
 * - "clip_start" / "clip_done" / "clip_failed": um clipe (ou video, no rebrand)
 *   comecou, terminou com sucesso ou falhou; `index`/`total` da a posicao no plano.
 */
export interface EngineProgressEvent {
  jobId: string
  timestamp: number
  event: 'phase' | 'plan' | 'clip_start' | 'clip_done' | 'clip_failed'
  phase?: string
  message?: string
  index?: number
  total?: number
  clipId?: string
  format?: string
  directory?: string
  status?: string
  stage?: string
}

/** Retornado por onLog/onExit para cancelar a subscricao. */
export type Unsubscribe = () => void

// ---------------------------------------------------------------------------
// Base de conhecimento (kb/<category>/{core,topics,sources})
// ---------------------------------------------------------------------------

export type KbSection = 'core' | 'topics'

/** Um documento markdown do dossie (core) ou de topico (topics). */
export interface KbDoc {
  /** Nome do arquivo sem extensao, ex. "10-pautas". Define a ordem (glob ordenado). */
  filename: string
  /** Extraido da primeira linha "# Titulo" do arquivo; igual ao filename se nao houver. */
  title: string
  /** Conteudo markdown completo, incluindo a linha "# Titulo". */
  content: string
}

/** Um arquivo de referencia bruto (PDF, etc) dentro de kb/<category>/sources/. */
export interface KbSourceFile {
  filename: string
  sizeBytes: number
}

export interface KbSnapshot {
  /** Caminho absoluto de kb/<category>, mesmo que a pasta ainda nao exista. */
  root: string
  core: KbDoc[]
  topics: KbDoc[]
  sources: KbSourceFile[]
}

// ---------------------------------------------------------------------------
// Marca d'agua e propaganda eleitoral: configuracao GLOBAL, persistida uma vez e
// aplicada automaticamente a TODO clipe curto gerado depois (New Clip e Rebrand),
// nao e escolha feita a cada rodada. O main process injeta essas flags no argv na
// hora de rodar o engine; New Clip/Rebrand nao pedem mais isso ao usuario.
// ---------------------------------------------------------------------------

export type WatermarkFormat = 'short' | 'long'

/** Posicao/tamanho da logo dentro do quadro de um formato, em fracao (0-1) do
 * quadro - independente de resolucao de tela, usado tanto pelo editor quanto na
 * hora de "assar" o PNG final no tamanho real (1080x1920 ou 1920x1080). */
export interface WatermarkFormatState {
  /** Fracao (0-1) da largura/altura do quadro onde fica o CENTRO da logo. */
  x: number
  y: number
  /** Fracao (0-1) da largura do quadro ocupada pela logo; a altura segue a
   * proporcao original da imagem-fonte (nunca distorce). */
  widthFraction: number
}

export interface WatermarkConfig {
  enabled: boolean
  /** Caminho absoluto da imagem-fonte enviada pelo usuario (a logo crua, antes de
   * posicionada em cada formato). Null se nada foi enviado ainda. */
  sourceImagePath: string | null
  short: WatermarkFormatState
  long: WatermarkFormatState
}

export interface EleitoralConfig {
  enabled: boolean
  text: string
}

export interface FeaturesConfig {
  watermark: WatermarkConfig
  eleitoral: EleitoralConfig
}

export interface WatermarkBakeResult {
  /** Caminho absoluto do PNG final gravado, pronto para --watermark-short/--watermark-long. */
  path: string
  /** data: URL do PNG final, para preview imediato sem reler do disco. */
  previewDataUrl: string
}

/** Resultado de escolher/substituir a imagem-fonte: o main process ja COPIOU o arquivo
 * pra dentro da pasta gerenciada do app (nao referencia o caminho original do usuario,
 * que pode ser movido/apagado depois), e devolve o novo caminho + uma data: URL pronta
 * pra preview sem reler do disco (data: URL evita "tainted canvas" ao bakear depois,
 * o que file:// causava). */
export interface WatermarkSourceImageResult {
  path: string
  previewDataUrl: string
}

// ---------------------------------------------------------------------------
// Superficie completa exposta em window.api pelo preload
// ---------------------------------------------------------------------------

export interface SettingsApi {
  get(): Promise<EngineSettings>
  save(settings: EngineSettings): Promise<void>
}

export interface DialogsApi {
  pickVideoFile(): Promise<string | null>
  pickFolder(): Promise<string | null>
  pickPngFile(): Promise<string | null>
  openInFileManager(path: string): Promise<void>
}

export interface EngineApi {
  runClip(args: ClipJobArgs): Promise<JobHandle>
  runRebrand(args: RebrandJobArgs): Promise<JobHandle>
  cancel(jobId: string): Promise<void>
  onLog(jobId: string, callback: (event: EngineLogEvent) => void): Unsubscribe
  onExit(jobId: string, callback: (event: EngineExitEvent) => void): Unsubscribe
  onProgress(jobId: string, callback: (event: EngineProgressEvent) => void): Unsubscribe
}

export interface KbApi {
  list(category: ClipadorCategory): Promise<KbSnapshot>
  saveDoc(category: ClipadorCategory, section: KbSection, filename: string, content: string): Promise<void>
  deleteDoc(category: ClipadorCategory, section: KbSection, filename: string): Promise<void>
  /** Abre um seletor de arquivo (qualquer tipo) e copia pra kb/<category>/sources/. Null se cancelado. */
  addSource(category: ClipadorCategory): Promise<string | null>
  removeSource(category: ClipadorCategory, filename: string): Promise<void>
}

export interface FeaturesApi {
  get(): Promise<FeaturesConfig>
  save(config: FeaturesConfig): Promise<void>
}

export interface WatermarkApi {
  /** Abre seletor de imagem (PNG/JPG), COPIA o arquivo escolhido pra pasta gerenciada do
   * app e devolve o novo caminho + preview. Null se cancelado. Chamar de novo com uma
   * imagem ja existente SUBSTITUI a copia anterior. */
  pickSourceImage(): Promise<WatermarkSourceImageResult | null>
  /** data: URL da imagem-fonte ja copiada (se houver). Null se nenhuma foi enviada ainda. */
  readSourceImage(): Promise<string | null>
  /** Apaga a copia local da imagem-fonte. Nao mexe nos PNGs ja assados (short/long). */
  removeSourceImage(): Promise<void>
  /** Recebe os bytes PNG ja renderizados pelo canvas do editor e grava em disco. */
  saveBakedImage(format: WatermarkFormat, pngBytes: ArrayBuffer): Promise<WatermarkBakeResult>
  /** Le o PNG ja gravado (se existir) como data: URL, para preview ao reabrir a tela. Null se
   * este formato ainda nunca foi salvo. */
  readBakedImage(format: WatermarkFormat): Promise<string | null>
}

// ---------------------------------------------------------------------------
// Info do app e auto-update (electron-updater, so ativo em build empacotado)
// ---------------------------------------------------------------------------

export interface AppInfo {
  version: string
  /** false ao rodar via `npm run dev`; true no .exe instalado (usa engine/python
   * embutidos nos resources em vez do checkout do monorepo, ver runtime-paths.ts). */
  isPackaged: boolean
}

export type UpdateStatus =
  | { state: 'checking' }
  | { state: 'available'; version: string }
  | { state: 'not-available' }
  | { state: 'downloading'; percent: number }
  | { state: 'downloaded'; version: string }
  | { state: 'error'; message: string }

export interface AppApi {
  getInfo(): Promise<AppInfo>
  /** Dispara uma checagem manual (o app tambem checa sozinho ao abrir). */
  checkForUpdates(): Promise<void>
  /** So funciona depois de um UpdateStatus com state "downloaded"; fecha e reabre
   * o app ja atualizado. */
  quitAndInstall(): Promise<void>
  onUpdateStatus(callback: (status: UpdateStatus) => void): Unsubscribe
}

export interface ClipadorApi {
  settings: SettingsApi
  dialogs: DialogsApi
  engine: EngineApi
  kb: KbApi
  features: FeaturesApi
  watermark: WatermarkApi
  app: AppApi
}
