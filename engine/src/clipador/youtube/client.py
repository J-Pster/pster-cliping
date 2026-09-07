import os

from dotenv import load_dotenv
from googleapiclient.discovery import build

load_dotenv(override=True)  # .env do projeto sempre vence env var solta do sistema


def get_client():
    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "YOUTUBE_API_KEY nao esta definida no ambiente (verifique o arquivo .env)"
        )
    return build("youtube", "v3", developerKey=api_key)
