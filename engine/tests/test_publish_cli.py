import json

import pytest

import clipador.publish.cli as publish_cli
from clipador.export.review import MARKER_NAME
from clipador.publish.models import PublishResult
from clipador.select.models import LONG_FORMAT, SHORT_FORMAT


def _write_clip(tmp_path, *, format_=SHORT_FORMAT, pending=False):
    (tmp_path / "video.mp4").write_bytes(b"fake")
    (tmp_path / "metadata.json").write_text(
        json.dumps({"title": "Titulo", "description": "Descricao", "hashtags": ["politica"], "format": format_}),
        encoding="utf-8",
    )
    if pending:
        (tmp_path / MARKER_NAME).write_text("pendente", encoding="utf-8")
    return tmp_path


def test_load_clip_recusa_clipe_pendente_de_revisao(tmp_path):
    _write_clip(tmp_path, pending=True)

    with pytest.raises(SystemExit):
        publish_cli._load_clip(tmp_path)


def test_load_clip_le_metadata_e_localiza_o_video(tmp_path):
    _write_clip(tmp_path)

    clip = publish_cli._load_clip(tmp_path)

    assert clip["title"] == "Titulo"
    assert clip["_video_path"] == tmp_path / "video.mp4"


def test_run_publish_recusa_clipe_longo_em_plataforma_vertical(tmp_path, monkeypatch):
    _write_clip(tmp_path, format_=LONG_FORMAT)
    chamadas = []
    monkeypatch.setattr(
        publish_cli,
        "_publish_one",
        lambda platform, clip, group: chamadas.append(platform) or PublishResult(platform, True),
    )

    args = publish_cli.build_parser().parse_args(
        [
            "publish",
            str(tmp_path),
            "--platforms",
            "youtube,instagram,tiktok",
            "--group",
            "commit_civico",
        ]
    )
    exit_code = publish_cli._run_publish(args)

    assert exit_code == 1  # instagram/tiktok contam como falha (mensagem explicativa, nao erro real)
    assert chamadas == ["youtube"]


def test_run_publish_libera_todas_as_plataformas_pra_clipe_curto(tmp_path, monkeypatch):
    _write_clip(tmp_path, format_=SHORT_FORMAT)
    chamadas = []
    monkeypatch.setattr(
        publish_cli,
        "_publish_one",
        lambda platform, clip, group: chamadas.append(platform) or PublishResult(platform, True),
    )

    args = publish_cli.build_parser().parse_args(
        [
            "publish",
            str(tmp_path),
            "--platforms",
            "youtube,instagram,tiktok",
            "--group",
            "commit_civico",
        ]
    )
    exit_code = publish_cli._run_publish(args)

    assert exit_code == 0
    assert chamadas == ["youtube", "instagram", "tiktok"]


def test_run_publish_rejeita_plataforma_desconhecida(tmp_path):
    _write_clip(tmp_path)
    args = publish_cli.build_parser().parse_args(
        ["publish", str(tmp_path), "--platforms", "orkut", "--group", "commit_civico"]
    )

    with pytest.raises(SystemExit):
        publish_cli._run_publish(args)


def test_publish_sem_group_falha_no_argparse(tmp_path):
    with pytest.raises(SystemExit):
        publish_cli.build_parser().parse_args(["publish", str(tmp_path)])
