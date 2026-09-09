import type { ClipJobArgs, FeaturesConfig, RebrandJobArgs } from '../../shared/ipc-contract'

/** Mirror de `clipador.cli` (engine/src/clipador/cli.py::build_parser). */
export function buildClipArgv(args: ClipJobArgs, features?: FeaturesConfig): string[] {
  const argv: string[] = ['-m', 'clipador.cli', args.input, '--category', args.category]

  if (args.kb) argv.push('--kb', args.kb)
  if (args.movement) argv.push('--movement', args.movement)
  if (args.output) argv.push('--output', args.output)
  if (args.workDir) argv.push('--work-dir', args.workDir)
  if (args.minShortClips !== undefined) argv.push('--min-short-clips', String(args.minShortClips))
  if (args.minLongClips !== undefined) argv.push('--min-long-clips', String(args.minLongClips))

  argv.push('--watermark', args.watermark)
  if (args.watermark === 'on') {
    if (args.watermarkShort) argv.push('--watermark-short', args.watermarkShort)
    if (args.watermarkLong) argv.push('--watermark-long', args.watermarkLong)
  }

  if (args.handle !== undefined) argv.push('--handle', args.handle)
  if (args.subtitlePreset) argv.push('--subtitle-preset', args.subtitlePreset)
  if (args.fontsDir) argv.push('--fonts-dir', args.fontsDir)
  if (args.subtitleUppercase) argv.push('--subtitle-uppercase', args.subtitleUppercase)
  if (args.subtitleEmphasis) argv.push('--subtitle-emphasis')

  if (args.transcriber) argv.push('--transcriber', args.transcriber)
  if (args.transcriberModel) argv.push('--transcriber-model', args.transcriberModel)
  if (args.transcriberDevice) argv.push('--transcriber-device', args.transcriberDevice)
  if (args.transcriberComputeType) {
    argv.push('--transcriber-compute-type', args.transcriberComputeType)
  }
  if (args.diarize) argv.push('--diarize')

  argv.push('--generate-thumbnails', args.generateThumbnails)
  if (args.generateThumbnails === 'on' && args.disableThumbnailComposition) {
    argv.push('--no-thumbnail-composition')
  }
  if (args.generateMainThumbnail) argv.push('--generate-main-thumbnail')
  if (args.faceModelPath) argv.push('--face-model-path', args.faceModelPath)
  if (args.cookiesFromBrowser) argv.push('--cookies-from-browser', args.cookiesFromBrowser)
  if (args.verbose) argv.push('--verbose')

  if (features?.eleitoral.enabled && features.eleitoral.text.trim()) {
    argv.push('--eleitoral-text', features.eleitoral.text.trim())
  }

  return argv
}

/** Mirror de `clipador.rebrand.cli` (engine/src/clipador/rebrand/cli.py::build_parser). */
export function buildRebrandArgv(args: RebrandJobArgs, features?: FeaturesConfig): string[] {
  const argv: string[] = [
    '-m',
    'clipador.rebrand.cli',
    args.inputDir,
    '--category',
    args.category
  ]

  if (args.kb) argv.push('--kb', args.kb)
  if (args.movement) argv.push('--movement', args.movement)
  if (args.output) argv.push('--output', args.output)
  if (args.workDir) argv.push('--work-dir', args.workDir)
  if (args.batchName) argv.push('--batch-name', args.batchName)
  if (args.outroImage) argv.push('--outro-image', args.outroImage)
  if (args.outroDuration !== undefined) argv.push('--outro-duration', String(args.outroDuration))
  if (args.disableThumbnailComposition) argv.push('--no-thumbnail-composition')
  if (args.faceModelPath) argv.push('--face-model-path', args.faceModelPath)
  if (args.limit !== undefined) argv.push('--limit', String(args.limit))
  if (args.verbose) argv.push('--verbose')

  if (features?.eleitoral.enabled && features.eleitoral.text.trim()) {
    argv.push('--eleitoral-text', features.eleitoral.text.trim())
  }

  return argv
}
