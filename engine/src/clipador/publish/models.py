"""Tipos compartilhados entre os publishers de cada plataforma."""

from __future__ import annotations

from dataclasses import dataclass

PLATFORM_YOUTUBE = "youtube"
PLATFORM_INSTAGRAM = "instagram"
PLATFORM_TIKTOK = "tiktok"
ALL_PLATFORMS = (PLATFORM_YOUTUBE, PLATFORM_INSTAGRAM, PLATFORM_TIKTOK)

# A conta Buffer do usuario tem 2 grupos de canais (contas conectadas
# distintas), cada um com seus proprios canais de YouTube/Instagram/TikTok.
GROUP_COMMIT_CIVICO = "commit_civico"
GROUP_PESSOAL = "pessoal"
ALL_GROUPS = (GROUP_COMMIT_CIVICO, GROUP_PESSOAL)

# TikTok e Instagram sao plataformas essencialmente verticais: um clipe longo
# (16:9) so faz sentido ir pro YouTube. Evita publicar cortes horizontais fora
# de contexto num feed vertical sem o usuario ter que lembrar disso toda vez.
LONG_FORMAT_PLATFORMS = (PLATFORM_YOUTUBE,)


class PublishError(RuntimeError):
    """Erro especifico de uma plataforma durante autenticacao ou publicacao."""


@dataclass
class PublishResult:
    platform: str
    success: bool
    remote_id: str | None = None
    remote_url: str | None = None
    message: str = ""
