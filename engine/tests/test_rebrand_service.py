"""Testes de `rebrand_batch`: TODAS as dependencias pesadas sao fakes, 100% offline.

Nenhum ffmpeg real, nenhum modelo de rosto carregado, nenhuma chamada de API. O que se
valida aqui e o ORQUESTRADOR EM LOTE: se ele descobre os videos da pasta de entrada,
transcreve/gera metadata/thumbnail/prende frame/anexa outro/exporta/enfileira revisao
para cada um, isola falha por video e produz UMA pasta de saida com todos os clipes do
lote dentro, na mesma estrutura do pipeline principal.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from clipador.export.models import REVIEW_PENDING
from clipador.export.outro_appender import OutroImageAppender
from clipador.export.periodic_flash import PeriodicImageFlasher
from clipador.export.review import ReviewQueue
from clipador.export.thumbnail_frame import ThumbnailFramePrepender
from clipador.export.writer import ExportWriter
from clipador.kb.knowledge import KnowledgeBase, KnowledgeDocument
from clipador.rebrand.service import RebrandBatchResult, discover_videos, rebrand_batch
from clipador.select.models import SHORT_FORMAT
from clipador.thumbnail.builder import ThumbnailBuilder
from clipador.thumbnail.extractor import IFrameExtractor
from clipador.transcribe.models import Segment, TranscriptionResult, Word


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


def metadata_client(**overrides) -> FakeClient:
    payload = {
        "title": "Titulo de rebrand",
        "description": "Descricao de rebrand gerada pelo LLM.",
        "hashtags": ["shorts", "politica"],
        "kb_references": ["Pauta: transparencia fiscal"],
        "thumbnail_headline": "E agora?",
    }
    payload.update(overrides)
    return FakeClient(FakeResponse([FakeToolUseBlock("propose_metadata", payload)]))


def build_transcription(word_count: int = 10) -> TranscriptionResult:
    words = [
        Word(id=index, text=f"palavra{index}", start=float(index), end=float(index) + 0.8)
        for index in range(word_count)
    ]
    segment = Segment(
        id=0,
        start=words[0].start,
        end=words[-1].end,
        text=" ".join(word.text for word in words),
        words=words,
    )
    return TranscriptionResult(segments=[segment], language="pt", duration=words[-1].end)


class FakeTranscriber:
    """Transcricao fake: mesmo resultado pra todo video, ou excecao configurada por
    nome de arquivo (`fail_for`) - usado pra testar isolamento de erro por video."""

    def __init__(
        self, transcription: TranscriptionResult | None = None, fail_for: str | None = None
    ):
        self.transcription = transcription or build_transcription()
        self.fail_for = fail_for
        self.calls: list[Path] = []

    def transcribe(self, video_path):
        self.calls.append(Path(video_path))
        if self.fail_for and Path(video_path).name == self.fail_for:
            raise RuntimeError("falha simulada de transcricao")
        return self.transcription


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


class FakeFrameSampler:
    def frame_size(self, video_path):
        return 1080, 1920

    def frame_count_and_fps(self, video_path):
        return 300, 30.0

    def read_frames(self, video_path, frame_indices):
        return [SimpleNamespace(index=index) for index in frame_indices]


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


def build_outro_image(tmp_path: Path) -> Path:
    path = tmp_path / "outro.jpg"
    Image.new("RGB", (600, 600), color=(0, 0, 0)).save(path)
    return path


def build_components(tmp_path: Path, ffmpeg: FfmpegSpy) -> dict:
    thumbnail_builder = ThumbnailBuilder(
        extractor=IFrameExtractor(runner=ffmpeg),
        sharpness_scorer=SimpleNamespace(score=lambda frame: 1.0),
        face_scorer=SimpleNamespace(score=lambda frame: 0.5),
        save_frame=FakeFrameSaver(),
        frame_loader=lambda path: SimpleNamespace(path=path),
    )
    return {
        "thumbnail_builder": thumbnail_builder,
        "flasher": PeriodicImageFlasher(frame_sampler=FakeFrameSampler(), runner=ffmpeg),
        "frame_prepender": ThumbnailFramePrepender(frame_sampler=FakeFrameSampler(), runner=ffmpeg),
        "outro_appender": OutroImageAppender(frame_sampler=FakeFrameSampler(), runner=ffmpeg),
        "writer": ExportWriter(tmp_path / "output"),
        "review_queue": ReviewQueue(),
    }


def make_input_dir(tmp_path: Path, names: list[str]) -> Path:
    input_dir = tmp_path / "entrada"
    input_dir.mkdir()
    for name in names:
        (input_dir / name).write_bytes(b"video de entrada")
    return input_dir


def test_discover_videos_acha_so_extensoes_de_video_ordenados(tmp_path):
    input_dir = tmp_path / "entrada"
    input_dir.mkdir()
    (input_dir / "b.mp4").write_bytes(b"x")
    (input_dir / "a.mov").write_bytes(b"x")
    (input_dir / "c.mkv").write_bytes(b"x")
    (input_dir / "notas.txt").write_bytes(b"x")
    (input_dir / "subpasta").mkdir()

    videos = discover_videos(input_dir)

    assert [path.name for path in videos] == ["a.mov", "b.mp4", "c.mkv"]


def test_rebrand_batch_gera_uma_pasta_de_output_com_todos_os_clipes_do_lote(tmp_path):
    input_dir = make_input_dir(tmp_path, ["video1.mp4", "video2.mp4", "video3.mp4"])
    ffmpeg = FfmpegSpy()
    outro_image = build_outro_image(tmp_path)
    components = build_components(tmp_path, ffmpeg)

    result = rebrand_batch(
        input_dir,
        build_kb(),
        output_root=tmp_path / "output",
        work_dir=tmp_path / "work",
        outro_image=outro_image,
        transcriber=FakeTranscriber(),
        metadata_client=metadata_client(),
        **components,
    )

    assert isinstance(result, RebrandBatchResult)
    assert result.batch_folder == "rebrand_entrada"
    assert result.failures == []
    assert len(result.clips) == 3
    assert {clip.clip_id for clip in result.clips} == {"video1", "video2", "video3"}

    for clip in result.clips:
        assert clip.format == SHORT_FORMAT
        assert clip.review_status == REVIEW_PENDING
        assert clip.video_path.is_file()
        assert clip.thumbnail_path is not None and clip.thumbnail_path.is_file()
        assert clip.metadata is not None
        assert clip.metadata.title == "Titulo de rebrand"
        assert clip.directory == tmp_path / "output" / "rebrand_entrada" / "short" / clip.clip_id
        assert (clip.directory / "ready-to-post.txt").is_file()
        assert (clip.directory / "metadata.json").is_file()
        assert (clip.directory / "metadata.txt").is_file()
        assert (clip.directory / "REVIEW_PENDING").is_file()


def test_rebrand_batch_limit_processa_so_os_n_primeiros_em_ordem_alfabetica(tmp_path):
    input_dir = make_input_dir(tmp_path, ["video1.mp4", "video2.mp4", "video3.mp4"])
    ffmpeg = FfmpegSpy()
    outro_image = build_outro_image(tmp_path)
    transcriber = FakeTranscriber()
    components = build_components(tmp_path, ffmpeg)

    result = rebrand_batch(
        input_dir,
        build_kb(),
        output_root=tmp_path / "output",
        work_dir=tmp_path / "work",
        outro_image=outro_image,
        transcriber=transcriber,
        metadata_client=metadata_client(),
        limit=1,
        **components,
    )

    assert len(result.clips) == 1
    assert result.clips[0].clip_id == "video1"
    assert [path.name for path in transcriber.calls] == ["video1.mp4"]


def test_rebrand_batch_isola_falha_de_um_video_sem_travar_os_outros(tmp_path):
    input_dir = make_input_dir(tmp_path, ["video1.mp4", "video2.mp4", "video3.mp4"])
    ffmpeg = FfmpegSpy()
    outro_image = build_outro_image(tmp_path)
    transcriber = FakeTranscriber(fail_for="video2.mp4")
    components = build_components(tmp_path, ffmpeg)

    result = rebrand_batch(
        input_dir,
        build_kb(),
        output_root=tmp_path / "output",
        work_dir=tmp_path / "work",
        outro_image=outro_image,
        transcriber=transcriber,
        metadata_client=metadata_client(),
        **components,
    )

    assert {clip.clip_id for clip in result.clips} == {"video1", "video3"}
    assert len(result.failures) == 1
    assert result.failures[0].clip_id == "video2"
    assert result.failures[0].stage == "transcribe"
    assert "falha simulada" in result.failures[0].message


def test_rebrand_batch_roda_flash_periodico_entre_thumbnail_e_prepend(tmp_path):
    input_dir = make_input_dir(tmp_path, ["video1.mp4"])
    ffmpeg = FfmpegSpy()
    outro_image = build_outro_image(tmp_path)
    components = build_components(tmp_path, ffmpeg)

    rebrand_batch(
        input_dir,
        build_kb(),
        output_root=tmp_path / "output",
        work_dir=tmp_path / "work",
        outro_image=outro_image,
        transcriber=FakeTranscriber(),
        metadata_client=metadata_client(),
        **components,
    )

    output_names = [Path(command[-1]).name for command in ffmpeg.commands]
    # etapas de ffmpeg do rebrand em si (fora dos frames intermediarios da thumbnail):
    # flash periodico -> prepend da thumbnail -> outro estatico no final.
    rebrand_stage_names = [
        name for name in output_names if name in {"with_flashes.mp4", "with_thumbnail_frame.mp4", "with_outro.mp4"}
    ]
    assert rebrand_stage_names == ["with_flashes.mp4", "with_thumbnail_frame.mp4", "with_outro.mp4"]


def test_rebrand_batch_name_default_deriva_do_nome_da_pasta_de_entrada(tmp_path):
    input_dir = make_input_dir(tmp_path, ["video1.mp4"])
    ffmpeg = FfmpegSpy()
    outro_image = build_outro_image(tmp_path)
    components = build_components(tmp_path, ffmpeg)

    result = rebrand_batch(
        input_dir,
        build_kb(),
        output_root=tmp_path / "output",
        work_dir=tmp_path / "work",
        outro_image=outro_image,
        transcriber=FakeTranscriber(),
        metadata_client=metadata_client(),
        **components,
    )

    assert result.batch_folder == f"rebrand_{input_dir.name}"


def test_rebrand_batch_name_customizado_sobrepoe_o_default(tmp_path):
    input_dir = make_input_dir(tmp_path, ["video1.mp4"])
    ffmpeg = FfmpegSpy()
    outro_image = build_outro_image(tmp_path)
    components = build_components(tmp_path, ffmpeg)

    result = rebrand_batch(
        input_dir,
        build_kb(),
        output_root=tmp_path / "output",
        work_dir=tmp_path / "work",
        batch_name="lote_customizado",
        outro_image=outro_image,
        transcriber=FakeTranscriber(),
        metadata_client=metadata_client(),
        **components,
    )

    assert result.batch_folder == "lote_customizado"
    assert result.clips[0].directory == tmp_path / "output" / "lote_customizado" / "short" / "video1"
