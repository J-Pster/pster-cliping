"""Upload de clipe pro TikTok via Content Posting API, modo "upload to inbox".

Decisao do usuario: usa o escopo `video.upload` (rascunho na inbox do app,
precisa abrir o TikTok e confirmar manualmente), nao o Direct Post automatico
(`video.publish`), porque um app nao auditado so consegue Direct Post em
conta marcada como privada, e a conta aqui precisa continuar publica.
"""

from __future__ import annotations

import base64
import hashlib
import math
import os
import secrets
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

load_dotenv(override=True)

PLATFORM = "tiktok"
AUTHORIZE_URL = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
INBOX_INIT_URL = "https://open.tiktokapis.com/v2/post/publish/inbox/video/init/"
SCOPES = "video.upload"

MIN_CHUNK_BYTES = 5 * 1024 * 1024
MAX_CHUNK_BYTES = 64 * 1024 * 1024


def _app_config() -> tuple[str, str, str]:
    client_key = os.environ.get("TIKTOK_CLIENT_KEY")
    client_secret = os.environ.get("TIKTOK_CLIENT_SECRET")
    redirect_uri = os.environ.get("TIKTOK_REDIRECT_URI")
    if not client_key or not client_secret or not redirect_uri:
        raise PublishError(
            "TIKTOK_CLIENT_KEY / TIKTOK_CLIENT_SECRET / TIKTOK_REDIRECT_URI nao estao definidas no .env"
        )
    return client_key, client_secret, redirect_uri


def _pkce_pair() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).rstrip(b"=").decode("ascii")
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
    return verifier, challenge.rstrip(b"=").decode("ascii")


def authenticate() -> None:
    client_key, client_secret, redirect_uri = _app_config()
    port = urlparse(redirect_uri).port
    if not port:
        raise PublishError("TIKTOK_REDIRECT_URI precisa incluir uma porta explicita")

    verifier, challenge = _pkce_pair()
    state = secrets.token_urlsafe(16)
    params = {
        "client_key": client_key,
        "response_type": "code",
        "scope": SCOPES,
        "redirect_uri": redirect_uri,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    webbrowser.open(f"{AUTHORIZE_URL}?{urlencode(params)}")
    code = wait_for_redirect_code(port)

    response = requests.post(
        TOKEN_URL,
        data={
            "client_key": client_key,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
            "code_verifier": verifier,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    save_tokens(
        PLATFORM,
        {
            "access_token": payload["access_token"],
            "refresh_token": payload["refresh_token"],
            "expires_at": time.time() + payload["expires_in"],
        },
    )


def _get_valid_token() -> str:
    stored = load_tokens(PLATFORM)
    if not stored:
        raise PublishError(
            "TikTok ainda nao autenticado, rode `clipador-publish auth tiktok` primeiro"
        )
    if stored["expires_at"] - time.time() > 60:
        return stored["access_token"]

    client_key, client_secret, _redirect_uri = _app_config()
    response = requests.post(
        TOKEN_URL,
        data={
            "client_key": client_key,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
            "refresh_token": stored["refresh_token"],
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    stored["access_token"] = payload["access_token"]
    stored["refresh_token"] = payload["refresh_token"]  # rotaciona a cada uso
    stored["expires_at"] = time.time() + payload["expires_in"]
    save_tokens(PLATFORM, stored)
    return stored["access_token"]


def _chunk_plan(video_size: int) -> tuple[int, int]:
    if video_size <= MIN_CHUNK_BYTES:
        return video_size, 1
    chunk_size = MAX_CHUNK_BYTES
    total_chunks = math.ceil(video_size / chunk_size)
    return chunk_size, total_chunks


def upload_draft(video_path: Path, caption: str) -> dict[str, Any]:
    """Sobe o clipe como rascunho na inbox do app; usuario confirma a postagem no celular."""
    access_token = _get_valid_token()
    video_size = video_path.stat().st_size
    chunk_size, total_chunk_count = _chunk_plan(video_size)

    init = requests.post(
        INBOX_INIT_URL,
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        json={
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": video_size,
                "chunk_size": chunk_size,
                "total_chunk_count": total_chunk_count,
            },
            "post_info": {"title": caption[:2200]},
        },
        timeout=30,
    )
    init.raise_for_status()
    init_data = init.json()["data"]
    upload_url = init_data["upload_url"]

    with video_path.open("rb") as handle:
        for chunk_index in range(total_chunk_count):
            start = chunk_index * chunk_size
            data = handle.read(chunk_size)
            end = start + len(data) - 1
            put_response = requests.put(
                upload_url,
                data=data,
                headers={
                    "Content-Range": f"bytes {start}-{end}/{video_size}",
                    "Content-Type": "video/mp4",
                },
                timeout=300,
            )
            put_response.raise_for_status()

    return init_data
