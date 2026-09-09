"""Testes do orquestrador ponta a ponta: TODAS as dependencias pesadas sao fakes, 100% offline.

Nenhuma chamada de API, nenhum ffmpeg real, nenhum download, nenhum modelo carregado.
O que se valida aqui e o ORQUESTRADOR: se ele liga as pecas certas, na ordem certa,
e produz a estrutura de saida esperada.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from clipador.download.downloader import DownloadResult
from clipador.export.cutter import ClipCutter
from clipador.export.models import REVIEW_PENDING
from clipador.export.review import MARKER_NAME, ReviewQueue
from clipador.export.thumbnail_frame import ThumbnailFramePrepender
from clipador.export.watermark import WatermarkImages, WatermarkOverlay
from clipador.export.writer import ExportWriter
from clipador.kb.knowledge import KnowledgeBase, KnowledgeDocument, load_knowledge_base
from clipador.pipeline import (
    PipelineConfig,
    PipelineError,
    build_output_folder_name,
    clip_excerpt,
    clip_words,
    run_pipeline,
    slugify_title,
)
from clipador.reframe.models import FaceBox, Scene
from clipador.reframe.reframer import VerticalReframer
from clipador.select.manifest import load_manifest
from clipador.select.models import LONG_FORMAT, SHORT_FORMAT
from clipador.subtitles.builder import AssSubtitleBuilder
from clipador.subtitles.burn import burn_in
from clipador.thumbnail.builder import ThumbnailBuilder
from clipador.thumbnail.extractor import IFrameExtractor
from clipador.thumbnail.models import ThumbnailError
from clipador.transcribe.models import Segment, TranscriptionResult, Word

SILENCE_STARTS = (4, 10, 16)
WORD_COUNT = 20


def build_transcription() -> TranscriptionResult:
    """20 palavras com pausas de silencio antes das palavras 4, 10 e 16."""
    words: list[Word] = []
    cursor = 0.0
    for index in range(WORD_COUNT):
        if index in SILENCE_STARTS:
            cursor += 0.5
        words.append(Word(id=index, text=f"palavra{index}", start=cursor, end=cursor + 0.8))
        cursor += 1.0

    segment = Segment(
        id=0,
        start=words[0].start,
        end=words[-1].end,
        text=" ".join(word.text for word in words),
        words=words,
        speaker="SPEAKER_00",
    )
    return TranscriptionResult(segments=[segment], language="pt", duration=words[-1].end)


def build_kb() -> KnowledgeBase:
    return KnowledgeBase(
        movement="Movimento Exemplo",
        core=[
            KnowledgeDocument(
                name="pautas", title="Pautas", content="Pauta de exemplo: transparencia fiscal."
            )
        ],
        topics_dir=None,
    )


class FakeToolUseBlock:
    def __init__(self, name: str, payload: dict):
        self.type = "tool_use"
        self.name = name
        self.input = payload


class FakeResponse:
    def __init__(self, content: list):
        self.content = content


class FakeMessages:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        index = min(len(self.calls) - 1, len(self._responses) - 1)
        return self._responses[index]


class FakeClient:
    def __init__(self, *responses):
        self.messages = FakeMessages(responses)


def selector_client(candidates: list[dict]) -> FakeClient:
    return FakeClient(FakeResponse([FakeToolUseBlock("propose_clips", {"candidates": candidates})]))


def metadata_client(**overrides) -> FakeClient:
    payload = {
        "title": "Renan Santos sobre transparencia fiscal",
        "description": "Trecho sobre a pauta de transparencia fiscal.",
        "hashtags": ["transparencia", "shorts"],
        "kb_references": ["Pauta: transparencia fiscal"],
        "thumbnail_headline": "E agora?",
    }
    payload.update(overrides)
    return FakeClient(FakeResponse([FakeToolUseBlock("propose_metadata", payload)]))


class FakeTranscriber:
    def __init__(self, transcription: TranscriptionResult):
        self.transcription = transcription
        self.calls: list[Path] = []

    def transcribe(self, audio_path):
        self.calls.append(Path(audio_path))
        return self.transcription


class FakeDownloader:
    def __init__(self, video_path: Path, video_id: str = "T3ENScVymJQ"):
        self.video_path = video_path
        self.video_id = video_id
        self.calls: list[str] = []

    def download(self, url: str) -> DownloadResult:
        self.calls.append(url)
        return DownloadResult(video_path=self.video_path, info={"id": self.video_id})


class FakeSceneDetector:
    def __init__(self):
        self.calls: list[Path] = []

    def detect_scenes(self, video_path):
        self.calls.append(Path(video_path))
        return [Scene(index=0, start_frame=0, end_frame=120, start_time=0.0, end_time=4.0)]


class FakeFrameSampler:
    def frame_size(self, video_path):
        return 1920, 1080

    def frame_count_and_fps(self, video_path):
        return 30, 30.0

    def read_frames(self, video_path, frame_indices):
        return [SimpleNamespace(index=index) for index in frame_indices]


class FakeFaceDetector:
    def detect_faces(self, frame):
        return [FaceBox(x=800.0, y=300.0, width=240.0, height=240.0, confidence=0.9)]


class FakeFrameSaver:
    """Substitui o save real da thumbnail (PIL abrindo o candidato de verdade) - os
    candidatos aqui sao bytes falsos escritos pelo FfmpegSpy, nao imagens validas."""

    def __init__(self):
        self.calls: list[tuple[Path, Path]] = []

    def __call__(self, frame_path, output_path):
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"fake png")
        self.calls.append((Path(frame_path), output_path))


class FfmpegSpy:
    """Substitui o subprocess.run de TODOS os passos de ffmpeg, criando os arquivos esperados."""

    def __init__(self):
        self.commands: list[list[str]] = []

    def __call__(self, command, **kwargs):
        self.commands.append(list(command))
        target = Path(command[-1])
        target.parent.mkdir(parents=True, exist_ok=True)
        if "%" in target.name:
            for index in (1, 2):
                (target.parent / (target.name % index)).write_bytes(b"frame")
        else:
            target.write_bytes(b"media")
        return SimpleNamespace(returncode=0)

    def commands_with(self, token: str) -> list[list[str]]:
        return [command for command in self.commands if any(token in part for part in command)]


def build_components(tmp_path, ffmpeg: FfmpegSpy, thumbnail_builder=None):
    scene_detector = FakeSceneDetector()
    reframer = VerticalReframer(
        scene_detector=scene_detector,
        face_detector=FakeFaceDetector(),
        frame_sampler=FakeFrameSampler(),
        runner=ffmpeg,
    )
    frame_saver = FakeFrameSaver()
    builder = thumbnail_builder or ThumbnailBuilder(
        extractor=IFrameExtractor(runner=ffmpeg),
        sharpness_scorer=SimpleNamespace(score=lambda frame: 1.0),
        face_scorer=SimpleNamespace(score=lambda frame: 0.5),
        save_frame=frame_saver,
        frame_loader=lambda path: SimpleNamespace(path=path),
    )
    return {
        "cutter": ClipCutter(runner=ffmpeg),
        "reframer": reframer,
        "subtitle_builder": AssSubtitleBuilder(),
        "burner": lambda video, ass, output, **kwargs: burn_in(
            video, ass, output, runner=ffmpeg, **kwargs
        ),
        "thumbnail_builder": builder,
        "thumbnail_frame_prepender": ThumbnailFramePrepender(
            frame_sampler=FakeFrameSampler(), runner=ffmpeg
        ),
        "watermark_overlay": WatermarkOverlay(
            frame_sampler=FakeFrameSampler(), runner=ffmpeg
        ),
        "writer": ExportWriter(tmp_path / "output"),
        "review_queue": ReviewQueue(),
    }, scene_detector, frame_saver


def build_config(tmp_path) -> PipelineConfig:
    # Os fixtures deste arquivo usam duracoes sinteticas minusculas (nao testam politica
    # de duracao, testam a fiacao do pipeline) - desliga a rede de seguranca de duracao
    # pra nao descartar os candidatos de teste.
    return PipelineConfig(
        output_root=tmp_path / "output",
        work_dir=tmp_path / "work",
        watermark=None,
        enforce_duration_bounds=False,
    )


TWO_FORMAT_CANDIDATES = [
    {
        "start_word_id": 5,
        "end_word_id": 13,
        "format": SHORT_FORMAT,
        "score": 91,
        "justificativa": "Gancho forte sobre transparencia fiscal.",
    },
    {
        "start_word_id": 16,
        "end_word_id": 19,
        "format": LONG_FORMAT,
        "score": 74,
        "justificativa": "Desenvolve a pauta com contexto.",
    },
]


def run_happy_path(
    tmp_path,
    thumbnail_builder=None,
    on_progress=None,
    eleitoral_text=None,
    generate_thumbnail=None,
):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video de origem")
    ffmpeg = FfmpegSpy()
    components, scene_detector, frame_saver = build_components(tmp_path, ffmpeg, thumbnail_builder)
    transcriber = FakeTranscriber(build_transcription())

    extra = {} if on_progress is None else {"on_progress": on_progress}
    config = build_config(tmp_path)
    if eleitoral_text is not None:
        config = replace(config, eleitoral_enabled=True, eleitoral_text=eleitoral_text)
    if generate_thumbnail is not None:
        config = replace(config, generate_thumbnail=generate_thumbnail)
    result = run_pipeline(
        source,
        build_kb(),
        config,
        transcriber=transcriber,
        selector_client=selector_client(TWO_FORMAT_CANDIDATES),
        metadata_client=metadata_client(),
        **components,
        **extra,
    )
    return result, ffmpeg, scene_detector, frame_saver, transcriber


def test_pipeline_produz_um_clipe_de_cada_formato_completo(tmp_path):
    result, _, _, _, _ = run_happy_path(tmp_path)

    assert result.failures == []
    assert [clip.format for clip in result.clips] == [SHORT_FORMAT, LONG_FORMAT]

    for clip in result.clips:
        assert clip.video_path.is_file()
        assert clip.subtitles_path.is_file()
        assert clip.thumbnail_path.is_file()
        assert clip.metadata_path.is_file()
        assert (clip.directory / "metadata.json").is_file()


def test_pipeline_emite_progresso_com_plano_e_um_evento_por_clipe(tmp_path):
    events = []
    result, _, _, _, _ = run_happy_path(tmp_path, on_progress=events.append)

    assert result.failures == []
    plan_events = [event for event in events if event["event"] == "plan"]
    assert plan_events == [
        {"event": "plan", "total": 2, "message": "2 clipe(s) planejado(s)"}
    ]

    done_events = [event for event in events if event["event"] == "clip_done"]
    assert [event["format"] for event in done_events] == [SHORT_FORMAT, LONG_FORMAT]
    assert [event["index"] for event in done_events] == [1, 2]
    assert all(event["total"] == 2 for event in done_events)
    assert all(event["status"] == REVIEW_PENDING for event in done_events)

    start_events = [event for event in events if event["event"] == "clip_start"]
    assert len(start_events) == 2
    # Cada clipe inicia antes de concluir, na mesma posicao.
    assert [event["index"] for event in start_events] == [1, 2]


def test_pipeline_emite_clip_failed_sem_derrubar_os_demais(tmp_path):
    class AlwaysExplodingThumbnailBuilder:
        def build(
            self, video_path, output_path, candidates_dir, start=None, end=None, headline="", subject=None
        ):
            raise ThumbnailError("nenhum frame candidato extraido")

    events = []
    result, _, _, _, _ = run_happy_path(
        tmp_path, thumbnail_builder=AlwaysExplodingThumbnailBuilder(), on_progress=events.append
    )

    assert result.clips == []
    assert len(result.failures) == 2
    failed_events = [event for event in events if event["event"] == "clip_failed"]
    assert len(failed_events) == 2
    assert all(event["stage"] == "thumbnail" for event in failed_events)
    assert [event["index"] for event in failed_events] == [1, 2]


def test_pipeline_generate_thumbnail_desligado_pula_a_etapa_por_completo(tmp_path):
    """Com generate_thumbnail=False, thumbnail_builder.build NUNCA e chamado (o builder
    usado aqui explode se for) e todo clipe sai sem nenhuma thumbnail."""

    class AlwaysExplodingThumbnailBuilder:
        def build(
            self, video_path, output_path, candidates_dir, start=None, end=None, headline="", subject=None
        ):
            raise ThumbnailError("nao deveria ter sido chamado")

    result, ffmpeg, _, _, _ = run_happy_path(
        tmp_path,
        thumbnail_builder=AlwaysExplodingThumbnailBuilder(),
        generate_thumbnail=False,
    )

    assert result.failures == []
    assert len(result.clips) == 2
    assert all(clip.thumbnail_path is None for clip in result.clips)
    # Formato curto tambem nao prende capa como 1o frame quando nao ha thumbnail nenhuma.
    assert ffmpeg.commands_with("with_thumbnail_frame.mp4") == []


def run_with_watermark(tmp_path):
    """Mesmo happy path, mas com a marca d'agua ligada e um PNG por formato."""
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video de origem")
    ffmpeg = FfmpegSpy()
    components, _, _ = build_components(tmp_path, ffmpeg)
    short_png = tmp_path / "wm_short.png"
    long_png = tmp_path / "wm_long.png"
    short_png.write_bytes(b"png curto")
    long_png.write_bytes(b"png longo")
    config = PipelineConfig(
        output_root=tmp_path / "output",
        work_dir=tmp_path / "work",
        watermark=WatermarkImages(short=short_png, long=long_png),
        enforce_duration_bounds=False,
    )

    result = run_pipeline(
        source,
        build_kb(),
        config,
        transcriber=FakeTranscriber(build_transcription()),
        selector_client=selector_client(TWO_FORMAT_CANDIDATES),
        metadata_client=metadata_client(),
        **components,
    )
    return result, ffmpeg, short_png, long_png


def test_pipeline_estampa_a_marca_dagua_do_formato_de_cada_clipe(tmp_path):
    result, ffmpeg, short_png, long_png = run_with_watermark(tmp_path)

    assert result.failures == []
    # Filtra pela SAIDA, nao por "aparece no comando": o passo seguinte (prender a
    # thumbnail como 1o frame) recebe o watermarked.mp4 como entrada e tambem casaria.
    comandos = [c for c in ffmpeg.commands if c[-1].endswith("watermarked.mp4")]
    assert len(comandos) == 2
    imagens = {part for command in comandos for part in command if part.endswith(".png")}
    assert imagens == {str(short_png), str(long_png)}


def test_pipeline_estampa_a_marca_antes_de_prender_a_thumbnail_como_1o_frame(tmp_path):
    # A capa (1o frame do formato curto) precisa sair SEM marca: ela ja carrega a
    # identidade do canal, e branding no primeiro frame aumenta a taxa de skip.
    _, ffmpeg, _, _ = run_with_watermark(tmp_path)

    prepend = ffmpeg.commands_with("with_thumbnail_frame.mp4")[0]
    assert any(part.endswith("watermarked.mp4") for part in prepend)


def test_pipeline_sem_marca_dagua_nao_roda_a_etapa_de_overlay(tmp_path):
    _, ffmpeg, _, _, _ = run_happy_path(tmp_path)

    assert [c for c in ffmpeg.commands if c[-1].endswith("watermarked.mp4")] == []


def test_pipeline_estampa_a_tarja_eleitoral_no_curto_e_no_longo(tmp_path):
    """A tarja de propaganda eleitoral vale para os dois formatos: o happy path gera um
    clipe curto e um longo, os dois devem ganhar a etapa `eleitoral`."""
    result, ffmpeg, _, _, _ = run_happy_path(tmp_path, eleitoral_text="PROPAGANDA ELEITORAL")

    assert result.failures == []
    comandos = [c for c in ffmpeg.commands if c[-1].endswith("eleitoral.mp4")]
    assert len(comandos) == 2


def test_pipeline_sem_texto_eleitoral_nao_roda_a_etapa(tmp_path):
    _, ffmpeg, _, _, _ = run_happy_path(tmp_path)

    assert [c for c in ffmpeg.commands if c[-1].endswith("eleitoral.mp4")] == []


def test_pipeline_nao_gera_thumbnail_do_video_principal_por_padrao(tmp_path):
    result, _, _, _, _ = run_happy_path(tmp_path)

    assert result.main_thumbnail is None


def test_pipeline_gera_thumbnail_do_video_principal_quando_habilitado(tmp_path):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video de origem")
    ffmpeg = FfmpegSpy()
    components, _, _ = build_components(tmp_path, ffmpeg)
    transcriber = FakeTranscriber(build_transcription())
    config = PipelineConfig(
        output_root=tmp_path / "output",
        work_dir=tmp_path / "work",
        watermark=None,
        enforce_duration_bounds=False,
        generate_main_thumbnail=True,
    )

    result = run_pipeline(
        source,
        build_kb(),
        config,
        transcriber=transcriber,
        selector_client=selector_client(TWO_FORMAT_CANDIDATES),
        metadata_client=metadata_client(),
        **components,
    )

    assert result.main_thumbnail is not None
    assert result.main_thumbnail.thumbnail_path.is_file()
    assert result.main_thumbnail.metadata_path.is_file()
    assert result.main_thumbnail.ready_to_post_path.is_file()
    assert result.main_thumbnail.metadata.title


def test_pipeline_reenquadra_apenas_o_formato_vertical(tmp_path):
    _, ffmpeg, scene_detector, _, _ = run_happy_path(tmp_path)

    assert len(scene_detector.calls) == 1
    assert len(ffmpeg.commands_with("crop=")) == 1


def test_pipeline_queima_legenda_nos_dois_clipes(tmp_path):
    _, ffmpeg, _, _, _ = run_happy_path(tmp_path)

    burn_commands = ffmpeg.commands_with("ass=")
    assert len(burn_commands) == 2
    for command in burn_commands:
        assert command[-1].endswith("burned.mp4")


def test_pipeline_prende_thumbnail_como_primeiro_frame_apenas_no_curto(tmp_path):
    """A etapa de prender a thumbnail como frame 0 (`concat` no filter_complex) so pode
    rodar pro formato curto (vertical) - o longo nao tem essa exigencia de previa."""
    _, ffmpeg, _, _, _ = run_happy_path(tmp_path)

    with_thumbnail_frame_commands = [
        command for command in ffmpeg.commands if Path(command[-1]).name == "with_thumbnail_frame.mp4"
    ]
    assert len(with_thumbnail_frame_commands) == 1

    concat_commands = ffmpeg.commands_with("concat=")
    assert len(concat_commands) == 1


def test_pipeline_usa_playres_diferente_por_formato_na_legenda(tmp_path):
    """Formato curto (9:16) usa PlayRes vertical; formato longo (16:9) usa PlayRes
    horizontal - a legenda nao pode ser gerada com o canvas errado pro clipe."""
    result, _, _, _, _ = run_happy_path(tmp_path)

    by_format = {clip.format: clip for clip in result.clips}
    short_ass = by_format[SHORT_FORMAT].subtitles_path.read_text(encoding="utf-8")
    long_ass = by_format[LONG_FORMAT].subtitles_path.read_text(encoding="utf-8")

    assert "PlayResX: 1080" in short_ass
    assert "PlayResY: 1920" in short_ass
    assert "PlayResX: 1920" in long_ass
    assert "PlayResY: 1080" in long_ass


def test_pipeline_propaga_kb_references_ate_o_export(tmp_path):
    result, _, _, _, _ = run_happy_path(tmp_path)

    for clip in result.clips:
        assert clip.kb_references == ["Pauta: transparencia fiscal"]
        assert "Pauta: transparencia fiscal" in clip.metadata_path.read_text(encoding="utf-8")


def test_pipeline_usa_snap_to_silence_antes_de_cortar(tmp_path):
    """Criterio de aceite 3: o corte cai sempre em fronteira de silencio, nunca no meio da fala."""
    result, ffmpeg, _, _, _ = run_happy_path(tmp_path)
    transcription = build_transcription()

    # O LLM pediu 5..13 (no meio de blocos de fala); o snap move para 4..15.
    short_candidate = result.candidates[0]
    assert (short_candidate.start_word_id, short_candidate.end_word_id) == (4, 15)
    assert short_candidate.start == transcription.word_by_id(4).start
    assert short_candidate.end == transcription.word_by_id(15).end

    # O corte real ainda sai do padding de contexto (config.context_pad_seconds),
    # comido do proprio silencio que o snap_to_silence garantiu existir ali -
    # o ponto do criterio de aceite e o -ss nunca cair no meio de uma palavra,
    # o que continua valendo com ou sem o padding.
    cut_command = ffmpeg.commands_with("libx264")[0]
    config = build_config(tmp_path)
    assert float(cut_command[cut_command.index("-ss") + 1]) == pytest.approx(
        short_candidate.start - config.context_pad_seconds
    )


def test_pipeline_marca_todo_clipe_como_pendente_de_revisao(tmp_path):
    result, _, _, _, _ = run_happy_path(tmp_path)

    for clip in result.clips:
        assert clip.review_status == REVIEW_PENDING
        assert (clip.directory / MARKER_NAME).is_file()

    pending = list(ReviewQueue().pending(tmp_path / "output"))
    assert len(pending) == 2


def test_pipeline_continua_quando_um_clipe_falha(tmp_path):
    class ExplodingThumbnailBuilder:
        def __init__(self):
            self.calls = 0

        def build(
            self, video_path, output_path, candidates_dir, start=None, end=None, headline="", subject=None
        ):
            self.calls += 1
            if self.calls == 1:
                raise ThumbnailError("nenhum frame candidato extraido")
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(output_path).write_bytes(b"fake png")
            return Path(output_path)

    result, _, _, _, _ = run_happy_path(tmp_path, thumbnail_builder=ExplodingThumbnailBuilder())

    assert len(result.clips) == 1
    assert result.clips[0].format == LONG_FORMAT
    assert len(result.failures) == 1
    assert result.failures[0].stage == "thumbnail"
    assert result.failures[0].clip_id == f"91_clip_00_{SHORT_FORMAT}"
    assert "nenhum frame candidato" in result.failures[0].message


def test_pipeline_nao_marca_trecho_como_usado_quando_o_clipe_falha(tmp_path):
    """P2.1: um erro transitorio numa etapa (aqui, thumbnail) nao pode queimar o trecho
    pra sempre no manifesto - senao aquele trecho nunca mais seria escolhido, mesmo sem
    nunca ter virado clipe de verdade. So o clipe que realmente exportou fica reservado."""

    class ExplodingThumbnailBuilder:
        def __init__(self):
            self.calls = 0

        def build(
            self, video_path, output_path, candidates_dir, start=None, end=None, headline="", subject=None
        ):
            self.calls += 1
            if self.calls == 1:
                raise ThumbnailError("nenhum frame candidato extraido")
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(output_path).write_bytes(b"fake png")
            return Path(output_path)

    result, _, _, _, _ = run_happy_path(tmp_path, thumbnail_builder=ExplodingThumbnailBuilder())
    assert len(result.failures) == 1
    assert result.failures[0].stage == "thumbnail"

    short_candidate = next(c for c in result.candidates if c.format == SHORT_FORMAT)
    long_candidate = next(c for c in result.candidates if c.format == LONG_FORMAT)
    manifest = load_manifest(tmp_path / "output" / "source" / "manifest.json")

    assert manifest.ranges_for(SHORT_FORMAT) == []
    assert manifest.ranges_for(LONG_FORMAT) == [
        (long_candidate.start_word_id, long_candidate.end_word_id)
    ]


def test_pipeline_categoria_politica_repassa_o_subject_escolhido_pro_thumbnail_builder(tmp_path):
    """P: um clipe sobre outra figura publica nao pode herdar a referencia facial de
    quem apareceu num clipe anterior - a escolha e por clipe (`select_thumbnail_subject`),
    e o resultado tem que chegar em `thumbnail_builder.build(subject=...)`."""
    import clipador.pipeline as pipeline_module
    from clipador.thumbnail.face_library import PoliticalFigure

    chosen = PoliticalFigure("lula", "Lula", tmp_path / "lula_fotos")
    subject_calls: list[tuple] = []

    def fake_select(candidate, transcript_excerpt, client):
        subject_calls.append((candidate, transcript_excerpt, client))
        return chosen

    original = pipeline_module.select_thumbnail_subject
    pipeline_module.select_thumbnail_subject = fake_select
    try:
        class SubjectSpyThumbnailBuilder:
            def __init__(self):
                self.subjects: list[Any] = []

            def build(
                self, video_path, output_path, candidates_dir, start=None, end=None,
                headline="", subject=None,
            ):
                self.subjects.append(subject)
                Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                Path(output_path).write_bytes(b"fake png")
                return Path(output_path)

        spy = SubjectSpyThumbnailBuilder()
        run_happy_path(tmp_path, thumbnail_builder=spy)
    finally:
        pipeline_module.select_thumbnail_subject = original

    assert len(subject_calls) == 2  # um por clipe (1 curto + 1 longo no happy path)
    assert spy.subjects == [chosen, chosen]


def test_pipeline_categoria_jogos_nunca_chama_selecao_de_assunto_da_thumbnail(tmp_path):
    """Jogos nao tem figura publica pra escolher - a chamada nem deveria acontecer,
    pra nao gastar uma chamada de LLM a toa em toda categoria que nao usa isso."""
    import clipador.pipeline as pipeline_module

    calls: list[Any] = []

    def fake_select(*args, **kwargs):
        calls.append(1)
        return None

    original = pipeline_module.select_thumbnail_subject
    pipeline_module.select_thumbnail_subject = fake_select
    try:
        source = tmp_path / "source.mp4"
        source.write_bytes(b"video de origem")
        ffmpeg = FfmpegSpy()
        components, _, _ = build_components(tmp_path, ffmpeg)
        config = PipelineConfig(
            output_root=tmp_path / "output",
            work_dir=tmp_path / "work",
            watermark=None,
            enforce_duration_bounds=False,
            category="jogos",
        )

        run_pipeline(
            source,
            build_kb(),
            config,
            transcriber=FakeTranscriber(build_transcription()),
            selector_client=selector_client(TWO_FORMAT_CANDIDATES),
            metadata_client=metadata_client(),
            **components,
        )
    finally:
        pipeline_module.select_thumbnail_subject = original

    assert calls == []


def test_pipeline_extrai_thumbnail_do_video_antes_da_legenda_queimada(tmp_path):
    """A thumbnail nao pode sair do `burned.mp4`: os frames candidatos viriam com a
    legenda karaoke desenhada dentro da imagem."""

    class ThumbnailSpy:
        def __init__(self):
            self.videos: list[Path] = []
            self.headlines: list[str] = []

        def build(
            self, video_path, output_path, candidates_dir, start=None, end=None, headline="", subject=None
        ):
            self.videos.append(Path(video_path))
            self.headlines.append(headline)
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(output_path).write_bytes(b"fake png")
            return Path(output_path)

    spy = ThumbnailSpy()
    run_happy_path(tmp_path, thumbnail_builder=spy)

    assert [video.name for video in spy.videos] == ["reframed.mp4", "cut.mp4"]
    assert spy.headlines == ["E agora?", "E agora?"]


def test_pipeline_pula_download_para_arquivo_local(tmp_path):
    source = tmp_path / "master.mp4"
    source.write_bytes(b"video de origem")
    ffmpeg = FfmpegSpy()
    components, _, _ = build_components(tmp_path, ffmpeg)
    downloader = FakeDownloader(source)

    result = run_pipeline(
        source,
        build_kb(),
        build_config(tmp_path),
        downloader=downloader,
        transcriber=FakeTranscriber(build_transcription()),
        selector_client=selector_client(TWO_FORMAT_CANDIDATES[:1]),
        metadata_client=metadata_client(),
        **components,
    )

    assert downloader.calls == []
    assert result.video_id == "master"
    assert result.video_path == source


def test_pipeline_baixa_quando_a_entrada_e_url(tmp_path):
    downloaded = tmp_path / "T3ENScVymJQ.mp4"
    downloaded.write_bytes(b"video baixado")
    ffmpeg = FfmpegSpy()
    components, _, _ = build_components(tmp_path, ffmpeg)
    downloader = FakeDownloader(downloaded)
    transcriber = FakeTranscriber(build_transcription())

    result = run_pipeline(
        "https://www.youtube.com/live/T3ENScVymJQ",
        build_kb(),
        build_config(tmp_path),
        downloader=downloader,
        transcriber=transcriber,
        selector_client=selector_client(TWO_FORMAT_CANDIDATES[:1]),
        metadata_client=metadata_client(),
        **components,
    )

    assert downloader.calls == ["https://www.youtube.com/live/T3ENScVymJQ"]
    assert transcriber.calls == [downloaded]
    assert result.video_id == "T3ENScVymJQ"
    assert result.clips[0].directory.parent.parent.name == "T3ENScVymJQ"


def test_pipeline_falha_quando_arquivo_local_some_antes_do_run(tmp_path):
    source = tmp_path / "sumiu.mp4"
    source.write_bytes(b"video")
    ffmpeg = FfmpegSpy()
    components, _, _ = build_components(tmp_path, ffmpeg)

    from clipador.ingest.source import IngestSource, SourceKind

    def fake_resolve(entry):
        return IngestSource(SourceKind.LOCAL_FILE, str(tmp_path / "inexistente.mp4"))

    import clipador.pipeline as pipeline_module

    original = pipeline_module.resolve_source
    pipeline_module.resolve_source = fake_resolve
    try:
        with pytest.raises(PipelineError):
            run_pipeline(source, build_kb(), build_config(tmp_path), **components)
    finally:
        pipeline_module.resolve_source = original


def test_pipeline_gerar_mais_reaproveita_transcricao_e_nao_repete_contexto(tmp_path):
    """Fluxo de "gerar mais": chamar run_pipeline de novo pro mesmo video (1) nao
    retranscreve (cache em work_dir), (2) nao repete o mesmo trecho NO MESMO formato
    (manifesto em output_root), (3) continua a numeracao de clip_id sem colidir com o
    que ja foi exportado na rodada anterior."""
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video de origem")
    kb = build_kb()
    config = PipelineConfig(
        output_root=tmp_path / "output",
        work_dir=tmp_path / "work",
        watermark=None,
        min_short_clips=1,
        min_long_clips=1,
        enforce_duration_bounds=False,
    )
    transcriber = FakeTranscriber(build_transcription())

    ffmpeg1 = FfmpegSpy()
    components1, _, _ = build_components(tmp_path, ffmpeg1)
    first = run_pipeline(
        source,
        kb,
        config,
        transcriber=transcriber,
        selector_client=selector_client(TWO_FORMAT_CANDIDATES),
        metadata_client=metadata_client(),
        **components1,
    )

    assert [c.format for c in first.clips] == [SHORT_FORMAT, LONG_FORMAT]
    assert transcriber.calls == [source]

    # Rodada 2: candidatos apontando pra trechos DIFERENTES (mesma transcricao de 20
    # palavras, blocos de silencio nao usados pela rodada 1).
    more_candidates = [
        {**TWO_FORMAT_CANDIDATES[0], "start_word_id": 0, "end_word_id": 3},
        {**TWO_FORMAT_CANDIDATES[1], "start_word_id": 4, "end_word_id": 9},
    ]
    ffmpeg2 = FfmpegSpy()
    components2, _, _ = build_components(tmp_path, ffmpeg2)
    second = run_pipeline(
        source,
        kb,
        config,
        transcriber=transcriber,
        selector_client=selector_client(more_candidates),
        metadata_client=metadata_client(),
        **components2,
    )

    # Transcricao NAO foi refeita - o transcriber so foi chamado na rodada 1.
    assert transcriber.calls == [source]

    assert [c.format for c in second.clips] == [SHORT_FORMAT, LONG_FORMAT]
    first_ids = {clip.clip_id for clip in first.clips}
    second_ids = {clip.clip_id for clip in second.clips}
    assert first_ids.isdisjoint(second_ids)

    # Pasta separada por formato, numeracao continuando entre rodadas.
    for clip in first.clips + second.clips:
        expected_subdir = "short" if clip.format == SHORT_FORMAT else "long"
        assert clip.directory.parent.name == expected_subdir


# --- nome de pasta de output (video_id + titulo) ---------------------------


def test_slugify_title_remove_caracteres_proibidos_no_windows():
    assert slugify_title('Titulo: "Especial" <teste> | parte/2\\3') == "Titulo_Especial_teste_parte23"


def test_slugify_title_colapsa_espacos_em_underscore():
    assert slugify_title("varios   espacos   aqui") == "varios_espacos_aqui"


def test_slugify_title_trunca_no_tamanho_maximo():
    titulo = "a" * 100
    assert len(slugify_title(titulo)) == 60


def test_slugify_title_reduz_acento_para_a_letra_base():
    assert slugify_title("Não é possível") == "Nao_e_possivel"


def test_slugify_title_descarta_caractere_nao_ascii_sem_equivalente():
    """P2.3: bug real de producao - titulo com travessao gerou pasta
    '..._Livro_Amarelo_—_EP.06', caractere nao-ASCII em caminho e fonte de problema de
    encoding em outras ferramentas. O travessao nao tem letra base em ASCII, e descartado
    (nao vira '_' extra: o underscore ao redor ja colapsa)."""
    assert slugify_title("Livro Amarelo — EP.06") == "Livro_Amarelo_EP.06"


def test_build_output_folder_name_concatena_id_e_titulo():
    assert build_output_folder_name("T3ENScVymJQ", "Titulo Legal") == "T3ENScVymJQ_Titulo_Legal"


def test_build_output_folder_name_sem_titulo_usa_so_o_id():
    assert build_output_folder_name("T3ENScVymJQ", None) == "T3ENScVymJQ"
    assert build_output_folder_name("T3ENScVymJQ", "") == "T3ENScVymJQ"


def test_pipeline_usa_titulo_do_sidecar_info_json_pra_nomear_a_pasta(tmp_path):
    """Arquivo local com um `<nome>.info.json` do yt-dlp ao lado (convencao de quando o
    arquivo veio de um download anterior) - a pasta de output usa o titulo de la, mesmo
    sem baixar de novo."""
    source = tmp_path / "T3ENScVymJQ.mp4"
    source.write_bytes(b"video de origem")
    (tmp_path / "T3ENScVymJQ.info.json").write_text(
        '{"title": "RENAN SANTOS: pronunciamento"}', encoding="utf-8"
    )
    ffmpeg = FfmpegSpy()
    components, _, _ = build_components(tmp_path, ffmpeg)

    result = run_pipeline(
        source,
        build_kb(),
        build_config(tmp_path),
        transcriber=FakeTranscriber(build_transcription()),
        selector_client=selector_client(TWO_FORMAT_CANDIDATES),
        metadata_client=metadata_client(),
        **components,
    )

    assert result.clips[0].directory.parent.parent.name == "T3ENScVymJQ_RENAN_SANTOS_pronunciamento"


def test_pipeline_sem_sidecar_info_json_usa_so_o_video_id_na_pasta(tmp_path):
    result, _, _, _, _ = run_happy_path(tmp_path)  # source.mp4 sem .info.json ao lado

    assert result.clips[0].directory.parent.parent.name == "source"


def test_pipeline_prefixa_clip_id_com_a_pontuacao_pra_ordenar_por_pasta(tmp_path):
    """Score na frente do nome: ordenacao alfabetica de pasta vira ordenacao por
    pontuacao sem ferramenta nenhuma (o pedido original do usuario)."""
    result, _, _, _, _ = run_happy_path(tmp_path)

    by_format = {clip.format: clip for clip in result.clips}
    assert by_format[SHORT_FORMAT].clip_id.startswith("91_")  # score do TWO_FORMAT_CANDIDATES[0]
    assert by_format[LONG_FORMAT].clip_id.startswith("74_")  # score do TWO_FORMAT_CANDIDATES[1]


def test_clip_words_rebaseia_o_tempo_para_o_inicio_do_clipe():
    transcription = build_transcription()
    offset = transcription.word_by_id(4).start

    words = clip_words(transcription, 4, 6, offset)

    assert [word.id for word in words] == [4, 5, 6]
    assert words[0].start == pytest.approx(0.0)
    assert words[-1].end == pytest.approx(transcription.word_by_id(6).end - offset)


def test_clip_excerpt_junta_apenas_as_palavras_do_trecho():
    assert clip_excerpt(build_transcription(), 2, 4) == "palavra2 palavra3 palavra4"


def test_kb_e_editavel_sem_reprocessamento(tmp_path):
    """Criterio de aceite 4: editar o .md e reinstanciar basta, nao ha indice para reconstruir."""
    core = tmp_path / "kb" / "core"
    core.mkdir(parents=True)
    (core / "10-pautas.md").write_text("# Pautas\n\nTransparencia fiscal.", encoding="utf-8")

    before = load_knowledge_base(tmp_path / "kb", "Movimento Exemplo").dossier()
    assert "Transparencia fiscal." in before

    (core / "10-pautas.md").write_text("# Pautas\n\nSeguranca publica.", encoding="utf-8")
    after = load_knowledge_base(tmp_path / "kb", "Movimento Exemplo").dossier()

    assert "Seguranca publica." in after
    assert "Transparencia fiscal." not in after
