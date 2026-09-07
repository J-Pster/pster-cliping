"""Upload de clipe pro YouTube via Data API v3 (videos.insert).

App OAuth fica em modo "Testing" no Google Cloud (decisao do usuario: evita
depender da verificacao do Google, que e imprevisivel para o escopo sensivel
youtube.upload). Efeito colateral aceito: o refresh token expira em 7 dias,
entao `get_credentials` reabre o navegador sozinho quando o refresh falha com
`invalid_grant`, em vez de propagar o erro pra quem chama.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from clipador.publish.credentials_store import load_tokens, save_tokens
from clipador.publish.models import PublishError

load_dotenv(override=True)

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
PLATFORM = "youtube"

# Vertical curto (<=3min) vira Short automaticamente, longo horizontal vira
# video normal. Nao existe parametro na API pra forcar isso, e so o arquivo.
DEFAULT_CATEGORY_ID = "25"  # News & Politics


def _client_secrets_file() -> Path:
    raw = os.environ.get("YOUTUBE_OAUTH_CLIENT_SECRETS_FILE")
    if not raw:
        raise PublishError(
            "YOUTUBE_OAUTH_CLIENT_SECRETS_FILE nao esta definida (baixe o client secret "
            "'Desktop app' do Google Cloud Console e aponte o caminho no .env)"
        )
    path = Path(raw)
    if not path.is_file():
        raise PublishError(f"Client secrets do YouTube nao encontrado em {path}")
    return path


def authenticate() -> None:
    """Roda o consentimento OAuth uma vez e persiste o refresh token local."""
    flow = InstalledAppFlow.from_client_secrets_file(str(_client_secrets_file()), SCOPES)
    creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    save_tokens(PLATFORM, {"authorized_user_info": creds.to_json()})


def get_credentials() -> Credentials:
    stored = load_tokens(PLATFORM)
    if not stored:
        raise PublishError(
            "YouTube ainda nao autenticado, rode `clipador-publish auth youtube` primeiro"
        )
    creds = Credentials.from_authorized_user_info(
        json.loads(stored["authorized_user_info"]), SCOPES
    )
    if creds.valid:
        return creds
    if not creds.refresh_token:
        raise PublishError("Token do YouTube sem refresh token, rode `clipador-publish auth youtube`")
    try:
        creds.refresh(Request())
    except RefreshError as exc:
        raise PublishError(
            "Refresh token do YouTube expirou (app em modo Testing expira em 7 dias). "
            "Rode `clipador-publish auth youtube` de novo."
        ) from exc
    save_tokens(PLATFORM, {"authorized_user_info": creds.to_json()})
    return creds


def upload(
    video_path: Path,
    title: str,
    description: str,
    *,
    privacy_status: str = "public",
    category_id: str = DEFAULT_CATEGORY_ID,
) -> dict[str, Any]:
    creds = get_credentials()
    youtube = build("youtube", "v3", credentials=creds)

    body = {
        "snippet": {"title": title[:100], "description": description, "categoryId": category_id},
        "status": {"privacyStatus": privacy_status, "selfDeclaredMadeForKids": False},
    }
    media = MediaFileUpload(str(video_path), mimetype="video/mp4", chunksize=8 * 1024 * 1024, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        _status, response = request.next_chunk()
    return response
