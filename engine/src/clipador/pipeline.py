"""Orquestrador ponta a ponta das 10 etapas do plano.

Ingest -> download -> transcricao -> selecao por LLM -> (por clipe) reenquadramento ->
legendas -> metadados -> thumbnail -> export na pasta de revisao editorial.

Para o formato curto (vertical), ha uma etapa extra entre thumbnail e export: a
thumbnail escolhida e prendida como o primeiro frame literal do video final (ver
`clipador.export.thumbnail_frame`), pra bater com a previa automatica que varias
plataformas mostram quando nenhuma thumbnail custom e setada via API.

Todo componente pesado e injetavel; o default so e construido quando nada foi passado,
entao o pipeline inteiro roda offline nos testes.
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable

from clipador import category as category_module
from clipador.download.downloader import Downloader, YtDlpDownloader
from clipador.export.cutter import ClipCutter
from clipador.export.models import ClipOutput
from clipador.export.review import ReviewQueue
from clipador.export.thumbnail_frame import ThumbnailFramePrepender
from clipador.export.watermark import WatermarkImages, WatermarkOverlay
from clipador.export.writer import DEFAULT_SOCIAL_HANDLE, ExportWriter
from clipador.ingest.source import IngestSource, resolve_source
from clipador.kb.knowledge import KnowledgeBase
from clipador.main_thumbnail import MainVideoThumbnailResult, generate_main_video_thumbnail
from clipador.metadata.generator import generate_metadata
from clipador.metadata.models import ClipMetadata
from clipador.reframe.faces import MediaPipeFaceDetector
from clipador.reframe.reframer import VerticalReframer
from clipador.select.manifest import load_manifest, save_manifest
from clipador.select.models import LONG_FORMAT, SHORT_FORMAT, ClipCandidate
from clipador.select.selector import select_clips_for_targets
from clipador.thumbnail.subject import select_thumbnail_subject
from clipador.subtitles.builder import AssSubtitleBuilder
from clipador.subtitles.burn import burn_in, save_ass
from clipador.subtitles.emphasis import select_emphasis_word_ids
from clipador.subtitles.fonts import BUNDLED_FONTS, DEFAULT_FONTS_DIR
from clipador.subtitles.models import SubtitleStyle
from clipador.subtitles.presets import DEFAULT_PRESET, build_subtitle_style
from clipador.thumbnail.ai_thumbnail import build_thumbnail_generator
from clipador.thumbnail.background import build_background_editor
from clipador.thumbnail.builder import ThumbnailBuilder
from clipador.thumbnail.composer import ThumbnailComposer, ThumbnailStyle
from clipador.thumbnail.cutout import PersonCutout
from clipador.thumbnail.face_quality import FaceQualityScorer
from clipador.transcribe.factory import TranscriberSettings, build_transcriber
from clipador.transcribe.models import (
    TranscriptionResult,
    Word,
    load_cached_transcription,
    save_transcription,
)
from clipador.transcribe.vocabulary import build_vocabulary

logger = logging.getLogger(__name__)

VERTICAL_FORMATS = (SHORT_FORMAT,)
# Categorias cujo conteudo e sobre figuras publicas reais (politica) - so nelas vale
# gastar a chamada de `select_thumbnail_subject`. Jogos nao tem figura publica pra
# escolher, e o dossie/biblioteca de rostos e sempre de politico brasileiro.
THUMBNAIL_SUBJECT_CATEGORIES = (category_module.POLITICS_PERSON, category_module.BOOK_AUDIOBOOK)


class PipelineError(RuntimeError):
    pass


class ClipStageError(RuntimeError):
    """Falha de UM clipe numa etapa especifica; nao derruba os demais clipes."""

    def __init__(self, stage: str, message: str) -> None:
        super().__init__(f"{stage}: {message}")
        self.stage = stage
        self.message = message


@dataclass
class ClipFailure:
    clip_id: str
    stage: str
    message: str


@dataclass
class PipelineConfig:
    output_root: Path
    work_dir: Path
    # Marca d'agua do canal por formato, ou None pra nao aplicar nenhuma. Obrigatorio e
    # SEM default de proposito: estampar ou nao a marca e decisao editorial de cada
    # rodada, e um default silencioso aqui gravaria (ou deixaria de gravar) branding em
    # todo clipe sem ninguem ter escolhido. A CLI exige `--watermark on|off`.
    # `WatermarkImages` so existe se os dois PNGs existirem, entao aqui nao ha mais o que
    # validar: ou e None, ou e um par de caminhos ja conferidos.
    watermark: WatermarkImages | None
    # Meta de "melhor esforco" por formato: tenta gerar pelo menos N NOVOS clipes de
    # cada, reconvocando a selecao (excluindo o que ja foi usado, ver `select.manifest`)
    # ate atingir a meta ou desistir (`max_selection_attempts`/2 rodadas sem novidade) -
    # nem todo video tem material pra 5 longos de 8-12min cada, por exemplo.
    min_short_clips: int = 5
    min_long_clips: int = 5
    max_selection_attempts: int = 4
    # Look da legenda por nome (ver clipador.subtitles.presets). O preset resolve fonte,
    # paleta, caixa alta e modo de animacao; a geometria (PlayRes, margens, tamanho
    # relativo da fonte) vem do FORMATO do clipe, nao do preset.
    subtitle_preset: str = DEFAULT_PRESET
    # Diretorio das fontes embarcadas, repassado ao libass via `fontsdir`. Sem ele o
    # libass cai numa fonte generica em silencio quando a fonte do estilo nao esta
    # instalada na maquina.
    subtitle_fonts_dir: Path = DEFAULT_FONTS_DIR
    # None = derivar do preset em `__post_init__`. Passar um `SubtitleStyle` pronto
    # continua valendo pra ajuste fino, e nesse caso nada aqui sobrescreve o que veio.
    subtitle_style: SubtitleStyle | None = None
    subtitle_style_long: SubtitleStyle | None = None
    # Enfase semantica: uma chamada de LLM POR CLIPE marca as palavras-chave que ganham
    # cor propria na legenda (ver clipador.subtitles.emphasis). Desligada por padrao
    # porque custa uma chamada a mais por clipe, alem da de metadados.
    subtitle_emphasis: bool = False
    # None = usa a caixa definida pelo preset. True/False sobrescreve nos dois formatos,
    # pra comparar caixa alta e caixa mista sem trocar de preset.
    subtitle_uppercase: bool | None = None
    # @ do canal escrito no `ready-to-post.txt`, entre a descricao e as hashtags.
    # String vazia remove o bloco.
    social_handle: str = DEFAULT_SOCIAL_HANDLE
    # Backend de transcricao e seus parametros. O default (WhisperX large-v3) e o que
    # sustenta o karaoke da legenda: ver clipador.transcribe.factory.
    transcriber: TranscriberSettings = field(default_factory=TranscriberSettings)
    # Rede de seguranca contra o LLM da selecao ignorar a janela de duracao do prompt
    # (ex.: rotular um clipe de 1:30 como long_16x9, que exige 8-12min), descarta
    # candidatos fora da janela do proprio formato em vez de exportar errado.
    enforce_duration_bounds: bool = True
    # Respiro antes/depois do corte, comido do silencio que o snap_to_silence
    # da selecao ja garante existir ali (gap minimo de 300ms por padrao) -
    # bem abaixo disso pra nunca invadir fala adjacente.
    context_pad_seconds: float = 0.08
    # Thumbnail composta (fundo tratado + recorte da pessoa + headline + destaque) em vez
    # do frame cru. Cada peca tem fallback proprio, entao ligar isso nao exige rembg,
    # chave do Gemini nem modelo de rosto instalados.
    enable_thumbnail_composition: bool = True
    # Nome do navegador local logado ("firefox", "chrome", "edge", ...) pra ler cookies
    # de sessao e evitar o 403 do YouTube em downloads de video+audio separados. Ver
    # docstring de YtDlpDownloader.
    cookies_from_browser: str | None = None
    # Caminho do blaze_face_short_range.tflite exigido por MediaPipeFaceDetector (reframe
    # do formato curto e recorte de rosto da thumbnail). Sem ele, reframe falha pra
    # TODO clipe curto (ver MediaPipeFaceDetector._detect).
    face_model_path: Path | None = Path("models/blaze_face_short_range.tflite")
    # Categoria de conteudo-fonte (politico/pessoa, jogos, livro/audiobook) - muda os
    # prompts de selecao, re-rank, metadados e thumbnail (ver clipador.category). A CLI
    # sempre passa isto explicito (`--category`); o default aqui so existe pra quem
    # constroi PipelineConfig direto (testes, uso programatico) sem se importar com
    # categoria.
    category: str = category_module.DEFAULT_CATEGORY
    # Desligado por padrao: gera tambem a thumbnail (+ titulo/descricao/hashtags) do VIDEO
    # PRINCIPAL inteiro, alem dos cortes (ver clipador.main_thumbnail) - util quando o
    # usuario tambem vai postar a gravacao/live completa, nao so os clipes. Reaproveita a
    # transcricao ja feita pros cortes, nao transcreve de novo.
    generate_main_thumbnail: bool = False

    def __post_init__(self) -> None:
        category_module.validate_category(self.category)
        self.output_root = Path(self.output_root)
        self.work_dir = Path(self.work_dir)
        self.subtitle_fonts_dir = Path(self.subtitle_fonts_dir)
        overrides: dict[str, object] = {"fonts_dir": self.subtitle_fonts_dir}
        if self.subtitle_uppercase is not None:
            overrides["uppercase"] = self.subtitle_uppercase
        if self.subtitle_style is None:
            self.subtitle_style = replace(
                build_subtitle_style(self.subtitle_preset, SHORT_FORMAT), **overrides
            )
        if self.subtitle_style_long is None:
            self.subtitle_style_long = replace(
                build_subtitle_style(self.subtitle_preset, LONG_FORMAT), **overrides
            )

    def style_for(self, clip_format: str) -> SubtitleStyle:
        style = self.subtitle_style if clip_format in VERTICAL_FORMATS else self.subtitle_style_long
        assert style is not None  # garantido por __post_init__
        return style


@dataclass
class PipelineResult:
    source: IngestSource
    video_path: Path
    video_id: str
    transcription: TranscriptionResult
    candidates: list[ClipCandidate]
    clips: list[ClipOutput] = field(default_factory=list)
    failures: list[ClipFailure] = field(default_factory=list)
    main_thumbnail: MainVideoThumbnailResult | None = None


def clip_words(
    transcription: TranscriptionResult,
    start_word_id: int,
    end_word_id: int,
    offset: float = 0.0,
) -> list[Word]:
    """Palavras do trecho com os tempos rebaseados para o inicio do clipe cortado."""
    return [
        Word(
            id=word.id,
            text=word.text,
            start=max(0.0, word.start - offset),
            end=max(0.0, word.end - offset),
            speaker=word.speaker,
        )
        for word in transcription.words
        if start_word_id <= word.id <= end_word_id
    ]


def clip_excerpt(transcription: TranscriptionResult, start_word_id: int, end_word_id: int) -> str:
    return " ".join(
        word.text for word in transcription.words if start_word_id <= word.id <= end_word_id
    )


def _run(stage: str, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    try:
        return fn(*args, **kwargs)
    except Exception as exc:
        raise ClipStageError(stage, str(exc)) from exc


def _title_from_sidecar_info_json(video_path: Path) -> str | None:
    """Le o titulo de um `<video>.info.json` (convencao do yt-dlp) ao lado do arquivo -
    existe quando o arquivo local veio de um download anterior (`write_info_json=True`
    por padrao), mesmo que a ingestao atual seja so o caminho local sem baixar de novo."""
    info_json_path = video_path.with_suffix(".info.json")
    if not info_json_path.is_file():
        return None
    try:
        data = json.loads(info_json_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    title = data.get("title")
    return str(title) if title else None


_SLUG_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_SLUG_WHITESPACE = re.compile(r"\s+")
_SLUG_REPEATED_UNDERSCORE = re.compile(r"_+")
MAX_TITLE_SLUG_LENGTH = 60


def slugify_title(title: str) -> str:
    """Formata o titulo do video pra virar parte segura de nome de pasta no Windows:
    reduz a ASCII puro (acento cai pra letra base, ex. "não" pra "nao"; o resto, como
    travessao ou emoji, e descartado), remove caracteres proibidos (`<>:"/\\|?*`),
    colapsa espaco em `_` e trunca. Caractere nao-ASCII sobrevivendo aqui e fonte de
    bug de encoding em outras ferramentas que leem o caminho depois (ver P2.3)."""
    ascii_only = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode("ascii")
    cleaned = _SLUG_INVALID_CHARS.sub("", ascii_only)
    cleaned = _SLUG_WHITESPACE.sub("_", cleaned.strip())
    cleaned = _SLUG_REPEATED_UNDERSCORE.sub("_", cleaned)
    cleaned = cleaned.strip("._ ")
    return cleaned[:MAX_TITLE_SLUG_LENGTH].strip("._ ")


def build_output_folder_name(video_id: str, title: str | None) -> str:
    """`<video_id>_<titulo-formatado>`, ou so `video_id` quando o titulo nao esta
    disponivel (ex.: arquivo local sem `.info.json` ao lado)."""
    slug = slugify_title(title) if title else ""
    return f"{video_id}_{slug}" if slug else video_id


def _original_video_url(source: IngestSource, video_id: str) -> str | None:
    """URL do video original pro bloco "Video original" do ready-to-post.txt. So existe
    quando a entrada do pipeline foi mesmo uma URL do YouTube (entrada local nao tem
    origem publica pra linkar)."""
    return f"https://youtu.be/{video_id}" if source.needs_download else None


def _resolve_video(source: IngestSource, downloader: Downloader) -> tuple[Path, str, str | None]:
    if not source.needs_download:
        path = source.path
        if path is None or not path.is_file():
            raise PipelineError(f"Arquivo local inexistente: {source.value}")
        return path, path.stem, _title_from_sidecar_info_json(path)

    result = downloader.download(source.value)
    video_id = result.video_id or source.video_id or "video"
    title = result.info.get("title")
    return Path(result.video_path), video_id, str(title) if title else None


def _default_thumbnail_builder(config: PipelineConfig) -> ThumbnailBuilder:
    face_scorer = FaceQualityScorer(
        face_detector=MediaPipeFaceDetector(model_path=config.face_model_path)
    )
    if not config.enable_thumbnail_composition:
        return ThumbnailBuilder(face_scorer=face_scorer)
    composer = ThumbnailComposer(
        cutout=PersonCutout(),
        background_editor=build_background_editor(config.category),
        face_detector=MediaPipeFaceDetector(model_path=config.face_model_path),
        ai_generator=build_thumbnail_generator(config.category),
        # Sem isto, o fallback em camadas (ver ThumbnailComposer, so roda quando a
        # geracao via Gemini falhar - cota estourada, erro 429, etc.) caia pra fonte
        # bitmap default do Pillow, que nao tem glifo pra acento (Ê, Ã, Õ saiam como
        # um quadrado): mesma fonte embarcada usada na legenda, com cobertura completa
        # de acentuacao do PT-BR.
        style=ThumbnailStyle(
            font_path=config.subtitle_fonts_dir / BUNDLED_FONTS["Montserrat ExtraBold"]
        ),
    )
    return ThumbnailBuilder(composer=composer, face_scorer=face_scorer)


def _process_candidate(
    clip_id: str,
    candidate: ClipCandidate,
    transcription: TranscriptionResult,
    kb: KnowledgeBase,
    config: PipelineConfig,
    video_path: Path,
    video_id: str,
    output_folder: str,
    original_video_url: str | None,
    cutter: ClipCutter,
    reframer: VerticalReframer,
    subtitle_builder: AssSubtitleBuilder,
    burner: Callable[..., Any],
    thumbnail_builder: ThumbnailBuilder,
    thumbnail_frame_prepender: ThumbnailFramePrepender,
    watermark_overlay: WatermarkOverlay,
    metadata_client: Any | None,
    writer: ExportWriter,
    review_queue: ReviewQueue,
) -> ClipOutput:
    stage_dir = config.work_dir / video_id / clip_id
    stage_dir.mkdir(parents=True, exist_ok=True)

    current = _run(
        "cut",
        cutter.cut,
        video_path,
        stage_dir / "cut.mp4",
        candidate.start,
        candidate.end,
        pad_seconds=config.context_pad_seconds,
    )

    if candidate.format in VERTICAL_FORMATS:
        current = _run(
            "reframe", reframer.reframe, current, stage_dir / "reframed.mp4"
        ).output_path

    words = clip_words(
        transcription, candidate.start_word_id, candidate.end_word_id, candidate.start
    )
    ass_path = stage_dir / "subtitles.ass"
    burned = stage_dir / "burned.mp4"
    subtitle_style = config.style_for(candidate.format)
    emphasis_word_ids: frozenset[int] = frozenset()
    if config.subtitle_emphasis:
        emphasis_word_ids = _run(
            "subtitles", select_emphasis_word_ids, words, metadata_client
        )
    ass_content = _run(
        "subtitles", subtitle_builder.build, words, subtitle_style, emphasis_word_ids
    )
    _run("subtitles", save_ass, ass_content, ass_path)
    _run("subtitles", burner, current, ass_path, burned, fonts_dir=subtitle_style.fonts_dir)
    # Os candidatos a thumbnail saem do video ANTES do burn-in: extrair do `burned`
    # colocaria a legenda karaoke dentro da imagem da thumbnail.
    pre_subtitle_video = current
    current = burned

    # A marca d'agua entra depois do burn-in e ANTES de prender a thumbnail como 1o
    # frame: ela cobre o video, nao o frame de capa. A capa ja carrega a identidade do
    # canal, e branding pesado no primeiro frame aumenta a taxa de skip.
    if config.watermark is not None:
        current = _run(
            "watermark",
            watermark_overlay.apply,
            current,
            config.watermark.path_for(candidate.format),
            stage_dir / "watermarked.mp4",
        )

    transcript_excerpt = clip_excerpt(transcription, candidate.start_word_id, candidate.end_word_id)
    metadata: ClipMetadata = _run(
        "metadata",
        generate_metadata,
        candidate,
        transcript_excerpt,
        kb,
        metadata_client,
        category=config.category,
    )

    # Escolha do "assunto" da thumbnail (qual figura publica cadastrada, se alguma, e o
    # tema deste trecho) e sub-etapa OPCIONAL como as demais da composicao: uma falha
    # aqui nao pode derrubar um clipe que, sem referencia facial nenhuma, ainda sai
    # correto (so cai pro comportamento de sempre, sem identidade ancorada).
    subject = None
    if config.category in THUMBNAIL_SUBJECT_CATEGORIES:
        try:
            subject = select_thumbnail_subject(candidate, transcript_excerpt, metadata_client)
        except Exception as exc:
            logger.warning(
                "Selecao do assunto da thumbnail falhou (%s); seguindo sem referencia facial.",
                exc,
            )

    thumbnail_path = _run(
        "thumbnail",
        thumbnail_builder.build,
        pre_subtitle_video,
        stage_dir / "thumbnail.png",
        stage_dir / "frames",
        headline=metadata.thumbnail_headline,
        subject=subject,
    )

    if candidate.format in VERTICAL_FORMATS:
        current = _run(
            "thumbnail_frame",
            thumbnail_frame_prepender.prepend,
            current,
            thumbnail_path,
            stage_dir / "with_thumbnail_frame.mp4",
        )

    output = _run(
        "export",
        writer.write,
        video_id,
        clip_id,
        candidate.format,
        current,
        metadata,
        ass_path,
        thumbnail_path,
        candidate,
        output_folder,
        original_video_url,
    )
    return _run("review", review_queue.enqueue, output)


def run_pipeline(
    input_source: str | Path,
    kb: KnowledgeBase,
    config: PipelineConfig,
    *,
    downloader: Downloader | None = None,
    transcriber: Any | None = None,
    selector_client: Any | None = None,
    metadata_client: Any | None = None,
    cutter: ClipCutter | None = None,
    reframer: VerticalReframer | None = None,
    subtitle_builder: AssSubtitleBuilder | None = None,
    burner: Callable[..., Any] | None = None,
    thumbnail_builder: ThumbnailBuilder | None = None,
    thumbnail_frame_prepender: ThumbnailFramePrepender | None = None,
    watermark_overlay: WatermarkOverlay | None = None,
    writer: ExportWriter | None = None,
    review_queue: ReviewQueue | None = None,
) -> PipelineResult:
    config.work_dir.mkdir(parents=True, exist_ok=True)
    config.output_root.mkdir(parents=True, exist_ok=True)

    source = resolve_source(input_source)
    video_path, video_id, video_title = _resolve_video(
        source,
        downloader
        or YtDlpDownloader(
            config.work_dir / "download", cookies_from_browser=config.cookies_from_browser
        ),
    )
    # Pasta de output legivel: <video_id>_<titulo-formatado> em vez de so o id cru. O
    # cache de transcricao (work_dir) continua chaveado so no video_id, estavel mesmo
    # se o titulo nao estiver disponivel na primeira passada.
    output_folder = build_output_folder_name(video_id, video_title)
    logger.info("Pasta de saida: %s", output_folder)
    original_video_url = _original_video_url(source, video_id)

    # Transcricao e a etapa mais cara do pipeline (minutos, mesmo em GPU) - reaproveita
    # do cache em vez de refazer a cada "gerar mais" clipes do mesmo video.
    transcription_cache_path = config.work_dir / video_id / "transcription.json"
    cached = load_cached_transcription(transcription_cache_path)
    if cached is not None:
        transcription = cached
        logger.info("Transcricao reaproveitada do cache: %s", transcription_cache_path)
    else:
        # O vocabulario da KB da categoria condiciona o ASR nos nomes e siglas do dominio,
        # que e onde o Whisper mais erra (ver clipador.transcribe.vocabulary).
        transcription = (
            transcriber
            or build_transcriber(config.transcriber, vocabulary=build_vocabulary(kb))
        ).transcribe(video_path)
        save_transcription(transcription, transcription_cache_path)

    # Manifesto: trechos ja usados por formato (curto/longo sao listas separadas - o
    # mesmo assunto pode virar um clipe de cada, so nao duas vezes no mesmo formato) e o
    # proximo indice de clip_id por formato, pra "gerar mais" continuar a numeracao sem
    # sobrescrever pasta ja exportada. Vive dentro da mesma pasta de output dos clipes.
    manifest_path = config.output_root / output_folder / "manifest.json"
    manifest = load_manifest(manifest_path)

    targets = {SHORT_FORMAT: config.min_short_clips, LONG_FORMAT: config.min_long_clips}
    collected = select_clips_for_targets(
        transcription,
        kb,
        targets,
        client=selector_client,
        used_ranges=manifest.used_ranges,
        enforce_duration_bounds=config.enforce_duration_bounds,
        max_attempts=config.max_selection_attempts,
        category=config.category,
    )
    for clip_format, found in collected.items():
        if len(found) < targets[clip_format]:
            logger.warning(
                "Meta de %s nao atingida: %d/%d novos candidatos validos (video pode nao "
                "ter material suficiente sem repetir contexto).",
                clip_format,
                len(found),
                targets[clip_format],
            )
    candidates = [*collected[SHORT_FORMAT], *collected[LONG_FORMAT]]

    # Score na frente do nome: ordenacao alfabetica de pasta (Windows Explorer etc.) vira
    # ordenacao por pontuacao de graca, sem precisar de ferramenta nenhuma pra isso.
    # Fica crescente (pior primeiro) - MAX_SCORE-score inverteria pra melhor primeiro.
    clip_plan: list[tuple[str, ClipCandidate]] = []
    for candidate in candidates:
        index = manifest.allocate_index(candidate.format)
        clip_plan.append(
            (f"{candidate.score:02d}_clip_{index:02d}_{candidate.format}", candidate)
        )
    # So o indice (pra nome de pasta estavel) e reservado aqui. O trecho vira "usado" -
    # e sai da lista que a proxima selecao evita repetir - so depois que o clipe exportar
    # com sucesso (ver o `manifest.mark_used` dentro do loop abaixo): reservar antes faria
    # um clipe que falhou numa etapa (ex.: LLM de metadados recusando o schema) queimar o
    # trecho pra sempre sem nunca ter virado clipe.
    save_manifest(manifest, manifest_path)

    result = PipelineResult(
        source=source,
        video_path=video_path,
        video_id=video_id,
        transcription=transcription,
        candidates=candidates,
    )

    cutter = cutter or ClipCutter()
    reframer = reframer or VerticalReframer(
        face_detector=MediaPipeFaceDetector(model_path=config.face_model_path)
    )
    subtitle_builder = subtitle_builder or AssSubtitleBuilder(config.subtitle_style)
    burner = burner or burn_in
    thumbnail_builder = thumbnail_builder or _default_thumbnail_builder(config)
    thumbnail_frame_prepender = thumbnail_frame_prepender or ThumbnailFramePrepender()
    watermark_overlay = watermark_overlay or WatermarkOverlay()
    writer = writer or ExportWriter(config.output_root, handle=config.social_handle)
    review_queue = review_queue or ReviewQueue()

    for clip_id, candidate in clip_plan:
        try:
            result.clips.append(
                _process_candidate(
                    clip_id,
                    candidate,
                    transcription,
                    kb,
                    config,
                    video_path,
                    video_id,
                    output_folder,
                    original_video_url,
                    cutter,
                    reframer,
                    subtitle_builder,
                    burner,
                    thumbnail_builder,
                    thumbnail_frame_prepender,
                    watermark_overlay,
                    metadata_client,
                    writer,
                    review_queue,
                )
            )
            # So marca o trecho como usado (exclui de selecoes futuras) DEPOIS do
            # export ter dado certo - ver o comentario acima de onde os indices
            # sao alocados. Salva a cada sucesso pra sobreviver a um crash no meio
            # do loop sem perder o que ja foi exportado de verdade.
            manifest.mark_used(candidate.format, candidate.start_word_id, candidate.end_word_id)
            save_manifest(manifest, manifest_path)
        except ClipStageError as exc:
            logger.warning("Clipe %s falhou na etapa %s: %s", clip_id, exc.stage, exc.message)
            result.failures.append(ClipFailure(clip_id, exc.stage, exc.message))

    if config.generate_main_thumbnail:
        try:
            result.main_thumbnail = generate_main_video_thumbnail(
                video_path,
                kb,
                config.output_root / output_folder / "video_principal",
                category=config.category,
                transcription=transcription,
                metadata_client=metadata_client,
                # Reaproveita o mesmo thumbnail_builder ja construido pros clipes (mesma
                # categoria, mesmo face_model_path) em vez de montar um novo do zero.
                thumbnail_builder=thumbnail_builder,
                face_model_path=config.face_model_path,
            )
        except Exception as exc:
            logger.warning("Thumbnail do video principal falhou (%s); video segue sem ela.", exc)

    return result
