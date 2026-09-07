"""Publicacao de clipes via Buffer (https://buffer.com), intermediario unico
para YouTube, Instagram e TikTok.

Fluxo: expor o clipe numa URL publica temporaria via servidor HTTP local +
tunel ngrok (local_tunnel) -> cria o post no Buffer em modo `addToQueue`
(unico modo testado onde o `text`/legenda realmente fica salvo no post -
`shareNow` e `customScheduled` na CRIACAO descartam o texto quando ha um
asset de video, confirmado repetidas vezes na pratica) -> edita esse mesmo
post pra `mode: shareNow` via `editPost` (dispara o envio imediato sem
perder o texto ja salvo) -> aguarda o status virar `sent` (polling) ->
derruba o servidor e o tunel.

Resolucao de canal por grupo (conta Buffer conectada) + plataforma e feita por
env var explicita, nunca por match textual do campo `service` retornado pela
API (o enum de `service` nao e documentado de forma confiavel o suficiente pra
adivinhar).
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

from clipador.publish.buffer_client import graphql_request
from clipador.publish.models import (
    ALL_GROUPS,
    ALL_PLATFORMS,
    PLATFORM_INSTAGRAM,
    PLATFORM_YOUTUBE,
    PublishError,
    PublishResult,
)
from clipador.publish.local_tunnel import delete_staged, stage_video

# Nomes de campo confirmados via introspection GraphQL contra a API real do Buffer
# (`__type(name: ...)`), NAO pela documentacao escrita (guides/reference.html tem
# exemplos incompletos e um enum de PostStatus desatualizado/errado - ver historico).
MAX_YOUTUBE_TITLE_LENGTH = 100

CONTAINER_POLL_INTERVAL_SECONDS = 5
CONTAINER_POLL_TIMEOUT_SECONDS = 600

_ORGANIZATIONS_QUERY = "query { account { organizations { id } } }"

_CHANNELS_QUERY = """
query($organizationId: OrganizationId!) {
  channels(input: { organizationId: $organizationId }) {
    id
    name
    service
  }
}
"""

_CREATE_POST_MUTATION = """
mutation($channelId: ChannelId!, $text: String!, $videoUrl: String!, $metadata: PostInputMetaData) {
  createPost(input: {
    text: $text
    channelId: $channelId
    schedulingType: automatic
    mode: addToQueue
    needsApproval: false
    assets: [{ video: { url: $videoUrl } }]
    metadata: $metadata
  }) {
    ... on PostActionSuccess { post { id text status } }
    ... on MutationError { message }
  }
}
"""

_EDIT_POST_MUTATION = """
mutation($id: PostId!) {
  editPost(input: { id: $id, mode: shareNow }) {
    ... on PostActionSuccess { post { id text status } }
    ... on MutationError { message }
  }
}
"""

_POST_STATUS_QUERY = """
query($id: PostId!) {
  post(input: { id: $id }) {
    id
    status
    dueAt
    sentAt
    error { message rawError }
  }
}
"""


def get_organization_id() -> str:
    data = graphql_request(_ORGANIZATIONS_QUERY)
    organizations = data.get("account", {}).get("organizations", [])
    if not organizations:
        raise PublishError("Buffer: nenhuma organizacao encontrada na conta")
    return organizations[0]["id"]


def list_channels() -> list[dict[str, Any]]:
    organization_id = get_organization_id()
    data = graphql_request(_CHANNELS_QUERY, {"organizationId": organization_id})
    return data.get("channels", [])


def _channel_env_var(group: str, platform: str) -> str:
    if group not in ALL_GROUPS:
        raise PublishError(f"Grupo de canais desconhecido pro Buffer: {group}")
    if platform not in ALL_PLATFORMS:
        raise PublishError(f"Plataforma desconhecida pro Buffer: {platform}")
    return f"BUFFER_CHANNEL_{group.upper()}_{platform.upper()}"


def _channel_id(group: str, platform: str) -> str:
    env_var = _channel_env_var(group, platform)
    channel_id = os.environ.get(env_var)
    if not channel_id:
        raise PublishError(
            f"{env_var} nao esta definida no .env. Rode `clipador-publish buffer-channels` "
            "pra listar os canais disponiveis e preencha a variavel com o id certo."
        )
    return channel_id


def _build_caption(title: str, description: str, hashtags: list[str]) -> str:
    tags = " ".join(f"#{tag.lstrip('#')}" for tag in hashtags)
    parts = [title, description, tags]
    return "\n\n".join(part for part in parts if part)


def _metadata_for_platform(platform: str, title: str) -> dict[str, Any] | None:
    """Bloco `metadata` por rede exigido pelo Buffer alem do `text` generico.

    YouTube guarda o titulo do video em campo proprio (`metadata.youtube.title`),
    separado da descricao/legenda que vai em `text` - sem isso o video sobe sem
    titulo. Instagram exige `type`+`shouldShareToFeed` dentro do bloco assim que
    ele e enviado; forcamos `reel` (o clipe curto e sempre vertical) compartilhado
    tambem no feed. TikTok nao tem campo obrigatorio, usa só o `text` generico.
    """
    if platform == PLATFORM_YOUTUBE:
        return {"youtube": {"title": title[:MAX_YOUTUBE_TITLE_LENGTH]}}
    if platform == PLATFORM_INSTAGRAM:
        return {"instagram": {"type": "reel", "shouldShareToFeed": True}}
    return None


def _create_post(channel_id: str, text: str, video_url: str, metadata: dict[str, Any] | None) -> str:
    data = graphql_request(
        _CREATE_POST_MUTATION,
        {"channelId": channel_id, "text": text, "videoUrl": video_url, "metadata": metadata},
    )
    result = data.get("createPost", {})
    if "message" in result:
        raise PublishError(f"Buffer: falha ao criar o post: {result['message']}")
    post = result.get("post")
    if not post:
        raise PublishError("Buffer: resposta inesperada ao criar o post")
    return post["id"]


def _publish_now(post_id: str) -> None:
    """Dispara o envio imediato via `editPost(mode: shareNow)` num post ja criado
    (com `addToQueue`, onde o `text` fica salvo de verdade) - evita o bug de
    `shareNow` direto na criacao, que descarta o texto em posts com video."""
    data = graphql_request(_EDIT_POST_MUTATION, {"id": post_id})
    result = data.get("editPost", {})
    if "message" in result:
        raise PublishError(f"Buffer: falha ao disparar publicacao imediata: {result['message']}")
    if not result.get("post"):
        raise PublishError("Buffer: resposta inesperada ao disparar publicacao imediata")


# Confirmado via introspection (`__type(name: "PostStatus")`) contra a API real:
# draft, error, needs_approval, scheduled, sending, sent - NAO "buffer"/"failed"
# como a documentacao escrita do Buffer sugeria (doc desatualizada/errada).
_STATUS_SENT = "sent"
_STATUS_ERROR = "error"
_STATUS_STUCK = frozenset({"draft", "needs_approval"})


def _wait_for_sent(post_id: str) -> None:
    deadline = time.monotonic() + CONTAINER_POLL_TIMEOUT_SECONDS
    while True:
        data = graphql_request(_POST_STATUS_QUERY, {"id": post_id})
        post = data.get("post") or {}
        status = post.get("status")
        if status == _STATUS_SENT:
            return
        if status == _STATUS_ERROR:
            error = post.get("error") or {}
            raise PublishError(f"Buffer: post falhou: {error.get('message', 'sem detalhe')}")
        if status in _STATUS_STUCK:
            raise PublishError(
                f"Buffer: post ficou em status '{status}' (nao vai virar 'sent' sozinho - "
                "precisa de acao manual no Buffer, ex: aprovacao ou publicar da fila)."
            )
        if time.monotonic() > deadline:
            raise PublishError("Buffer: timeout esperando o post ser publicado")
        time.sleep(CONTAINER_POLL_INTERVAL_SECONDS)


def publish(
    video_path: Path,
    title: str,
    description: str,
    hashtags: list[str],
    platform: str,
    group: str,
) -> PublishResult:
    channel_id = _channel_id(group, platform)
    text = _build_caption(title, description, hashtags)
    metadata = _metadata_for_platform(platform, title)

    staged, video_url = stage_video(video_path)
    try:
        post_id = _create_post(channel_id, text, video_url, metadata)
        _publish_now(post_id)
        _wait_for_sent(post_id)
        return PublishResult(platform, True, remote_id=post_id, message="publicado via Buffer")
    finally:
        delete_staged(staged)
