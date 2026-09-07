"""Publicacao de Reels via Instagram API with Instagram Login (Content Publishing API).

Fluxo: OAuth Instagram Login (nao precisa de Facebook Page) -> troca por long-lived
token (60 dias, renovavel sem novo login) -> upload do clipe pro S3 (staging_s3,
a Meta exige video_url publica) -> cria container -> aguarda status FINISHED ->
publica.
"""

from __future__ import annotations

import os
import time
import webbrowser
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlparse

import requests
from dotenv import load_dotenv

from clipador.publish.credentials_store import load_tokens, save_tokens
from clipador.publish.models import PublishError
from clipador.publish.oauth_local_server import wait_for_redirect_code
from clipador.publish.staging_s3 import delete_staged, stage_video

load_dotenv(override=True)

PLATFORM = "instagram"
AUTHORIZE_URL = "https://www.instagram.com/oauth/authorize"
TOKEN_URL = "https://api.instagram.com/oauth/access_token"
EXCHANGE_URL = "https://graph.instagram.com/access_token"
REFRESH_URL = "https://graph.instagram.com/refresh_access_token"
GRAPH_ROOT = "https://graph.instagram.com"

SCOPES = "instagram_business_basic,instagram_business_content_publish"
CONTAINER_POLL_INTERVAL_SECONDS = 5
CONTAINER_POLL_TIMEOUT_SECONDS = 600
# So renova quando faltar menos de 10 dias pros 60 de validade, evitando
# gastar renovacoes com um token que ainda tem sobra confortavel.
REFRESH_WHEN_EXPIRES_WITHIN_SECONDS = 10 * 24 * 3600


def _app_config() -> tuple[str, str, str]:
    app_id = os.environ.get("INSTAGRAM_APP_ID")
    app_secret = os.environ.get("INSTAGRAM_APP_SECRET")
    redirect_uri = os.environ.get("INSTAGRAM_REDIRECT_URI")
    if not app_id or not app_secret or not redirect_uri:
        raise PublishError(
            "INSTAGRAM_APP_ID / INSTAGRAM_APP_SECRET / INSTAGRAM_REDIRECT_URI "
            "nao estao definidas no .env"
        )
    return app_id, app_secret, redirect_uri


def build_authorize_url() -> str:
    app_id, _secret, redirect_uri = _app_config()
    params = {
        "client_id": app_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": SCOPES,
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


def exchange_code(code: str) -> None:
    """Troca o code do redirect por token curto, depois por um long-lived (60 dias)."""
    app_id, app_secret, redirect_uri = _app_config()
    short_lived = requests.post(
        TOKEN_URL,
        data={
            "client_id": app_id,
            "client_secret": app_secret,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
            "code": code,
        },
        timeout=30,
    )
    short_lived.raise_for_status()
    short_payload = short_lived.json()

    long_lived = requests.get(
        EXCHANGE_URL,
        params={
            "grant_type": "ig_exchange_token",
            "client_secret": app_secret,
            "access_token": short_payload["access_token"],
        },
        timeout=30,
    )
    long_lived.raise_for_status()
    long_payload = long_lived.json()

    save_tokens(
        PLATFORM,
        {
            "access_token": long_payload["access_token"],
            "expires_at": time.time() + long_payload["expires_in"],
            "ig_user_id": short_payload["user_id"],
        },
    )


def authenticate() -> None:
    """Abre o navegador pro consentimento, captura o redirect e persiste o token."""
    _app_id, _secret, redirect_uri = _app_config()
    port = urlparse(redirect_uri).port
    if not port:
        raise PublishError("INSTAGRAM_REDIRECT_URI precisa incluir uma porta explicita")
    webbrowser.open(build_authorize_url())
    code = wait_for_redirect_code(port)
    exchange_code(code)


def _get_valid_token() -> dict[str, Any]:
    stored = load_tokens(PLATFORM)
    if not stored:
        raise PublishError(
            "Instagram ainda nao autenticado, rode `clipador-publish auth instagram` primeiro"
        )
    if stored["expires_at"] - time.time() < REFRESH_WHEN_EXPIRES_WITHIN_SECONDS:
        response = requests.get(
            REFRESH_URL,
            params={"grant_type": "ig_refresh_token", "access_token": stored["access_token"]},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        stored["access_token"] = payload["access_token"]
        stored["expires_at"] = time.time() + payload["expires_in"]
        save_tokens(PLATFORM, stored)
    return stored


def _build_caption(title: str, description: str, hashtags: list[str]) -> str:
    tags = " ".join(f"#{tag.lstrip('#')}" for tag in hashtags)
    parts = [title, description, tags]
    return "\n\n".join(part for part in parts if part)


def publish(video_path: Path, title: str, description: str, hashtags: list[str]) -> dict[str, Any]:
    token = _get_valid_token()
    access_token = token["access_token"]
    ig_user_id = token["ig_user_id"]

    bucket, key, video_url = stage_video(video_path)
    try:
        create = requests.post(
            f"{GRAPH_ROOT}/{ig_user_id}/media",
            data={
                "media_type": "REELS",
                "video_url": video_url,
                "caption": _build_caption(title, description, hashtags),
                "share_to_feed": "true",
                "access_token": access_token,
            },
            timeout=60,
        )
        create.raise_for_status()
        container_id = create.json()["id"]

        deadline = time.monotonic() + CONTAINER_POLL_TIMEOUT_SECONDS
        while True:
            status = requests.get(
                f"{GRAPH_ROOT}/{container_id}",
                params={"fields": "status_code", "access_token": access_token},
                timeout=30,
            )
            status.raise_for_status()
            status_code = status.json()["status_code"]
            if status_code == "FINISHED":
                break
            if status_code in ("ERROR", "EXPIRED"):
                raise PublishError(f"Instagram rejeitou o container do clipe: {status_code}")
            if time.monotonic() > deadline:
                raise PublishError("Timeout esperando o Instagram processar o clipe")
            time.sleep(CONTAINER_POLL_INTERVAL_SECONDS)

        publish_response = requests.post(
            f"{GRAPH_ROOT}/{ig_user_id}/media_publish",
            data={"creation_id": container_id, "access_token": access_token},
            timeout=60,
        )
        publish_response.raise_for_status()
        return publish_response.json()
    finally:
        delete_staged(bucket, key)
