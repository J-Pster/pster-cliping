"""Testes da CLI `clipador-rebrand`: parsing de argumentos e validacao de entrada,
sem rodar `rebrand_batch` de verdade (sem ffmpeg, sem modelo de rosto, sem API)."""

from __future__ import annotations

from pathlib import Path

from clipador.rebrand.cli import build_parser, main


def test_build_parser_usa_os_defaults_certos(tmp_path):
    input_dir = tmp_path / "entrada"
    args = build_parser().parse_args([str(input_dir), "--category", "politico_pessoa"])

    assert args.input_dir == input_dir
    assert args.category == "politico_pessoa"
    assert args.kb is None
    assert args.movement is None
    assert args.output == Path("output")
    assert args.work_dir == Path(".clipador")
    assert args.batch_name is None
    assert args.outro_image is None
    assert args.outro_duration == 5.0
    assert args.enable_thumbnail_composition is True
    assert args.face_model_path == Path("models/blaze_face_short_range.tflite")
    assert args.limit is None
    assert args.verbose is False


def test_build_parser_exige_category(tmp_path):
    import pytest

    input_dir = tmp_path / "entrada"
    with pytest.raises(SystemExit):
        build_parser().parse_args([str(input_dir)])


def test_build_parser_aceita_flags_customizadas(tmp_path):
    input_dir = tmp_path / "entrada"
    kb_path = tmp_path / "kb_custom"
    output_path = tmp_path / "saida"
    work_dir = tmp_path / "work_custom"
    outro_path = tmp_path / "outro.jpg"

    args = build_parser().parse_args(
        [
            str(input_dir),
            "--category",
            "politico_pessoa",
            "--kb",
            str(kb_path),
            "--movement",
            "Movimento Exemplo",
            "--output",
            str(output_path),
            "--work-dir",
            str(work_dir),
            "--batch-name",
            "lote_1",
            "--outro-image",
            str(outro_path),
            "--outro-duration",
            "3.5",
            "--no-thumbnail-composition",
            "--limit",
            "1",
            "--verbose",
        ]
    )

    assert args.input_dir == input_dir
    assert args.category == "politico_pessoa"
    assert args.kb == kb_path
    assert args.movement == "Movimento Exemplo"
    assert args.output == output_path
    assert args.work_dir == work_dir
    assert args.batch_name == "lote_1"
    assert args.outro_image == outro_path
    assert args.outro_duration == 3.5
    assert args.enable_thumbnail_composition is False
    assert args.limit == 1
    assert args.verbose is True


def test_main_retorna_erro_claro_se_pasta_de_entrada_nao_existe(tmp_path, capsys):
    input_dir = tmp_path / "nao_existe"

    exit_code = main([str(input_dir), "--category", "politico_pessoa"])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert str(input_dir) in captured.out


def test_main_retorna_erro_se_input_dir_e_arquivo_em_vez_de_pasta(tmp_path, capsys):
    input_path = tmp_path / "arquivo.mp4"
    input_path.write_bytes(b"nao e uma pasta")

    exit_code = main([str(input_path), "--category", "politico_pessoa"])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert str(input_path) in captured.out


def test_main_exige_outro_image_explicito_fora_da_categoria_politico_pessoa(tmp_path, capsys):
    input_dir = tmp_path / "entrada"
    input_dir.mkdir()

    exit_code = main([str(input_dir), "--category", "jogos"])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "--outro-image" in captured.out
