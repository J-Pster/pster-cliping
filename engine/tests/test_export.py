import json

import pytest

from clipador.export.cutter import ClipCutter
from clipador.export.models import REVIEW_APPROVED, REVIEW_PENDING, ClipOutput, ExportError
from clipador.export.review import MARKER_NAME, ReviewQueue
from clipador.export.writer import ExportWriter, render_metadata_text, render_ready_to_post_text
from clipador.metadata.models import ClipMetadata
from clipador.select.models import LONG_FORMAT, SHORT_FORMAT, ClipCandidate


def build_metadata(**overrides) -> ClipMetadata:
    payload = dict(
        title="Renan Santos sobre transparencia fiscal",
        description="Trecho em que ele defende a pauta de transparencia fiscal.",
        hashtags=["transparencia", "shorts"],
        format=SHORT_FORMAT,
        kb_references=["Pauta: transparencia fiscal"],
    )
    payload.update(overrides)
    return ClipMetadata(**payload)


def build_candidate(**overrides) -> ClipCandidate:
    payload = dict(
        start_word_id=0,
        end_word_id=5,
        format=SHORT_FORMAT,
        score=88,
        justificativa="Gancho forte.",
        start=1.0,
        end=40.0,
    )
    payload.update(overrides)
    return ClipCandidate(**payload)


def make_artifacts(tmp_path):
    video = tmp_path / "burned.mp4"
    video.write_bytes(b"fake video")
    ass = tmp_path / "subtitles.ass"
    ass.write_text("[Script Info]", encoding="utf-8")
    thumb = tmp_path / "thumbnail.png"
    thumb.write_bytes(b"fake png")
    return video, ass, thumb


def test_writer_organiza_pasta_por_clipe(tmp_path):
    video, ass, thumb = make_artifacts(tmp_path)
    writer = ExportWriter(tmp_path / "output")

    output = writer.write(
        video_id="T3ENScVymJQ",
        clip_id="clip_00_short_9x16",
        clip_format=SHORT_FORMAT,
        video_path=video,
        metadata=build_metadata(),
        subtitles_path=ass,
        thumbnail_path=thumb,
        candidate=build_candidate(),
    )

    assert output.directory == tmp_path / "output" / "T3ENScVymJQ" / "short" / "clip_00_short_9x16"
    assert output.video_path.name == "video.mp4"
    assert output.subtitles_path.name == "subtitles.ass"
    assert output.thumbnail_path.name == "thumbnail.png"
    assert output.metadata_path.name == "metadata.txt"
    assert output.video_path.read_bytes() == b"fake video"
    assert (output.directory / "metadata.json").is_file()


def test_writer_preserva_kb_references_no_texto_e_no_json(tmp_path):
    video, ass, thumb = make_artifacts(tmp_path)
    writer = ExportWriter(tmp_path / "output")
    metadata = build_metadata(kb_references=["Glossario: Partido Missao", "Pauta: seguranca"])

    output = writer.write(
        video_id="vid",
        clip_id="clip_00",
        clip_format=SHORT_FORMAT,
        video_path=video,
        metadata=metadata,
        subtitles_path=ass,
        thumbnail_path=thumb,
    )

    text = output.metadata_path.read_text(encoding="utf-8")
    assert "Glossario: Partido Missao" in text
    assert "Pauta: seguranca" in text
    assert "#transparencia" in text

    payload = json.loads((output.directory / "metadata.json").read_text(encoding="utf-8"))
    assert payload["metadata"]["kb_references"] == metadata.kb_references
    assert output.kb_references == metadata.kb_references


def test_writer_aceita_clipe_sem_thumbnail_nem_metadados(tmp_path):
    video, ass, _ = make_artifacts(tmp_path)
    writer = ExportWriter(tmp_path / "output")

    output = writer.write(
        video_id="vid",
        clip_id="clip_01",
        clip_format=SHORT_FORMAT,
        video_path=video,
        subtitles_path=ass,
    )

    assert output.thumbnail_path is None
    assert output.metadata_path is None
    assert output.metadata is None


def test_writer_gera_ready_to_post_para_clipe_curto(tmp_path):
    video, ass, thumb = make_artifacts(tmp_path)
    writer = ExportWriter(tmp_path / "output")
    metadata = build_metadata(
        title="Flavio Bolsonaro, aceita o debate ou nao?",
        description="Desafio direto: convido o Flavio Bolsonaro pra um debate cara a cara.",
        hashtags=["politica", "FlavioBolsonaro"],
    )

    output = writer.write(
        video_id="vid",
        clip_id="clip_00",
        clip_format=SHORT_FORMAT,
        video_path=video,
        metadata=metadata,
        subtitles_path=ass,
        thumbnail_path=thumb,
    )

    ready_to_post_path = output.directory / "ready-to-post.txt"
    assert ready_to_post_path.is_file()
    assert ready_to_post_path.read_text(encoding="utf-8") == (
        "Flavio Bolsonaro, aceita o debate ou nao?\n\n"
        "Desafio direto: convido o Flavio Bolsonaro pra um debate cara a cara.\n\n"
        "@renansantosmbl\n\n"
        "#politica #FlavioBolsonaro\n"
    )
    assert output.extra["ready_to_post_path"] == str(ready_to_post_path)


def test_writer_gera_ready_to_post_para_clipe_longo_tambem(tmp_path):
    video, ass, thumb = make_artifacts(tmp_path)
    writer = ExportWriter(tmp_path / "output")

    output = writer.write(
        video_id="vid",
        clip_id="clip_00",
        clip_format=LONG_FORMAT,
        video_path=video,
        metadata=build_metadata(),
        subtitles_path=ass,
        thumbnail_path=thumb,
    )

    assert (output.directory / "ready-to-post.txt").is_file()
    assert output.extra["ready_to_post_path"] == str(output.directory / "ready-to-post.txt")


def test_writer_inclui_video_original_quando_url_informada(tmp_path):
    video, ass, thumb = make_artifacts(tmp_path)
    writer = ExportWriter(tmp_path / "output")

    output = writer.write(
        video_id="vid",
        clip_id="clip_00",
        clip_format=SHORT_FORMAT,
        video_path=video,
        metadata=build_metadata(),
        subtitles_path=ass,
        thumbnail_path=thumb,
        original_video_url="https://youtu.be/vid",
    )

    text = (output.directory / "ready-to-post.txt").read_text(encoding="utf-8")
    assert "Vídeo original: https://youtu.be/vid" in text


def test_writer_sem_metadata_nao_gera_ready_to_post(tmp_path):
    video, ass, _ = make_artifacts(tmp_path)
    writer = ExportWriter(tmp_path / "output")

    output = writer.write(
        video_id="vid",
        clip_id="clip_01",
        clip_format=SHORT_FORMAT,
        video_path=video,
        subtitles_path=ass,
    )

    assert not (output.directory / "ready-to-post.txt").exists()
    assert "ready_to_post_path" not in output.extra


def test_writer_falha_quando_video_final_nao_existe(tmp_path):
    writer = ExportWriter(tmp_path / "output")

    with pytest.raises(ExportError):
        writer.write(
            video_id="vid",
            clip_id="clip_00",
            clip_format=SHORT_FORMAT,
            video_path=tmp_path / "inexistente.mp4",
        )


def test_writer_falha_quando_legenda_declarada_nao_existe(tmp_path):
    video, _, _ = make_artifacts(tmp_path)
    writer = ExportWriter(tmp_path / "output")

    with pytest.raises(ExportError):
        writer.write(
            video_id="vid",
            clip_id="clip_00",
            clip_format=SHORT_FORMAT,
            video_path=video,
            subtitles_path=tmp_path / "sem_legenda.ass",
        )


def test_render_metadata_text_normaliza_hashtags():
    text = render_metadata_text(build_metadata(hashtags=["#ja_tem_cerquilha", "sem"]))
    assert "#ja_tem_cerquilha #sem" in text


def test_render_metadata_text_sem_kb_references():
    assert "(nenhuma)" in render_metadata_text(build_metadata(kb_references=[]))


def test_render_ready_to_post_text_formato_exato():
    """Blocos separados por linha em branco. A linha antes das hashtags nao e estetica:
    colada na descricao, a primeira hashtag e lida como parte da frase por quem passa o
    olho, e no Instagram ela entra na previa do feed junto com o texto."""
    text = render_ready_to_post_text(
        "Titulo do clipe",
        "Descricao do clipe.",
        ["tema", "#ja_tem_cerquilha"],
        handle="renansantosmbl",
    )

    assert text == (
        "Titulo do clipe\n\n"
        "Descricao do clipe.\n\n"
        "@renansantosmbl\n\n"
        "#tema #ja_tem_cerquilha\n"
    )


def test_render_ready_to_post_text_sem_handle_nao_deixa_linha_solta():
    text = render_ready_to_post_text("Titulo", "Descricao.", ["tema"], handle="")

    assert text == "Titulo\n\nDescricao.\n\n#tema\n"


def test_render_ready_to_post_text_normaliza_arroba_ja_escrito():
    text = render_ready_to_post_text("T", "D", ["x"], handle="@renansantosmbl")

    assert "@renansantosmbl" in text
    assert "@@" not in text


def test_render_ready_to_post_text_inclui_video_original_entre_descricao_e_handle():
    text = render_ready_to_post_text(
        "Titulo do clipe",
        "Descricao do clipe.",
        ["tema"],
        handle="renansantosmbl",
        original_video_url="https://youtu.be/abc123",
    )

    assert text == (
        "Titulo do clipe\n\n"
        "Descricao do clipe.\n\n"
        "Vídeo original: https://youtu.be/abc123\n\n"
        "@renansantosmbl\n\n"
        "#tema\n"
    )


def test_render_ready_to_post_text_sem_url_omite_bloco():
    text = render_ready_to_post_text("T", "D", ["x"], handle="", original_video_url=None)

    assert "Vídeo original" not in text


def test_review_queue_marca_clipe_como_pendente(tmp_path):
    video, ass, thumb = make_artifacts(tmp_path)
    writer = ExportWriter(tmp_path / "output")
    output = writer.write(
        video_id="vid",
        clip_id="clip_00",
        clip_format=SHORT_FORMAT,
        video_path=video,
        metadata=build_metadata(),
        subtitles_path=ass,
        thumbnail_path=thumb,
    )

    queue = ReviewQueue()
    queue.enqueue(output)

    assert output.review_status == REVIEW_PENDING
    assert (output.directory / MARKER_NAME).is_file()
    assert queue.is_pending(output)
    assert list(queue.pending(tmp_path / "output")) == [output.directory]


def test_review_queue_aprova_e_remove_o_marcador(tmp_path):
    directory = tmp_path / "output" / "vid" / "clip_00"
    directory.mkdir(parents=True)
    output = ClipOutput(
        clip_id="clip_00",
        video_id="vid",
        format=SHORT_FORMAT,
        directory=directory,
        video_path=directory / "video.mp4",
    )

    queue = ReviewQueue()
    queue.enqueue(output)
    queue.approve(output)

    assert output.review_status == REVIEW_APPROVED
    assert not (directory / MARKER_NAME).exists()
    assert list(queue.pending(tmp_path / "output")) == []


def test_cutter_monta_comando_ffmpeg_com_trecho_correto(tmp_path):
    calls = []

    def runner(command, **kwargs):
        calls.append((command, kwargs))

    cutter = ClipCutter(runner=runner)
    output = cutter.cut(tmp_path / "source.mp4", tmp_path / "out" / "cut.mp4", 12.5, 42.0)

    command = calls[0][0]
    assert command[0] == "ffmpeg"
    assert command[command.index("-ss") + 1] == "12.5"
    assert command[command.index("-t") + 1] == "29.5"
    assert command[-1] == str(output)
    assert calls[0][1] == {"check": True}
    assert output.parent.is_dir()


def test_cutter_nao_gera_duracao_negativa(tmp_path):
    cutter = ClipCutter(runner=lambda command, **kwargs: None)
    command = cutter.build_command(tmp_path / "a.mp4", tmp_path / "b.mp4", 10.0, 5.0)
    assert command[command.index("-t") + 1] == "0"


def test_cutter_aplica_fade_e_loudnorm_por_padrao(tmp_path):
    cutter = ClipCutter(runner=lambda command, **kwargs: None)
    command = cutter.build_command(tmp_path / "a.mp4", tmp_path / "b.mp4", 0.0, 30.0)

    audio_filter = command[command.index("-af") + 1]
    assert "afade=t=in:st=0:d=0.03" in audio_filter
    assert "afade=t=out:st=29.97:d=0.03" in audio_filter
    assert "loudnorm=I=-16.0:TP=-1.5:LRA=11.0" in audio_filter
    assert command.index("-af") < command.index("-c:a")


def test_cutter_pula_fade_em_clipe_curto_demais(tmp_path):
    cutter = ClipCutter(runner=lambda command, **kwargs: None)
    command = cutter.build_command(tmp_path / "a.mp4", tmp_path / "b.mp4", 0.0, 0.02)

    audio_filter = command[command.index("-af") + 1]
    assert "afade" not in audio_filter
    assert "loudnorm" in audio_filter


def test_cutter_loudnorm_desativado_mantem_so_o_fade(tmp_path):
    cutter = ClipCutter(runner=lambda command, **kwargs: None, loudnorm=False)
    command = cutter.build_command(tmp_path / "a.mp4", tmp_path / "b.mp4", 0.0, 30.0)

    audio_filter = command[command.index("-af") + 1]
    assert "afade" in audio_filter
    assert "loudnorm" not in audio_filter


def test_cutter_sem_fade_nem_loudnorm_nao_adiciona_af(tmp_path):
    cutter = ClipCutter(runner=lambda command, **kwargs: None, fade_seconds=0.0, loudnorm=False)
    command = cutter.build_command(tmp_path / "a.mp4", tmp_path / "b.mp4", 0.0, 30.0)

    assert "-af" not in command


def test_cutter_pad_seconds_estende_o_corte_pra_tras_e_pra_frente(tmp_path):
    cutter = ClipCutter(runner=lambda command, **kwargs: None)
    command = cutter.build_command(
        tmp_path / "a.mp4", tmp_path / "b.mp4", 12.5, 42.0, pad_seconds=0.08
    )

    assert command[command.index("-ss") + 1] == "12.42"
    assert command[command.index("-t") + 1] == "29.66"


def test_cutter_pad_seconds_nao_deixa_ss_negativo(tmp_path):
    cutter = ClipCutter(runner=lambda command, **kwargs: None)
    command = cutter.build_command(
        tmp_path / "a.mp4", tmp_path / "b.mp4", 0.02, 5.0, pad_seconds=0.08
    )

    assert command[command.index("-ss") + 1] == "0"


def test_cutter_cut_repassa_pad_seconds_pro_build_command(tmp_path):
    calls = []
    cutter = ClipCutter(runner=lambda command, **kwargs: calls.append(command))
    cutter.cut(tmp_path / "source.mp4", tmp_path / "out" / "cut.mp4", 12.5, 42.0, pad_seconds=0.08)

    assert calls[0][calls[0].index("-ss") + 1] == "12.42"


def test_build_audio_filter_sem_fade_quando_fade_seconds_zero():
    from clipador.export.cutter import build_audio_filter

    assert "afade" not in build_audio_filter(30.0, fade_seconds=0.0)
