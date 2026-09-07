"""Roda o pipeline de ponta a ponta contra o video de teste combinado com o usuario.

Diferente de `python -m clipador.cli` (que usa so os componentes default), este script
liga explicitamente o que foi configurado nesta sessao: WhisperX (alinhamento CTC +
diarizacao real, se houver HUGGINGFACE_TOKEN) e o LR-ASD vendorizado como active speaker
detector. Ver o aviso de log no arranque sobre o LR-ASD: o `VerticalReframer` ainda nao
constroi um `SpeakerContext` de audio real por amostra (pendencia conhecida, documentada
no ledger), entao na pratica ele ainda cai na heuristica de maior rosto durante este run -
o modelo esta carregado e pronto, so falta essa fiacao fina.
"""

from __future__ import annotations

import functools
import logging
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env", override=True)  # .env do projeto sempre vence env var solta do sistema

from clipador.download.downloader import YtDlpDownloader  # noqa: E402
from clipador.export.cutter import ClipCutter  # noqa: E402
from clipador.export.watermark import WatermarkImages  # noqa: E402
from clipador.kb.knowledge import load_knowledge_base  # noqa: E402
from clipador.pipeline import PipelineConfig, run_pipeline  # noqa: E402
from clipador.reframe.faces import MediaPipeFaceDetector  # noqa: E402
from clipador.reframe.reframer import VerticalReframer  # noqa: E402
from clipador.reframe.speaker import LRASDActiveSpeakerDetector  # noqa: E402
from clipador.subtitles.burn import burn_in  # noqa: E402
from clipador.subtitles.presets import DEFAULT_PRESET  # noqa: E402
from clipador.thumbnail.ai_thumbnail import AIThumbnailGenerator  # noqa: E402
from clipador.thumbnail.background import GeminiBackgroundEditor  # noqa: E402
from clipador.thumbnail.builder import ThumbnailBuilder  # noqa: E402
from clipador.thumbnail.composer import ThumbnailComposer  # noqa: E402
from clipador.thumbnail.cutout import PersonCutout  # noqa: E402
from clipador.thumbnail.face_quality import FaceQualityScorer  # noqa: E402
from clipador.transcribe.factory import (  # noqa: E402
    CLOUD_BACKENDS,
    DEFAULT_BACKEND,
    TranscriberSettings,
    build_transcriber,
)
from clipador.transcribe.vocabulary import build_vocabulary  # noqa: E402

# GPU disponivel na maquina (RTX 4070 SUPER): decode NVDEC + encode NVENC em vez de
# libx264/software puro. A fonte original e AV1 (av1_cuvid); os estagios seguintes
# (reframe/burn-in) ja leem H264 gerado pelo estagio anterior (h264_cuvid).
VIDEO_CODEC = "h264_nvenc"
SOURCE_DECODER = "av1_cuvid"
H264_DECODER = "h264_cuvid"

FACE_MODEL_PATH = Path(__file__).resolve().parent.parent / "models" / "blaze_face_short_range.tflite"

# Marca d'agua do canal, um PNG do tamanho do quadro por formato. Trocar por `None` no
# `PipelineConfig` abaixo desliga - `PipelineConfig.watermark` nao tem default, a escolha
# e sempre explicita.
WATERMARK_DIR = Path(__file__).resolve().parent.parent / "assets" / "watermark"

# Ja baixado numa tentativa anterior (work/download/) - usar o arquivo local pula o
# download de novo e valida o caminho preferencial do plano (ingest por arquivo local).
VIDEO_URL = "https://www.youtube.com/live/T3ENScVymJQ"
LOCAL_VIDEO_PATH = Path(__file__).resolve().parent.parent / "work" / "download" / "T3ENScVymJQ.mp4"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("run_test_video")


def main() -> int:
    started = time.monotonic()
    hf_token = os.environ.get("HUGGINGFACE_TOKEN")

    kb = load_knowledge_base(ROOT / "kb")
    logger.info("KB carregada (dossie de %d doc(s) core)", len(kb.core))

    # A instalacao original puxou o torch CPU-only (pip escolhe isso por padrao sem
    # --index-url); reinstalado como torch==2.8.0+cu126 pra usar a RTX 4070 SUPER da
    # maquina. Em CUDA o throughput permite o large-v3: em PT-BR a diferenca dele pro
    # "medium" aparece exatamente onde a legenda mostra - nome proprio, sigla e
    # concordancia. O vocabulario sai do dossie da KB e vira initial_prompt/hotwords.
    # Default do projeto: ElevenLabs Scribe v2 (ver clipador.transcribe.factory e
    # .docs/decisions/2026-09-02-transcricao-elevenlabs-scribe.md). CLIPADOR_TRANSCRIBER
    # permite rodar o mesmo video num backend local pra comparar sem editar o script.
    backend = os.environ.get("CLIPADOR_TRANSCRIBER", DEFAULT_BACKEND)
    transcriber = build_transcriber(
        TranscriberSettings(
            backend=backend,
            model_size="large-v3",
            device="cuda",
            compute_type="float16",
            language="pt",
            # Na ElevenLabs a diarizacao vem inclusa no preco; no WhisperX ela exige
            # token do HuggingFace com os termos do pyannote aceitos.
            diarize=backend in CLOUD_BACKENDS or bool(hf_token),
            hf_token=hf_token,
        ),
        vocabulary=build_vocabulary(kb),
    )

    face_detector = MediaPipeFaceDetector(model_path=FACE_MODEL_PATH)
    speaker_detector = LRASDActiveSpeakerDetector(model_dir=ROOT / "vendor" / "lr_asd")
    reframer = VerticalReframer(
        face_detector=face_detector,
        speaker_detector=speaker_detector,
        video_codec=VIDEO_CODEC,
        input_decoder=H264_DECODER,
    )
    logger.info("LR-ASD available=%s (ver docstring: SpeakerContext ainda nao alimentado)", speaker_detector.available)
    logger.info("Encode: %s (decode fonte=%s, decode intermediario=%s)", VIDEO_CODEC, SOURCE_DECODER, H264_DECODER)

    cutout = PersonCutout()
    background_editor = GeminiBackgroundEditor()
    ai_generator = AIThumbnailGenerator()
    thumbnail_builder = ThumbnailBuilder(
        face_scorer=FaceQualityScorer(face_detector=MediaPipeFaceDetector(model_path=FACE_MODEL_PATH)),
        composer=ThumbnailComposer(
            cutout=cutout,
            background_editor=background_editor,
            face_detector=MediaPipeFaceDetector(model_path=FACE_MODEL_PATH),
            ai_generator=ai_generator,
        ),
    )
    logger.info(
        "Thumbnail composer: geracao completa via IA available=%s (fallback: rembg "
        "available=%s, Gemini bg available=%s - cada peca indisponivel cai no fallback "
        "seguinte, a composicao nunca quebra o clipe)",
        ai_generator.available,
        cutout.available,
        background_editor.available,
    )

    cutter = ClipCutter(video_codec=VIDEO_CODEC, input_decoder=SOURCE_DECODER)
    burner = functools.partial(burn_in, video_codec=VIDEO_CODEC, input_decoder=H264_DECODER)

    # CLIPADOR_OUTPUT_DIR: permite rodar de novo sem sobrescrever um output anterior que
    # ainda esta sendo revisado (ex.: comparar ajustes de duracao/legenda lado a lado).
    # CLIPADOR_MIN_SHORT_CLIPS/CLIPADOR_MIN_LONG_CLIPS: meta de clipes NOVOS desta rodada
    # ("gerar mais X curtos" sem mexer nos longos, por exemplo) - default 5/5.
    output_dir_name = os.environ.get("CLIPADOR_OUTPUT_DIR", "output")
    min_short_clips = int(os.environ.get("CLIPADOR_MIN_SHORT_CLIPS", "5"))
    min_long_clips = int(os.environ.get("CLIPADOR_MIN_LONG_CLIPS", "5"))
    config = PipelineConfig(
        output_root=ROOT / output_dir_name,
        work_dir=ROOT / "work",
        min_short_clips=min_short_clips,
        min_long_clips=min_long_clips,
        watermark=WatermarkImages(
            short=WATERMARK_DIR / "commit_civico_short_1080x1920.png",
            long=WATERMARK_DIR / "commit_civico_long_1920x1080.png",
        ),
        # CLIPADOR_SUBTITLE_PRESET: troca o look da legenda sem editar o script
        # (impacto | anton | neon | classico - ver clipador.subtitles.presets).
        subtitle_preset=os.environ.get("CLIPADOR_SUBTITLE_PRESET", DEFAULT_PRESET),
        subtitle_fonts_dir=ROOT / "assets" / "fonts",
        subtitle_emphasis=os.environ.get("CLIPADOR_SUBTITLE_EMPHASIS", "0") == "1",
    )
    logger.info(
        "Output: %s | meta: %d curto(s), %d longo(s)",
        config.output_root,
        min_short_clips,
        min_long_clips,
    )

    if LOCAL_VIDEO_PATH.is_file():
        input_source: str | Path = LOCAL_VIDEO_PATH
        logger.info("Ingest: arquivo local ja baixado em %s (pula download)", LOCAL_VIDEO_PATH)
        downloader = None
    else:
        # YouTube bloqueia (403) formato adaptativo sem sessao autenticada - risco ja
        # documentado no plano. Cookies do Firefox local resolvem sem passo manual.
        input_source = VIDEO_URL
        downloader = YtDlpDownloader(config.work_dir / "download", cookies_from_browser="firefox")
        logger.info("Downloader: yt-dlp com cookies do Firefox local")

    result = run_pipeline(
        input_source,
        kb,
        config,
        downloader=downloader,
        transcriber=transcriber,
        cutter=cutter,
        reframer=reframer,
        burner=burner,
        thumbnail_builder=thumbnail_builder,
    )

    elapsed = time.monotonic() - started
    print()
    print(f"== Pipeline concluido em {elapsed / 60:.1f} min ==")
    print(f"video_id={result.video_id} candidatos={len(result.candidates)}")
    for clip in result.clips:
        print(f"  OK {clip.clip_id} [{clip.format}] -> {clip.directory} ({clip.review_status})")
    for failure in result.failures:
        print(f"  FALHOU {failure.clip_id} na etapa {failure.stage}: {failure.message}")
    print(f"{len(result.clips)} clipe(s) exportado(s), {len(result.failures)} falha(s).")
    return 1 if result.failures and not result.clips else 0


if __name__ == "__main__":
    raise SystemExit(main())
