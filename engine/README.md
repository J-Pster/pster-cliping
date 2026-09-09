# Clipador engine

Turns a raw YouTube video (or a local video file) into vertical (9:16) and horizontal
(16:9) clips: automatic cut selection, reframing, burned-in karaoke subtitles, a
composed thumbnail, and an LLM-written title, description and hashtags, ready for
human review.

This document is for someone who wants to **run** the engine end to end. For the
internal architecture, pipeline stage names, and the binding technical decisions behind
transcription and subtitles, see `engine/CLAUDE.md` instead.

## 1. Prerequisites

- **Python >= 3.11** (see `pyproject.toml`).
- **ffmpeg** on PATH, built with **libass** support. The engine shells out to `ffmpeg`
  directly for cutting, reframing, subtitle burn-in and encoding (`clipador/subtitles/burn.py`,
  `clipador/ffmpeg_codec.py`). There is no bundled ffmpeg binary.
- **GPU (CUDA) is optional, not required by the default configuration.** The default
  transcription backend (ElevenLabs Scribe v2) and the default text LLM (Claude) both run
  in the cloud, so the engine works on a CPU-only machine out of the box. A CUDA GPU only
  matters if you opt into a local transcriber (`--transcriber whisperx` or
  `faster-whisper`, part of the `video` extra), where it is used for `torch`/Whisper
  inference; `--transcriber-device auto` detects CUDA and falls back to CPU automatically
  when none is found.
- Face detection (used for the vertical reframe and for the thumbnail's face crop) needs
  a MediaPipe model file. `engine/models/blaze_face_short_range.tflite` is already
  present in the repo, so this works out of the box with the default
  `--face-model-path models/blaze_face_short_range.tflite`.
- Subtitle fonts are bundled at `engine/assets/fonts/` (versioned in the repo, see the
  README there); no separate font install is needed. Run `python scripts/fetch_fonts.py`
  only if that directory is ever deleted and needs to be rebuilt.

All commands below assume your shell's current directory is `engine/`.

## 2. Install

Base install (download, transcription client plumbing, thumbnail composition without
AI, publish helpers unavailable):

```bash
pip install -e .
```

In practice you will want one or more of the optional extras, matching what
`pyproject.toml` declares:

| Extra | Adds | Needed for |
| --- | --- | --- |
| `video` | `faster-whisper`, `opencv-python`, `mediapipe`, `scenedetect`, `librosa`, `whisperx` | face detection/reframe (always needed), scene/silence analysis, and the **local** transcription backends (`whisperx`, `faster-whisper`) |
| `cloud-transcribe` | `assemblyai`, `elevenlabs` | the **cloud** transcription backends, including the default `elevenlabs` (Scribe v2) |
| `thumbnail-ai` | `rembg`, `google-genai` | AI-composed thumbnails (person cutout via `rembg`, background treatment/generation via Gemini "Nano Banana") |
| `publish` | `requests` | `clipador-publish` (posting approved clips to Buffer) |
| `dev` | `pytest`, `pytest-mock`, `numpy` | running the offline test suite |

Since the default configuration uses MediaPipe (face detection, always required) and
ElevenLabs (default transcriber), a realistic first install is:

```bash
pip install -e ".[video,cloud-transcribe,thumbnail-ai]"
```

Add `,publish` to that bracket if you also plan to post clips via Buffer, and `,dev` if
you plan to run the test suite.

Note: `anthropic`, `google-api-python-client`, `yt-dlp`, `python-dotenv`, `pillow` and
`pysubs2` are base dependencies, always installed.

## 3. Environment setup

Copy the example file and fill in what you need:

```bash
cp .env.example .env
```

`engine/.env.example` documents every variable inline (in Portuguese, matching the rest
of this repo's internal comments); the summary below is in English.

### Required for the default configuration

- **`ELEVENLABS_API_KEY`** - the default transcription backend is ElevenLabs Scribe v2
  (`DEFAULT_BACKEND = "elevenlabs"` in `clipador/transcribe/factory.py`), and it is a
  measured, binding decision, not a preference (see
  `.docs/decisions/2026-09-02-transcricao-elevenlabs-scribe.md`). **Without this key the
  pipeline fails loudly** (`TranscriberConfigError`) instead of silently falling back to
  a lower-quality local backend. Get it at
  [elevenlabs.io](https://elevenlabs.io) → profile menu (bottom left) → API Keys → Create
  API Key, with "Speech to Text" write access. The key is shown only once, at creation.
  To run fully offline instead, pass `--transcriber whisperx` explicitly (see section 6).
- Authentication for the text LLM (selection, rerank, title/description/hashtags).
  `CLIPADOR_TEXT_LLM_PROVIDER` defaults to `claude`, and `CLIPADOR_LLM_AUTH_MODE`
  defaults to `oauth`, which means by default you need:
  - **`CLAUDE_CODE_OAUTH_TOKEN`** - generate with `claude setup-token` (requires Claude
    Code installed and logged in). This consumes your Claude Pro/Max subscription quota
    instead of pay-per-use API credit.
  - Alternatively, set `CLIPADOR_LLM_AUTH_MODE=api_key` and provide
    **`ANTHROPIC_API_KEY`** from [console.anthropic.com](https://console.anthropic.com/)
    for direct pay-per-use billing.

### Optional

- **`GEMINI_API_KEY`** - always used to treat/generate the thumbnail background via the
  "Nano Banana" (Gemini Image) model, regardless of which text LLM you chose. **Without
  it, thumbnail generation does not fail: it falls back automatically to a local Pillow
  treatment** (darken/blur), so the pipeline still completes with a lower-effort
  thumbnail. Also required for the text LLM calls if you set
  `CLIPADOR_TEXT_LLM_PROVIDER=gemini`. Get it at
  [aistudio.google.com/apikey](https://aistudio.google.com/apikey).
- **`CLIPADOR_TEXT_LLM_PROVIDER`** (`claude` default, or `gemini`) - which provider does
  the TEXT stages (selection, rerank, title/description/hashtags). Image generation is
  always Gemini regardless of this variable.
- **`CLIPADOR_GEMINI_TEXT_MODEL`** - only used when `CLIPADOR_TEXT_LLM_PROVIDER=gemini`;
  unset uses the code default (`gemini-3.1-pro-preview` at the time of writing). Does not
  affect the thumbnail's image model, which is fixed in `thumbnail/ai_thumbnail.py`.
- **`HUGGINGFACE_TOKEN`** - only needed for **real speaker diarization** on the local
  `whisperx` backend (`--transcriber whisperx --diarize`). Requires accepting the terms
  at `huggingface.co/pyannote/speaker-diarization-3.1` and
  `huggingface.co/pyannote/segmentation-3.0` with the same account. Not needed for
  `elevenlabs`, where diarization is included in the price with no extra setup, nor for
  `assemblyai`.
- **`ASSEMBLYAI_API_KEY`** - only needed if you pass `--transcriber assemblyai`. Get it
  at [console.assemblyai.com](https://console.assemblyai.com/).
- **`BUFFER_API_KEY`** and the **`BUFFER_CHANNEL_<GROUP>_<PLATFORM>`** variables - only
  needed for `clipador-publish` (posting approved clips to YouTube/Instagram/TikTok via
  [Buffer](https://buffer.com)). Get the API key in the Buffer account's Settings > API,
  then run `clipador-publish buffer-channels` (after setting `BUFFER_API_KEY`) to list
  the channel IDs to fill in. Publishing also stages the video for Buffer to fetch via a
  local HTTP server tunneled with `ngrok` (`clipador/publish/local_tunnel.py`); this
  requires the `ngrok` binary installed and authenticated
  (`ngrok config add-authtoken <token>`, free plan is enough) but is unrelated to any
  `.env` variable.

## 4. First run

The main entry point is the `clipador` console script (`clipador.cli:main`):

```bash
python -m clipador.cli "https://www.youtube.com/watch?v=XXXXXXXXXXX" \
  --category politico_pessoa \
  --watermark off
```

or, once installed, simply `clipador <input> --category <cat> --watermark on|off`. The
positional `input` accepts either a YouTube URL or a path to a local video file
(auto-detected, see `clipador/ingest/source.py`).

### Flags you are most likely to need

- `--category` (**required**) - one of `politico_pessoa`, `jogos`, `livro_audiobook`.
  Changes the prompts used for cut selection, rerank, metadata and thumbnail. See
  section 5.
- `--watermark on|off` (**required, no default on purpose**) - whether to stamp a
  channel watermark on top of the exported clips. This is an editorial choice per run,
  not a convention, hence no default. With `on`, `--watermark-short` and
  `--watermark-long` become required (each a transparent PNG sized to the full frame,
  with the watermark already positioned inside it); with `off`, neither may be passed.
- `--kb <path>` - knowledge base root. Defaults to `kb/<category>` (see section 5).
- `--movement <name>` - name of the person/movement the knowledge base is about; used in
  prompts. Defaults to the KB folder name.
- `--output <path>` - output root (default `output/`).
- `--work-dir <path>` - intermediate artifacts folder, including the transcription cache
  (default `.clipador/`).
- `--min-short-clips <N>` / `--min-long-clips <N>` - best-effort target number of NEW
  clips to generate per format (default 5/5). Re-running with the same input tries to
  generate additional, non-overlapping clips rather than starting over.
- `--transcriber {elevenlabs,assemblyai,whisperx,faster-whisper}` (default `elevenlabs`)
  - see section 6.
- `--diarize` - turns on "who's speaking" labeling in the selection prompt. Free with
  `elevenlabs`; on `whisperx` requires `HUGGINGFACE_TOKEN` as described above.
- `--subtitle-preset {impacto,anton,neon,classico}` (default `impacto`) - burned-in
  subtitle look. Run `python -m clipador.cli --help` to see each preset's one-line
  description printed live from the code.
- `--subtitle-uppercase on|off` - override the preset's default casing.
- `--subtitle-emphasis` - has the LLM mark keyword(s) per clip with their own subtitle
  color; costs one extra LLM call per clip.
- `--fonts-dir <path>` (default `assets/fonts/`) - libass `fontsdir`. Without matching
  fonts here, libass silently falls back to a generic system font when the preset's font
  isn't installed.
- `--no-thumbnail-composition` - saves the raw chosen video frame as the thumbnail
  instead of the composed one (treated background, person cutout, headline, highlight).
- `--generate-main-thumbnail` - also generates a thumbnail (+ title/description/hashtags)
  for the ENTIRE source video, not just the clips, under
  `<output>/<folder>/video_principal/`. Off by default. Can also be run standalone via
  `clipador-main-thumbnail` (section 4.2).
- `--face-model-path <path>` (default `models/blaze_face_short_range.tflite`) - required
  for any vertical clip; there is no silent fallback if it's missing.
- `--cookies-from-browser <browser>` - reads cookies from a locally logged-in browser
  (`firefox`, `chrome`, `edge`, ...) to avoid YouTube 403s on adaptive-format downloads.
  `firefox` tends to work best on Windows.
- `--handle <text>` (default `renansantosmbl`, see `DEFAULT_SOCIAL_HANDLE` in
  `export/writer.py`) - the `@handle` written into `ready-to-post.txt`. Pass an empty
  string to omit it.
- `--verbose` - debug-level logging.

Run `python -m clipador.cli --help` for the authoritative, always-current list (it
includes a few lower-level flags for transcriber model/device/compute-type not repeated
here).

### What happens and where it lands

The pipeline downloads (or reads a local file), transcribes, has an LLM select
candidate excerpts, then per clip: cuts, reframes (vertical only), burns in subtitles,
generates metadata, builds a thumbnail, and exports. Nothing is marked publishable
automatically - every exported clip is a pending editorial review checkpoint.

Output lands under `<output-root>/<video_id>_<slugified-title>/`:

```
output/
  <video_id>_<title-slug>/
    manifest.json                  # tracks used excerpts, so a re-run adds NEW clips
    short/
      <score>_clip_<index>_short_9x16/
        video.mp4
        subtitles.ass
        thumbnail.png
        metadata.txt                # human-readable title/description/hashtags/refs
        metadata.json                # same, machine-readable, plus the full candidate
        ready-to-post.txt            # copy-paste-ready caption
        REVIEW_PENDING                # marker file; delete it (or use ReviewQueue.approve) once reviewed
    long/
      <score>_clip_<index>_long_16x9/
        ... (same layout)
    video_principal/                 # only with --generate-main-thumbnail
      thumbnail.png
      metadata.txt / metadata.json
      ready-to-post.txt
```

Folder names are prefixed with the clip's selection score so that plain alphabetical
sorting (e.g. Windows Explorer) also sorts by quality, worst first. The CLI's own stdout
prints one line per exported clip (`<clip_id> [<format>] -> <directory> (<review_status>)`)
and one line per failed clip, followed by a final `N clipe(s) exportado(s), M falha(s).`
summary; exit code is `1` only when there were failures AND zero clips made it through.

### 4.2. Standalone thumbnail for the whole video

If you already have clips and just need a thumbnail (+ metadata) for the full
recording/live, without re-running selection/cutting:

```bash
clipador-main-thumbnail path/to/local_video.mp4 --category politico_pessoa
```

Only accepts a local file path (no YouTube URL). Output defaults to
`output/<video-filename>/video_principal/`.

### 4.3. Other console scripts (not covered end to end here)

- `clipador-rebrand <input_dir> --category <cat> --outro-image <img>` - batch-rebrands a
  folder of already-existing short clips (new thumbnail/metadata via LLM, thumbnail
  pinned as first frame, static outro appended), without going through
  selection/transcription.
- `clipador-publish buffer-channels` / `clipador-publish publish <clip_dir> --group <g>`
  - posts an already-approved clip (i.e. one whose `REVIEW_PENDING` marker was removed)
  to YouTube/Instagram/TikTok through Buffer. Requires the `publish` extra and the
  Buffer/`ngrok` setup from section 3.

Run either with `--help` for their full flag list.

## 5. Categories and the knowledge base

`--category` selects which prompt variants are used across selection, rerank, metadata
and thumbnail generation (`clipador/category.py`). The three valid values, defined in
`CATEGORIES`, are:

- `politico_pessoa`
- `jogos`
- `livro_audiobook`

The category is always picked by the user per run; it is never inferred from the
video's content.

By default, `--kb` points at `kb/<category>/`. Today the repo ships:

```
kb/
  politico_pessoa/
    core/       # 00-perfil-de-voz.md, 05-livro-amarelo-visao-geral.md, 10-pautas.md,
                # 20-glossario.md, 30-temas-sensiveis.md
    topics/     # 14 topic files, e.g. 01-ajuste-fiscal.md, 07-saude.md, 13-politica-externa.md
    sources/    # livro-amarelo-resumo-2026.pdf (reference source, not read by the pipeline)
  jogos/
    core/       # 00-sobre-o-canal.md
  livro_audiobook/
    core/       # 00-sobre-o-canal.md
```

- `core/*.md` files are concatenated into a single "dossier" injected directly into
  LLM prompts (`KnowledgeBase.dossier()`).
- `topics/*.md` files are not injected wholesale; they are searched by substring on
  demand (`clipador.kb.knowledge.search_topics`) and only matching excerpts are used.
- `sources/` is not read by the code at all; it is only a place to keep the original
  reference material a `core`/`topics` file was distilled from.

To add a new category's knowledge base, create `kb/<name>/core/*.md` (at least one file
recommended, since an empty `core/` produces an empty dossier) and, optionally,
`kb/<name>/topics/*.md`. Note that `--category` itself is a fixed enum
(`politico_pessoa`, `jogos`, `livro_audiobook`) checked by `argparse` - adding a KB folder
under a new name is not enough by itself to introduce a fourth category; that also
requires adding the value to `CATEGORIES` in `clipador/category.py` and to each
`..._BY_CATEGORY` prompt dict in `select/selector.py`, `select/rerank.py`,
`metadata/generator.py`, `thumbnail/ai_thumbnail.py` and `thumbnail/background.py` (a
code change, not just content).

`--movement` overrides the "who/what this is about" name used in the dossier header and
prompts; it defaults to the KB folder's own name when omitted.

## 6. Transcription backends

`--transcriber` accepts `whisperx`, `faster-whisper`, `assemblyai`, `elevenlabs`
(`clipador/transcribe/factory.py`). Default is `elevenlabs`.

| Backend | Where it runs | Needs | Notes |
| --- | --- | --- | --- |
| `elevenlabs` (default) | Cloud | `ELEVENLABS_API_KEY` | Scribe v2; own word-level alignment; diarization included; `no_verbatim` cleanup on |
| `assemblyai` | Cloud | `ASSEMBLYAI_API_KEY` | Alternative cloud backend, own alignment |
| `whisperx` | Local (GPU recommended) | the `video` extra installed; `HUGGINGFACE_TOKEN` only if `--diarize` | Realigns Whisper output via CTC (wav2vec2) for millisecond-accurate word timestamps, which the karaoke subtitle effect needs |
| `faster-whisper` | Local (GPU recommended) | the `video` extra installed | Last resort; no alignment model, word timestamps can be off by 200-300ms |

A cloud backend without its API key fails loudly (`TranscriberConfigError`) rather than
silently degrading to a local backend, by design. Requesting `whisperx` without the
`video` extra installed logs a warning and falls back to `faster-whisper` instead
(that fallback is considered acceptable, since it's a missing optional dependency, not
an editorial choice).

`--transcriber-model` (default `large-v3`), `--transcriber-device` (`auto`/`cuda`/`cpu`)
and `--transcriber-compute-type` (`auto`/`float16`/`int8`) only apply to the local
backends and are ignored otherwise.

## 7. Smoke test script

`scripts/run_test_video.py` runs the pipeline end to end against a specific test video
the project owner already validated (hardcoded YouTube URL / local cached file path,
`whisperx` transcription with real diarization, GPU-accelerated ffmpeg encode via NVENC).
It is a fixed personal script, not a generic "test any video" tool, and expects a local
GPU setup (RTX-class, CUDA torch build) plus files at `vendor/lr_asd/` and
`work/download/` that are specific to that environment. Run it from `engine/`:

```bash
python scripts/run_test_video.py
```

It reads a few env vars not present in `.env.example` to tweak a run without editing the
script: `CLIPADOR_TRANSCRIBER`, `CLIPADOR_OUTPUT_DIR`, `CLIPADOR_MIN_SHORT_CLIPS`,
`CLIPADOR_MIN_LONG_CLIPS`, `CLIPADOR_SUBTITLE_PRESET`, `CLIPADOR_SUBTITLE_EMPHASIS`.

For your own video, use `python -m clipador.cli` (section 4) instead.

## 8. Offline test suite

```bash
pip install -e ".[dev]"
python -m pytest tests/ -q
```

No test in `tests/` calls the network or a real ffmpeg/GPU; every heavy component
(downloader, transcriber, ffmpeg calls, LLM clients, face detectors) is injectable and
mocked in tests. This means the suite runs on any machine with just the `dev` extra
installed, with no API keys, ffmpeg or GPU required.

## 9. Troubleshooting

- **`TranscriberConfigError: ELEVENLABS_API_KEY nao esta definida...`** - expected,
  by design, when using the default transcriber without the key set. Either add
  `ELEVENLABS_API_KEY` to `.env`, or pass `--transcriber whisperx` (or
  `faster-whisper`/`assemblyai`) to use a different backend explicitly.
- **`RuntimeError: CLAUDE_CODE_OAUTH_TOKEN nao esta definida...`** - default LLM auth
  mode is `oauth`. Either run `claude setup-token` and put the token in `.env`, or set
  `CLIPADOR_LLM_AUTH_MODE=api_key` and provide `ANTHROPIC_API_KEY` instead.
- **Thumbnail looks like a plain darkened/blurred frame instead of a composed image**:
  expected fallback when `GEMINI_API_KEY` is missing, or when `rembg`/`google-genai`
  (the `thumbnail-ai` extra) aren't installed. This is a deliberate, non-fatal
  degradation, not a bug: check the logs for a warning from `thumbnail/composer.py`
  naming which piece fell back.
- **ffmpeg errors mentioning the `ass=` filter, or subtitles rendering in a generic
  font** - make sure `ffmpeg` is on PATH and was built with libass, and that
  `--fonts-dir` points at a directory containing the `.ttf` the chosen `--subtitle-preset`
  needs (default `assets/fonts/`, rebuildable with `python scripts/fetch_fonts.py`).
  libass does not error when a style's font is missing from `fontsdir`/fontconfig; it
  silently substitutes a generic font, so a wrong result here produces no error message
  at all.
- **`ReframeError` about `MediaPipeFaceDetector` / a missing `.tflite`** - every vertical
  clip needs `--face-model-path` pointing at a real
  `blaze_face_short_range.tflite` file; there is no fallback. The file is already present
  at `engine/models/blaze_face_short_range.tflite` by default.
- **Real speaker diarization not happening on `whisperx`** - `--diarize` on `whisperx`
  needs `HUGGINGFACE_TOKEN`, and that token's account must have accepted the terms on
  both `huggingface.co/pyannote/speaker-diarization-3.1` and
  `huggingface.co/pyannote/segmentation-3.0`. Not needed on `elevenlabs`.
- **YouTube download returns HTTP 403** - pass `--cookies-from-browser firefox` (or
  another logged-in browser) so `yt-dlp` authenticates the adaptive-format download.
- **A re-run with the same input doesn't seem to reuse the transcription** - the
  transcription cache is keyed by `video_id` under `--work-dir` (default `.clipador/`);
  passing a different `--work-dir` (or deleting it) forces re-transcription.
