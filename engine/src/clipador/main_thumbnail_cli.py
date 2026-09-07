"""Entry point da CLI `clipador-main-thumbnail`: gera so a thumbnail (+ titulo/descricao/
hashtags) do video PRINCIPAL, sem rodar selecao/geracao de cortes.

Uso tipico: o usuario ja gerou os cortes de um video (ou nem quer cortes desta vez) e
precisa de uma thumbnail pra postar o video inteiro tambem."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Sequence

from clipador import category as category_module
from clipador.kb.knowledge import load_knowledge_base
from clipador.main_thumbnail import generate_main_video_thumbnail

DEFAULT_OUTPUT_ROOT = Path("output")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="clipador-main-thumbnail",
        description=(
            "Gera a thumbnail e o pacote de titulo/descricao/hashtags do VIDEO PRINCIPAL "
            "(a gravacao/live inteira), fora do fluxo de selecao/geracao de cortes."
        ),
    )
    parser.add_argument("input", type=Path, help="Caminho de um arquivo de video local")
    parser.add_argument(
        "--category",
        choices=category_module.CATEGORIES,
        required=True,
        help="Categoria do conteudo-fonte: muda os prompts de metadados e thumbnail "
        "(politico_pessoa, jogos ou livro_audiobook)",
    )
    parser.add_argument(
        "--kb",
        type=Path,
        default=None,
        help="Raiz da base de conhecimento (default: kb/<category>)",
    )
    parser.add_argument("--movement", default=None, help="Nome do movimento/pessoa da base de conhecimento")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Pasta onde salvar thumbnail.png/metadata.txt/metadata.json/ready-to-post.txt "
        "(default: output/<nome-do-arquivo>/video_principal)",
    )
    parser.add_argument(
        "--face-model-path",
        type=Path,
        default=Path("models/blaze_face_short_range.tflite"),
        help="Caminho do blaze_face_short_range.tflite usado pelo MediaPipeFaceDetector "
        "(recorte de rosto da thumbnail)",
    )
    parser.add_argument("--verbose", action="store_true", help="Log detalhado")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)

    if not args.input.is_file():
        print(f"Video de entrada nao encontrado: {args.input}")
        return 1

    kb_root = args.kb if args.kb is not None else Path("kb") / args.category
    kb = load_knowledge_base(kb_root, args.movement)
    output_dir = args.output or (DEFAULT_OUTPUT_ROOT / args.input.stem / "video_principal")

    result = generate_main_video_thumbnail(
        args.input,
        kb,
        output_dir,
        category=args.category,
        face_model_path=args.face_model_path,
    )

    print(f"Thumbnail: {result.thumbnail_path}")
    print(f"Metadados: {result.metadata_path}")
    print(f"Pronto pra postar: {result.ready_to_post_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
