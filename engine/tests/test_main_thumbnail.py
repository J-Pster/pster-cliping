"""Testes de `generate_main_video_thumbnail`: TODAS as dependencias pesadas sao fakes,
100% offline. Mesmo padrao de `test_rebrand_service.py` (FfmpegSpy + IFrameExtractor +
FakeFrameSaver), sem composer (equivalente a --no-thumbnail-composition), ja que o
composer/gerador de IA por categoria ja tem cobertura propria em test_thumbnail_ai.py."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from clipador.category import BOOK_AUDIOBOOK, GAMING, POLITICS_PERSON
from clipador.kb.knowledge import KnowledgeBase, KnowledgeDocument
from clipador.main_thumbnail import build_main_video_candidate, generate_main_video_thumbnail
from clipador.select.models import LONG_FORMAT
from clipador.thumbnail.builder import ThumbnailBuilder
from clipador.thumbnail.extractor import IFrameExtractor
from clipador.transcribe.models import Segment, TranscriptionResult, Word


def build_kb() -> KnowledgeBase:
    return KnowledgeBase(
        movement="Movimento Exemplo",
        core=[KnowledgeDocument(name="pautas", title="Pautas", content="Pauta de exemplo.")],
        topics_dir=None,
    )


def build_transcription(word_count: int = 10) -> TranscriptionResult:
    words = [
        Word(id=index, text=f"palavra{index}", start=float(index), end=float(index) + 0.8)
        for index in range(word_count)
    ]
    segment = Segment(
        id=0, start=words[0].start, end=words[-1].end, text=" ".join(w.text for w in words), words=words
    )
    return TranscriptionResult(segments=[segment], language="pt", duration=words[-1].end)


class FakeTranscriber:
    def __init__(self, transcription: TranscriptionResult | None = None):
        self.transcription = transcription or build_transcription()
        self.calls: list[Path] = []

    def transcribe(self, video_path):
        self.calls.append(Path(video_path))
        return self.transcription


class FakeToolUseBlock:
    def __init__(self, name: str, payload: dict):
        self.type = "tool_use"
        self.name = name
        self.input = payload


class FakeResponse:
    def __init__(self, content: list):
        self.content = content


class FakeMessages:
    def __init__(self, response):
        self._response = response
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._response


class FakeClient:
    def __init__(self, response):
        self.messages = FakeMessages(response)


def metadata_client(**overrides) -> FakeClient:
    payload = {
        "title": "Titulo do video principal",
        "description": "Descricao do video principal gerada pelo LLM.",
        "hashtags": ["politica", "corte"],
        "kb_references": ["Pauta de exemplo"],
        "thumbnail_headline": "TITULO DA THUMB",
    }
    payload.update(overrides)
    return FakeClient(FakeResponse([FakeToolUseBlock("propose_metadata", payload)]))


class FfmpegSpy:
    def __init__(self):
        self.commands: list[list[str]] = []

    def __call__(self, command, **kwargs):
        self.commands.append(list(command))
        target = Path(command[-1])
        target.parent.mkdir(parents=True, exist_ok=True)
        if "%" in target.name:
            (target.parent / (target.name % 1)).write_bytes(b"frame")
        else:
            target.write_bytes(b"media")
        return SimpleNamespace(returncode=0)


class FakeFrameSaver:
    def __init__(self):
        self.calls: list[tuple[Path, Path]] = []

    def __call__(self, frame_path, output_path):
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"fake png")
        self.calls.append((Path(frame_path), output_path))


def build_thumbnail_builder(ffmpeg: FfmpegSpy) -> ThumbnailBuilder:
    return ThumbnailBuilder(
        extractor=IFrameExtractor(runner=ffmpeg),
        sharpness_scorer=SimpleNamespace(score=lambda frame: 1.0),
        face_scorer=SimpleNamespace(score=lambda frame: 0.5),
        save_frame=FakeFrameSaver(),
        frame_loader=lambda path: SimpleNamespace(path=path),
    )


# --- build_main_video_candidate ---------------------------------------------


def test_build_main_video_candidate_cobre_o_video_inteiro():
    transcription = build_transcription(word_count=5)

    candidate = build_main_video_candidate(transcription)

    assert candidate.format == LONG_FORMAT
    assert candidate.start_word_id == 0
    assert candidate.end_word_id == 4
    assert candidate.start == 0.0
    assert candidate.end == transcription.duration


def test_build_main_video_candidate_rejeita_transcricao_vazia():
    vazio = TranscriptionResult(segments=[], language="pt", duration=0.0)

    with pytest.raises(ValueError):
        build_main_video_candidate(vazio)


# --- generate_main_video_thumbnail ------------------------------------------


def test_generate_main_video_thumbnail_gera_todos_os_artefatos(tmp_path):
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"video de entrada")
    ffmpeg = FfmpegSpy()

    result = generate_main_video_thumbnail(
        video_path,
        build_kb(),
        tmp_path / "saida",
        category=POLITICS_PERSON,
        transcription=build_transcription(),
        metadata_client=metadata_client(),
        thumbnail_builder=build_thumbnail_builder(ffmpeg),
    )

    assert result.thumbnail_path.is_file()
    assert result.metadata_path.is_file()
    assert result.ready_to_post_path.is_file()
    assert (tmp_path / "saida" / "metadata.json").is_file()
    assert result.metadata.title == "Titulo do video principal"
    assert result.metadata.thumbnail_headline == "TITULO DA THUMB"
    assert "Titulo do video principal" in result.ready_to_post_path.read_text(encoding="utf-8")


def test_generate_main_video_thumbnail_reaproveita_transcricao_ja_pronta(tmp_path):
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"video de entrada")
    transcriber = FakeTranscriber()

    generate_main_video_thumbnail(
        video_path,
        build_kb(),
        tmp_path / "saida",
        category=POLITICS_PERSON,
        transcription=build_transcription(),
        transcriber=transcriber,
        metadata_client=metadata_client(),
        thumbnail_builder=build_thumbnail_builder(FfmpegSpy()),
    )

    assert transcriber.calls == []


def test_generate_main_video_thumbnail_transcreve_quando_nao_fornecida(tmp_path):
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"video de entrada")
    transcriber = FakeTranscriber()

    generate_main_video_thumbnail(
        video_path,
        build_kb(),
        tmp_path / "saida",
        category=POLITICS_PERSON,
        transcriber=transcriber,
        metadata_client=metadata_client(),
        thumbnail_builder=build_thumbnail_builder(FfmpegSpy()),
    )

    assert transcriber.calls == [video_path]


@pytest.mark.parametrize("category", [POLITICS_PERSON, GAMING, BOOK_AUDIOBOOK])
def test_generate_main_video_thumbnail_funciona_nas_tres_categorias(tmp_path, category):
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"video de entrada")

    result = generate_main_video_thumbnail(
        video_path,
        build_kb(),
        tmp_path / "saida" / category,
        category=category,
        transcription=build_transcription(),
        metadata_client=metadata_client(),
        thumbnail_builder=build_thumbnail_builder(FfmpegSpy()),
    )

    assert result.thumbnail_path.is_file()


def test_generate_main_video_thumbnail_rejeita_categoria_invalida(tmp_path):
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"video de entrada")

    with pytest.raises(ValueError):
        generate_main_video_thumbnail(
            video_path,
            build_kb(),
            tmp_path / "saida",
            category="categoria-que-nao-existe",
            transcription=build_transcription(),
            metadata_client=metadata_client(),
            thumbnail_builder=build_thumbnail_builder(FfmpegSpy()),
        )
