"""Entry point da CLI de rebrand em lote: liga uma pasta de videos curtos ja existentes
ao `rebrand_batch`."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Sequence

from clipador import category as category_module
from clipador.kb.knowledge import load_knowledge_base
from clipador.rebrand.service import DEFAULT_OUTRO_IMAGE, rebrand_batch


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="clipador-rebrand",
        description=(
            "Rebranding em lote de videos curtos ja existentes (fora do pipeline principal): "
            "gera thumbnail+titulo/descricao/hashtags via LLM, prende a thumbnail como 1o frame e "
            "adiciona um outro estatico no final. Cada video da pasta de entrada vira um clipe dentro "
            "de UMA pasta em output/, na mesma estrutura do pipeline principal."
        ),
    )
    parser.add_argument("input_dir", type=Path, help="Pasta contendo os videos curtos a re-brandear")
    parser.add_argument(
        "--category",
        choices=category_module.CATEGORIES,
        required=True,
        help="Categoria do conteudo-fonte: muda os prompts de metadados e thumbnail "
        "(politico_pessoa, jogos ou livro_audiobook)",
    )
    parser.add_argument(
        "--kb", type=Path, default=None, help="Raiz da base de conhecimento (default: kb/<category>)"
    )
    parser.add_argument("--movement", default=None, help="Nome do movimento/pessoa da base de conhecimento")
    parser.add_argument("--output", type=Path, default=Path("output"), help="Raiz da pasta de saida")
    parser.add_argument(
        "--work-dir", type=Path, default=Path(".clipador"), help="Pasta de artefatos intermediarios"
    )
    parser.add_argument(
        "--batch-name",
        default=None,
        help="Nome da pasta de saida do lote (default: rebrand_<nome-da-pasta-de-entrada>)",
    )
    parser.add_argument(
        "--outro-image",
        type=Path,
        default=None,
        help="Imagem estatica usada como outro/encerramento no final de cada video "
        "(default: a imagem padrao do canal so pra --category politico_pessoa; "
        "as demais categorias exigem este argumento explicito)",
    )
    parser.add_argument(
        "--outro-duration",
        type=float,
        default=5.0,
        help="Duracao em segundos do outro/encerramento",
    )
    parser.add_argument(
        "--no-thumbnail-composition",
        action="store_false",
        dest="enable_thumbnail_composition",
        default=True,
        help="Salva o frame escolhido cru, sem fundo tratado, recorte, headline nem destaque",
    )
    parser.add_argument(
        "--face-model-path",
        type=Path,
        default=Path("models/blaze_face_short_range.tflite"),
        help="Caminho do blaze_face_short_range.tflite usado pelo MediaPipeFaceDetector",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help=(
            "Processa so os N primeiros videos (ordem alfabetica) - util pra testar com 1 "
            "antes do lote inteiro"
        ),
    )
    parser.add_argument("--verbose", action="store_true", help="Log detalhado")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)

    if not args.input_dir.is_dir():
        print(f"Pasta de entrada nao encontrada: {args.input_dir}")
        return 1

    outro_image = args.outro_image
    if outro_image is None:
        if args.category != category_module.POLITICS_PERSON:
            print(
                f"--category {args.category} exige --outro-image explicito: nao ha "
                "imagem de outro padrao pra esta categoria."
            )
            return 1
        outro_image = DEFAULT_OUTRO_IMAGE

    kb_root = args.kb if args.kb is not None else Path("kb") / args.category
    kb = load_knowledge_base(kb_root, args.movement)
    result = rebrand_batch(
        args.input_dir,
        kb,
        output_root=args.output,
        work_dir=args.work_dir,
        batch_name=args.batch_name,
        outro_image=outro_image,
        outro_duration_seconds=args.outro_duration,
        enable_thumbnail_composition=args.enable_thumbnail_composition,
        face_model_path=args.face_model_path,
        limit=args.limit,
        category=args.category,
    )

    for clip in result.clips:
        print(f"{clip.clip_id} [{clip.format}] -> {clip.directory} ({clip.review_status})")
    for failure in result.failures:
        print(f"FALHOU {failure.clip_id} na etapa {failure.stage}: {failure.message}")
    print(f"{len(result.clips)} clipe(s) exportado(s), {len(result.failures)} falha(s).")

    return 1 if result.failures and not result.clips else 0


if __name__ == "__main__":
    raise SystemExit(main())
