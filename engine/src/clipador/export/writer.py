"""Organiza os artefatos ja processados de um clipe numa pasta de saida por clipe.

Nao faz encode de video: o video final ja chega pronto das etapas [5]/[6]; aqui e
so copia de arquivo e escrita do pacote de metadados.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from clipador.export.models import ClipOutput, ExportError
from clipador.metadata.models import ClipMetadata
from clipador.select.models import LONG_FORMAT, SHORT_FORMAT, ClipCandidate

VIDEO_STEM = "video"
SUBTITLES_NAME = "subtitles.ass"
THUMBNAIL_STEM = "thumbnail"
METADATA_TEXT_NAME = "metadata.txt"
METADATA_JSON_NAME = "metadata.json"
READY_TO_POST_NAME = "ready-to-post.txt"

# @ do canal, inserido entre a descricao e as hashtags no `ready-to-post.txt`. Fica aqui
# como default pra nao exigir a flag em toda execucao; `--handle` na CLI sobrescreve, e
# string vazia remove o bloco.
DEFAULT_SOCIAL_HANDLE = "renansantosmbl"

# Pasta separada por formato: um clipe longo pode reaproveitar o mesmo assunto de um
# curto (contexto diferente, formato diferente), entao o dedup de selecao so faz
# sentido DENTRO de cada pasta, nunca entre elas.
_FORMAT_SUBDIR = {SHORT_FORMAT: "short", LONG_FORMAT: "long"}


def format_subdir(clip_format: str) -> str:
    return _FORMAT_SUBDIR.get(clip_format, clip_format)


def render_metadata_text(metadata: ClipMetadata) -> str:
    """Versao legivel por humano do pacote de metadados, para a revisao editorial."""
    hashtags = " ".join(f"#{tag.lstrip('#')}" for tag in metadata.hashtags)
    references = "\n".join(f"- {ref}" for ref in metadata.kb_references) or "- (nenhuma)"
    return (
        f"TITULO\n{metadata.title}\n\n"
        f"DESCRICAO\n{metadata.description}\n\n"
        f"HASHTAGS\n{hashtags}\n\n"
        f"HEADLINE DA THUMBNAIL\n{metadata.thumbnail_headline or '(nenhuma)'}\n\n"
        f"REFERENCIAS DA BASE DE CONHECIMENTO\n{references}\n"
    )


def render_ready_to_post_text(
    title: str,
    description: str,
    hashtags: list[str],
    handle: str | None = None,
    original_video_url: str | None = None,
) -> str:
    """Conteudo pronto pra copiar e colar direto numa rede social, sem labels.

    Layout: titulo, descricao, video original (se a entrada do pipeline foi uma URL do
    YouTube), mencao do canal e hashtags, cada bloco separado por linha em branco. A linha
    em branco antes das hashtags nao e estetica: colada na descricao, a primeira hashtag e
    lida como parte da frase por quem passa o olho, e no Instagram ela entra na previa do
    feed junto com o texto.

    `handle` vazio ou None simplesmente omite o bloco de mencao, sem deixar linha solta.
    `original_video_url` None (entrada local, sem URL de origem) omite o bloco do mesmo jeito.
    """
    blocks = [title.strip(), description.strip()]
    if original_video_url and original_video_url.strip():
        blocks.append(f"Vídeo original: {original_video_url.strip()}")
    if handle and handle.strip():
        blocks.append(f"@{handle.strip().lstrip('@')}")
    tags_line = " ".join(f"#{tag.lstrip('#')}" for tag in hashtags)
    if tags_line:
        blocks.append(tags_line)
    return "\n\n".join(block for block in blocks if block) + "\n"


class ExportWriter:
    """Escreve `output_root/<output_folder>/<clip_id>/` com video, legenda, thumbnail e metadados."""

    def __init__(
        self, output_root: str | Path, handle: str | None = DEFAULT_SOCIAL_HANDLE
    ) -> None:
        self.output_root = Path(output_root)
        self.handle = handle

    def clip_dir(self, output_folder: str, clip_id: str, clip_format: str) -> Path:
        return self.output_root / output_folder / format_subdir(clip_format) / clip_id

    def write(
        self,
        video_id: str,
        clip_id: str,
        clip_format: str,
        video_path: str | Path,
        metadata: ClipMetadata | None = None,
        subtitles_path: str | Path | None = None,
        thumbnail_path: str | Path | None = None,
        candidate: ClipCandidate | None = None,
        output_folder: str | None = None,
        original_video_url: str | None = None,
    ) -> ClipOutput:
        """`output_folder` e o nome real da pasta em disco (ex.: `<video_id>_<titulo>`);
        default `video_id` quando nao informado. `ClipOutput.video_id` continua sendo o
        id cru, independente do nome da pasta."""
        source_video = Path(video_path)
        if not source_video.is_file():
            raise ExportError(f"Video final do clipe {clip_id} nao existe: {source_video}")

        directory = self.clip_dir(output_folder or video_id, clip_id, clip_format)
        directory.mkdir(parents=True, exist_ok=True)

        final_video = directory / f"{VIDEO_STEM}{source_video.suffix or '.mp4'}"
        _copy(source_video, final_video)

        final_subtitles = _copy_optional(subtitles_path, directory / SUBTITLES_NAME)
        final_thumbnail = None
        if thumbnail_path is not None:
            source_thumb = Path(thumbnail_path)
            final_thumbnail = _copy_optional(
                source_thumb, directory / f"{THUMBNAIL_STEM}{source_thumb.suffix or '.png'}"
            )

        output = ClipOutput(
            clip_id=clip_id,
            video_id=video_id,
            format=clip_format,
            directory=directory,
            video_path=final_video,
            subtitles_path=final_subtitles,
            thumbnail_path=final_thumbnail,
            metadata=metadata,
        )

        if metadata is not None:
            metadata_path = directory / METADATA_TEXT_NAME
            metadata_path.write_text(render_metadata_text(metadata), encoding="utf-8")
            output.metadata_path = metadata_path

            ready_to_post_path = directory / READY_TO_POST_NAME
            ready_to_post_path.write_text(
                render_ready_to_post_text(
                    metadata.title,
                    metadata.description,
                    metadata.hashtags,
                    handle=self.handle,
                    original_video_url=original_video_url,
                ),
                encoding="utf-8",
            )
            output.extra["ready_to_post_path"] = str(ready_to_post_path)

        payload = output.to_dict()
        if candidate is not None:
            payload["candidate"] = candidate.to_dict()
        (directory / METADATA_JSON_NAME).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return output


def _copy(source: Path, target: Path) -> Path:
    if source.resolve() != target.resolve():
        shutil.copy2(source, target)
    return target


def _copy_optional(source: str | Path | None, target: Path) -> Path | None:
    if source is None:
        return None
    source_path = Path(source)
    if not source_path.is_file():
        raise ExportError(f"Artefato esperado nao existe: {source_path}")
    return _copy(source_path, target)
