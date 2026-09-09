from pathlib import Path

import pytest

import clipador.cli as cli
from clipador.export.models import REVIEW_PENDING, ClipOutput
from clipador.export.watermark import WatermarkImages
from clipador.pipeline import ClipFailure, PipelineConfig, PipelineResult
from clipador.select.models import SHORT_FORMAT


def test_parser_usa_defaults_de_kb_saida_e_trabalho():
    args = cli.build_parser().parse_args(
        [
            "https://www.youtube.com/live/T3ENScVymJQ",
            "--category",
            "politico_pessoa",
            "--watermark",
            "off",
        ]
    )

    assert args.input == "https://www.youtube.com/live/T3ENScVymJQ"
    assert args.category == "politico_pessoa"
    assert args.kb is None
    assert args.output == cli.DEFAULT_OUTPUT_ROOT
    assert args.work_dir == cli.DEFAULT_WORK_DIR
    assert args.min_short_clips == 5
    assert args.min_long_clips == 5
    assert args.generate_main_thumbnail is False
    assert args.verbose is False


def test_parser_exige_category():
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["video.mp4", "--watermark", "off"])


def test_parser_exige_escolha_explicita_de_marca_dagua():
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["video.mp4", "--category", "politico_pessoa"])


def test_parser_aceita_overrides():
    args = cli.build_parser().parse_args(
        [
            "video.mp4",
            "--category",
            "jogos",
            "--kb",
            "outra-kb",
            "--movement",
            "Movimento Exemplo",
            "--output",
            "saida",
            "--work-dir",
            "tmp",
            "--min-short-clips",
            "3",
            "--min-long-clips",
            "2",
            "--watermark",
            "off",
            "--verbose",
        ]
    )

    assert args.category == "jogos"
    assert args.kb == Path("outra-kb")
    assert args.movement == "Movimento Exemplo"
    assert args.output == Path("saida")
    assert args.work_dir == Path("tmp")
    assert args.min_short_clips == 3
    assert args.min_long_clips == 2
    assert args.verbose is True


def test_parser_exige_entrada():
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args([])


def build_result(tmp_path, clips=(), failures=()):
    return PipelineResult(
        source=None,
        video_path=tmp_path / "video.mp4",
        video_id="vid",
        transcription=None,
        candidates=[],
        clips=list(clips),
        failures=list(failures),
    )


def test_main_repassa_os_argumentos_para_o_pipeline(tmp_path, monkeypatch, capsys):
    calls = {}

    def fake_load_kb(root, movement):
        calls["kb"] = (root, movement)
        return "kb-fake"

    def fake_run_pipeline(input_source, kb, config, **_kwargs):
        calls["pipeline"] = (input_source, kb, config)
        clip = ClipOutput(
            clip_id="clip_00",
            video_id="vid",
            format=SHORT_FORMAT,
            directory=tmp_path / "saida" / "vid" / "clip_00",
            video_path=tmp_path / "saida" / "vid" / "clip_00" / "video.mp4",
        )
        return build_result(tmp_path, clips=[clip])

    monkeypatch.setattr(cli, "load_knowledge_base", fake_load_kb)
    monkeypatch.setattr(cli, "run_pipeline", fake_run_pipeline)

    exit_code = cli.main(
        [
            "video.mp4",
            "--category",
            "politico_pessoa",
            "--kb",
            "kb-x",
            "--output",
            "saida",
            "--min-short-clips",
            "2",
            "--min-long-clips",
            "1",
            "--watermark",
            "off",
        ]
    )

    assert exit_code == 0
    assert calls["kb"] == (Path("kb-x"), None)
    input_source, kb, config = calls["pipeline"]
    assert input_source == "video.mp4"
    assert kb == "kb-fake"
    assert isinstance(config, PipelineConfig)
    assert config.output_root == Path("saida")
    assert config.min_short_clips == 2
    assert config.min_long_clips == 1
    assert config.generate_main_thumbnail is False
    assert config.generate_thumbnail is True
    assert REVIEW_PENDING in capsys.readouterr().out


def test_main_repassa_generate_main_thumbnail_quando_a_flag_e_passada(tmp_path, monkeypatch):
    calls = {}

    monkeypatch.setattr(cli, "load_knowledge_base", lambda root, movement: "kb-fake")

    def fake_run_pipeline(input_source, kb, config, **_kwargs):
        calls["config"] = config
        return build_result(tmp_path)

    monkeypatch.setattr(cli, "run_pipeline", fake_run_pipeline)

    cli.main(
        ["video.mp4", "--category", "politico_pessoa", "--watermark", "off", "--generate-main-thumbnail"]
    )

    assert calls["config"].generate_main_thumbnail is True


def test_main_repassa_generate_thumbnails_off(tmp_path, monkeypatch):
    calls = {}

    monkeypatch.setattr(cli, "load_knowledge_base", lambda root, movement: "kb-fake")

    def fake_run_pipeline(input_source, kb, config, **_kwargs):
        calls["config"] = config
        return build_result(tmp_path)

    monkeypatch.setattr(cli, "run_pipeline", fake_run_pipeline)

    cli.main(
        ["video.mp4", "--category", "politico_pessoa", "--watermark", "off", "--generate-thumbnails", "off"]
    )

    assert calls["config"].generate_thumbnail is False


def test_main_retorna_erro_quando_nenhum_clipe_saiu(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "load_knowledge_base", lambda root, movement: "kb-fake")
    monkeypatch.setattr(
        cli,
        "run_pipeline",
        lambda *args, **kwargs: build_result(
            tmp_path, failures=[ClipFailure("clip_00", "thumbnail", "sem frame")]
        ),
    )

    assert cli.main(["video.mp4", "--category", "politico_pessoa", "--watermark", "off"]) == 1
    assert "FALHOU clip_00 na etapa thumbnail" in capsys.readouterr().out


# --- marca d'agua ------------------------------------------------------------


def watermark_pngs(tmp_path):
    short = tmp_path / "wm_short.png"
    long = tmp_path / "wm_long.png"
    short.write_bytes(b"png curto")
    long.write_bytes(b"png longo")
    return short, long


def resolve_watermark(*extra_argv):
    parser = cli.build_parser()
    argv = ["video.mp4", "--category", "politico_pessoa", *extra_argv]
    return cli.resolve_watermark(parser, parser.parse_args(argv))


def test_watermark_off_resulta_em_nenhuma_marca():
    assert resolve_watermark("--watermark", "off") is None


def test_watermark_on_monta_o_par_de_caminhos(tmp_path):
    short, long = watermark_pngs(tmp_path)

    images = resolve_watermark(
        "--watermark", "on", "--watermark-short", str(short), "--watermark-long", str(long)
    )

    assert images == WatermarkImages(short=short, long=long)


def test_watermark_on_sem_os_caminhos_aborta():
    with pytest.raises(SystemExit):
        resolve_watermark("--watermark", "on")


def test_watermark_on_com_so_um_dos_caminhos_aborta(tmp_path):
    short, _ = watermark_pngs(tmp_path)

    with pytest.raises(SystemExit):
        resolve_watermark("--watermark", "on", "--watermark-short", str(short))


def test_watermark_off_com_caminhos_aborta(tmp_path):
    short, long = watermark_pngs(tmp_path)

    with pytest.raises(SystemExit):
        resolve_watermark(
            "--watermark", "off", "--watermark-short", str(short), "--watermark-long", str(long)
        )


def test_watermark_on_com_arquivo_inexistente_aborta(tmp_path):
    short, _ = watermark_pngs(tmp_path)

    with pytest.raises(SystemExit):
        resolve_watermark(
            "--watermark",
            "on",
            "--watermark-short",
            str(short),
            "--watermark-long",
            str(tmp_path / "nao_existe.png"),
        )


def test_main_repassa_a_marca_dagua_para_o_pipeline(tmp_path, monkeypatch):
    short, long = watermark_pngs(tmp_path)
    calls = {}

    monkeypatch.setattr(cli, "load_knowledge_base", lambda root, movement: "kb-fake")

    def fake_run_pipeline(input_source, kb, config, **_kwargs):
        calls["config"] = config
        return build_result(tmp_path)

    monkeypatch.setattr(cli, "run_pipeline", fake_run_pipeline)

    cli.main(
        [
            "video.mp4",
            "--category",
            "politico_pessoa",
            "--watermark",
            "on",
            "--watermark-short",
            str(short),
            "--watermark-long",
            str(long),
        ]
    )

    assert calls["config"].watermark == WatermarkImages(short=short, long=long)
