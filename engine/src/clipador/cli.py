"""Entry point da CLI do Clipador: liga a entrada (URL ou arquivo) ao pipeline ponta a ponta."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Sequence

from clipador import category as category_module
from clipador.export.watermark import WatermarkError, WatermarkImages
from clipador.export.writer import DEFAULT_SOCIAL_HANDLE
from clipador.kb.knowledge import load_knowledge_base
from clipador.pipeline import PipelineConfig, run_pipeline
from clipador.progress import print_progress
from clipador.subtitles.fonts import DEFAULT_FONTS_DIR
from clipador.subtitles.presets import DEFAULT_PRESET, PRESET_NAMES, PRESETS
from clipador.transcribe.factory import (
    BACKENDS,
    DEFAULT_BACKEND,
    DEFAULT_MODEL_SIZE,
    TranscriberSettings,
)

DEFAULT_KB_ROOT = Path("kb")
DEFAULT_OUTPUT_ROOT = Path("output")
DEFAULT_WORK_DIR = Path(".clipador")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="clipador",
        description="Gera clipes 16:9 e 9:16 a partir de um video do YouTube ou arquivo local.",
    )
    parser.add_argument("input", help="URL do YouTube ou caminho de um arquivo de video local")
    parser.add_argument(
        "--category",
        choices=category_module.CATEGORIES,
        required=True,
        help="Categoria do conteudo-fonte: muda os prompts de selecao, metadados e "
        "thumbnail (politico_pessoa, jogos ou livro_audiobook)",
    )
    parser.add_argument(
        "--kb",
        type=Path,
        default=None,
        help="Raiz da base de conhecimento (default: kb/<category>)",
    )
    parser.add_argument(
        "--movement", default=None, help="Nome do movimento/pessoa da base de conhecimento"
    )
    parser.add_argument(
        "--output", type=Path, default=DEFAULT_OUTPUT_ROOT, help="Raiz da pasta de saida"
    )
    parser.add_argument(
        "--work-dir", type=Path, default=DEFAULT_WORK_DIR, help="Pasta de artefatos intermediarios"
    )
    parser.add_argument(
        "--min-short-clips",
        type=int,
        default=5,
        help="Meta de melhor esforco de clipes curtos NOVOS a gerar (9:16)",
    )
    parser.add_argument(
        "--min-long-clips",
        type=int,
        default=5,
        help="Meta de melhor esforco de clipes longos NOVOS a gerar (16:9)",
    )
    parser.add_argument(
        "--watermark",
        choices=("on", "off"),
        required=True,
        help="Estampa (on) ou nao (off) a marca d'agua do canal por cima dos clipes "
        "gerados. Obrigatorio e sem default: e escolha editorial da rodada, nao "
        "convencao. Com 'on', --watermark-short e --watermark-long passam a ser "
        "exigidos; com 'off', nenhum dos dois pode ser passado.",
    )
    parser.add_argument(
        "--watermark-short",
        type=Path,
        default=None,
        help="PNG com transparencia da marca d'agua do formato CURTO (9:16). Deve ter o "
        "tamanho do quadro inteiro, com a marca ja posicionada dentro dele: a posicao "
        "vem do arquivo, nao de parametro",
    )
    parser.add_argument(
        "--watermark-long",
        type=Path,
        default=None,
        help="PNG com transparencia da marca d'agua do formato LONGO (16:9), mesmas regras",
    )
    parser.add_argument(
        "--eleitoral-text",
        default=None,
        help="Texto de propaganda eleitoral queimado numa tarja pequena e rotacionada na "
        "lateral de TODO clipe gerado, curto e longo. Sem a flag, nenhuma tarja e aplicada.",
    )
    parser.add_argument(
        "--handle",
        default=DEFAULT_SOCIAL_HANDLE,
        help="@ do canal escrito no ready-to-post.txt, entre a descricao e as hashtags. "
        "Passe string vazia para nao escrever mencao nenhuma",
    )
    parser.add_argument(
        "--subtitle-preset",
        choices=PRESET_NAMES,
        default=DEFAULT_PRESET,
        help="Look da legenda queimada. "
        + " | ".join(f"{name}: {preset.description}" for name, preset in PRESETS.items()),
    )
    parser.add_argument(
        "--fonts-dir",
        type=Path,
        default=DEFAULT_FONTS_DIR,
        help="Diretorio das fontes .ttf embarcadas, repassado ao libass. Sem ele o "
        "libass cai numa fonte generica EM SILENCIO quando a fonte do preset nao esta "
        "instalada na maquina",
    )
    parser.add_argument(
        "--subtitle-uppercase",
        choices=("on", "off"),
        default=None,
        help="Forca (on) ou desliga (off) a caixa alta da legenda, sobrescrevendo o "
        "preset. Sem a flag, vale o que o preset define",
    )
    parser.add_argument(
        "--subtitle-emphasis",
        action="store_true",
        default=False,
        help="Marca palavras-chave do trecho com cor propria na legenda, via LLM. Custa "
        "uma chamada a mais por clipe, alem da de metadados",
    )
    parser.add_argument(
        "--transcriber",
        choices=BACKENDS,
        default=DEFAULT_BACKEND,
        help="Backend de transcricao. whisperx alinha por CTC (timestamp por palavra na "
        "casa de ms, o que o karaoke da legenda exige) e faster-whisper e o fallback sem "
        "modelo de alinhamento, ambos locais e usando a GPU; elevenlabs (Scribe v2) e "
        "assemblyai rodam em nuvem, liberam a GPU pro encode e mandam o audio pra fora",
    )
    parser.add_argument(
        "--transcriber-model",
        default=DEFAULT_MODEL_SIZE,
        help="Tamanho do modelo Whisper (large-v3, medium, small, ...). Ignorado por "
        "--transcriber assemblyai",
    )
    parser.add_argument(
        "--transcriber-device",
        default="auto",
        help="'cuda', 'cpu' ou 'auto' (detecta CUDA)",
    )
    parser.add_argument(
        "--transcriber-compute-type",
        default="auto",
        help="'float16', 'int8', ... ou 'auto' (float16 em GPU, int8 em CPU)",
    )
    parser.add_argument(
        "--diarize",
        action="store_true",
        default=False,
        help="Liga a diarizacao (quem fala quando), que vira o cabecalho de cada segmento "
        "no prompt de selecao. No whisperx exige HUGGINGFACE_TOKEN com os termos do "
        "pyannote aceitos; no elevenlabs vem inclusa no preco, sem configuracao",
    )
    parser.add_argument(
        "--no-thumbnail-composition",
        action="store_false",
        dest="enable_thumbnail_composition",
        default=True,
        help="Salva o frame escolhido cru, sem fundo tratado, recorte, headline nem destaque",
    )
    parser.add_argument(
        "--generate-thumbnails",
        choices=("on", "off"),
        default="on",
        help="Gera (on, padrao) ou pula por completo (off) a thumbnail de CADA clipe, "
        "curto e longo. Com 'off', o formato curto tambem nao prende nenhuma capa como "
        "1o frame do video. Nao mexe em --generate-main-thumbnail (thumbnail do video "
        "principal inteiro), que e um toggle separado.",
    )
    parser.add_argument(
        "--generate-main-thumbnail",
        action="store_true",
        default=False,
        help="Alem dos cortes, gera tambem a thumbnail (+ titulo/descricao/hashtags) do "
        "VIDEO PRINCIPAL inteiro, em <output>/<pasta>/video_principal/ (desligado por "
        "padrao; roda sozinho tambem via clipador-main-thumbnail)",
    )
    parser.add_argument(
        "--face-model-path",
        type=Path,
        default=Path("models/blaze_face_short_range.tflite"),
        help="Caminho do blaze_face_short_range.tflite usado pelo MediaPipeFaceDetector "
        "(reframe do formato curto e recorte de rosto da thumbnail)",
    )
    parser.add_argument(
        "--cookies-from-browser",
        default=None,
        help="Navegador local logado ('firefox', 'chrome', 'edge', ...) pra ler cookies de "
        "sessao e evitar 403 do YouTube. 'firefox' costuma funcionar melhor no Windows.",
    )
    parser.add_argument("--verbose", action="store_true", help="Log detalhado")
    return parser


def resolve_watermark(
    parser: argparse.ArgumentParser, args: argparse.Namespace
) -> WatermarkImages | None:
    """Traduz os tres argumentos de marca d'agua no unico tipo que o pipeline consome.

    Toda a validacao acontece aqui, na fronteira da CLI: ou sai None (desligada), ou sai
    um `WatermarkImages` cujos dois arquivos ja foram conferidos. Nenhuma etapa adiante
    volta a perguntar se o caminho existe.
    """
    if args.watermark == "off":
        if args.watermark_short is not None or args.watermark_long is not None:
            parser.error("--watermark-short/--watermark-long so valem com --watermark on")
        return None
    if args.watermark_short is None or args.watermark_long is None:
        parser.error("--watermark on exige --watermark-short e --watermark-long")
    try:
        return WatermarkImages(short=args.watermark_short, long=args.watermark_long)
    except WatermarkError as exc:
        parser.error(str(exc))


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)

    watermark = resolve_watermark(parser, args)
    kb_root = args.kb if args.kb is not None else DEFAULT_KB_ROOT / args.category
    kb = load_knowledge_base(kb_root, args.movement)
    config = PipelineConfig(
        output_root=args.output,
        work_dir=args.work_dir,
        watermark=watermark,
        min_short_clips=args.min_short_clips,
        min_long_clips=args.min_long_clips,
        enable_thumbnail_composition=args.enable_thumbnail_composition,
        generate_thumbnail=args.generate_thumbnails == "on",
        cookies_from_browser=args.cookies_from_browser,
        face_model_path=args.face_model_path,
        category=args.category,
        generate_main_thumbnail=args.generate_main_thumbnail,
        eleitoral_enabled=bool(args.eleitoral_text),
        eleitoral_text=args.eleitoral_text or "",
        social_handle=args.handle,
        subtitle_preset=args.subtitle_preset,
        subtitle_fonts_dir=args.fonts_dir,
        subtitle_emphasis=args.subtitle_emphasis,
        subtitle_uppercase=None if args.subtitle_uppercase is None
        else args.subtitle_uppercase == "on",
        transcriber=TranscriberSettings(
            backend=args.transcriber,
            model_size=args.transcriber_model,
            device=args.transcriber_device,
            compute_type=args.transcriber_compute_type,
            diarize=args.diarize,
        ),
    )

    result = run_pipeline(args.input, kb, config, on_progress=print_progress)

    for clip in result.clips:
        print(f"{clip.clip_id} [{clip.format}] -> {clip.directory} ({clip.review_status})")
    for failure in result.failures:
        print(f"FALHOU {failure.clip_id} na etapa {failure.stage}: {failure.message}")

    print(f"{len(result.clips)} clipe(s) exportado(s), {len(result.failures)} falha(s).")
    return 1 if result.failures and not result.clips else 0


if __name__ == "__main__":
    raise SystemExit(main())
