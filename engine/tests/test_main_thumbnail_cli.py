"""Testes da CLI `clipador-main-thumbnail`: parsing de argumentos e validacao de entrada,
sem rodar `generate_main_video_thumbnail` de verdade (sem ffmpeg, sem modelo de rosto, sem API)."""

from __future__ import annotations

from pathlib import Path

import pytest

from clipador.main_thumbnail_cli import build_parser, main


def test_build_parser_usa_os_defaults_certos(tmp_path):
    video_path = tmp_path / "video.mp4"
    args = build_parser().parse_args([str(video_path), "--category", "politico_pessoa"])

    assert args.input == video_path
    assert args.category == "politico_pessoa"
    assert args.kb is None
    assert args.movement is None
    assert args.output is None
    assert args.face_model_path == Path("models/blaze_face_short_range.tflite")
    assert args.verbose is False


def test_build_parser_exige_category(tmp_path):
    video_path = tmp_path / "video.mp4"
    with pytest.raises(SystemExit):
        build_parser().parse_args([str(video_path)])


def test_build_parser_aceita_flags_customizadas(tmp_path):
    video_path = tmp_path / "video.mp4"
    kb_path = tmp_path / "kb_custom"
    output_path = tmp_path / "saida"

    args = build_parser().parse_args(
        [
            str(video_path),
            "--category",
            "jogos",
            "--kb",
            str(kb_path),
            "--movement",
            "Canal Exemplo",
            "--output",
            str(output_path),
            "--verbose",
        ]
    )

    assert args.category == "jogos"
    assert args.kb == kb_path
    assert args.movement == "Canal Exemplo"
    assert args.output == output_path
    assert args.verbose is True


def test_main_retorna_erro_claro_se_video_nao_existe(tmp_path, capsys):
    video_path = tmp_path / "nao_existe.mp4"

    exit_code = main([str(video_path), "--category", "politico_pessoa"])

    assert exit_code == 1
    assert str(video_path) in capsys.readouterr().out


def test_main_repassa_argumentos_para_generate_main_video_thumbnail(tmp_path, monkeypatch, capsys):
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"video")
    calls = {}

    class FakeResult:
        thumbnail_path = tmp_path / "saida" / "thumbnail.png"
        metadata_path = tmp_path / "saida" / "metadata.txt"
        ready_to_post_path = tmp_path / "saida" / "ready-to-post.txt"

    def fake_load_kb(root, movement):
        calls["kb"] = (root, movement)
        return "kb-fake"

    def fake_generate(video, kb, output_dir, **kwargs):
        calls["generate"] = (video, kb, output_dir, kwargs)
        return FakeResult()

    monkeypatch.setattr("clipador.main_thumbnail_cli.load_knowledge_base", fake_load_kb)
    monkeypatch.setattr("clipador.main_thumbnail_cli.generate_main_video_thumbnail", fake_generate)

    exit_code = main([str(video_path), "--category", "livro_audiobook"])

    assert exit_code == 0
    assert calls["kb"] == (Path("kb") / "livro_audiobook", None)
    video, kb, output_dir, kwargs = calls["generate"]
    assert video == video_path
    assert kb == "kb-fake"
    assert output_dir == Path("output") / "video" / "video_principal"
    assert kwargs["category"] == "livro_audiobook"
    assert "thumbnail.png" in capsys.readouterr().out
