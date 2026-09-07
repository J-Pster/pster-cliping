"""Tratamento do fundo/luz do frame pelo Gemini Flash Image (apelidado "Nano Banana").

"Nano Banana" e o apelido do modelo de imagem Flash do Gemini (Google); o SDK usado e o
`google-genai`, opcional. O prompt trata SO fundo, luz e contraste: o rosto da pessoa
nunca pode ser editado, senao a thumbnail deixa de corresponder ao clipe.

Sem `GEMINI_API_KEY`, sem o SDK ou com a chamada falhando (quota, timeout, resposta sem
imagem), `edit()` cai em `fallback_treatment`, um tratamento local em Pillow puro, para
que sempre exista um fundo tratado.
"""

from __future__ import annotations

import io
import logging
import os
from typing import Any, Callable

from dotenv import load_dotenv
from PIL import Image, ImageEnhance, ImageFilter

from clipador import category as category_module

logger = logging.getLogger(__name__)

load_dotenv(override=True)  # .env do projeto sempre vence env var solta do sistema

MODEL_ID = "gemini-2.5-flash-image"

_POLITICS_PERSON_DEFAULT_PROMPT = (
    "Trate esta imagem para virar thumbnail de video de alto impacto: aplique um grade "
    "cinematografico escuro e dramatico no fundo atras da pessoa (contraste bem mais alto, "
    "sombras profundas, uma leve vinheta escurecendo as bordas), como thumbnail profissional "
    "de canal grande do YouTube, nao uma correcao sutil de cor. A pessoa em primeiro plano "
    "deve continuar bem iluminada e destacada contra esse fundo mais escuro. Mantenha o "
    "rosto e os tracos faciais da pessoa exatamente como estao, nao distorca o rosto, nao "
    "mude a expressao, nao adicione nem remova pessoas e nao escreva texto na imagem."
)

_GAMING_DEFAULT_PROMPT = (
    "Trate esta imagem (frame de gameplay) para virar thumbnail de alto impacto: aumente "
    "saturacao e contraste da cena de jogo pra ficar vibrante e chamativa, sem escurecer o "
    "fundo nem aplicar grade cinematografico escuro - thumbnail de gaming funciona melhor "
    "clara e energetica, nao sombria. Se houver rosto de jogador visivel (webcam), mantenha "
    "seus tracos faciais exatamente como estao, nao distorca o rosto, nao mude a expressao, "
    "nao adicione nem remova pessoas e nao escreva texto na imagem."
)

# Alinhado com `ai_thumbnail._BOOK_AUDIOBOOK_PROMPT_TEMPLATE` em 2026-09-04: a categoria
# deixou de ser "pessoa lendo, luz dourada, clima BookTok" e passou a usar a mesma
# linguagem visual da politico/pessoa (escuro, cinematografico, alto contraste). Este
# prompt e o caminho de FALLBACK (composicao em camadas quando a geracao completa falha),
# entao ele so trata o frame - nao ha como inventar imagem conceitual aqui.
_BOOK_AUDIOBOOK_DEFAULT_PROMPT = (
    "Trate esta imagem para virar thumbnail de video de alto impacto: aplique um grade "
    "cinematografico escuro e dramatico (contraste bem mais alto, sombras profundas, uma "
    "leve vinheta escurecendo as bordas), como thumbnail profissional de canal grande do "
    "YouTube, nao uma correcao sutil de cor. O objeto principal em primeiro plano (o livro, "
    "o documento ou o que estiver em foco na cena) deve continuar bem iluminado e destacado "
    "contra esse fundo mais escuro. Se houver pessoa visivel, mantenha o rosto e os tracos "
    "faciais exatamente como estao, nao distorca o rosto e nao mude a expressao. Nao "
    "adicione nem remova pessoas e nao escreva texto na imagem."
)

DEFAULT_PROMPT_BY_CATEGORY: dict[str, str] = {
    category_module.POLITICS_PERSON: _POLITICS_PERSON_DEFAULT_PROMPT,
    category_module.GAMING: _GAMING_DEFAULT_PROMPT,
    category_module.BOOK_AUDIOBOOK: _BOOK_AUDIOBOOK_DEFAULT_PROMPT,
}

# Mantido para quem ainda importa o nome antigo diretamente: sempre a variante politico/pessoa.
DEFAULT_PROMPT = _POLITICS_PERSON_DEFAULT_PROMPT


def fallback_treatment(frame: Image.Image) -> Image.Image:
    """Fundo tratado sem API nenhuma: escurece de leve e aplica blur leve."""
    treated = frame.convert("RGB").filter(ImageFilter.GaussianBlur(radius=3))
    return ImageEnhance.Brightness(treated).enhance(0.7)


def _first_image(response: Any) -> Image.Image | None:
    for candidate in getattr(response, "candidates", None) or []:
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", None) or []:
            inline = getattr(part, "inline_data", None)
            data = getattr(inline, "data", None)
            if data:
                return Image.open(io.BytesIO(data))
    return None


class GeminiBackgroundEditor:
    """Edita fundo/luz de um frame via Gemini Flash Image, com fallback local garantido."""

    def __init__(
        self,
        client_factory: Callable[[], Any] | None = None,
        model: str = MODEL_ID,
        prompt: str = DEFAULT_PROMPT,
    ) -> None:
        self.model = model
        self.prompt = prompt
        self._client_factory = client_factory
        self._client: Any | None = None
        self._available: bool | None = None

    def _probe(self) -> bool:
        if self._client_factory is not None:
            return True
        if not os.environ.get("GEMINI_API_KEY"):
            logger.warning(
                "GEMINI_API_KEY nao definida; o fundo da thumbnail sera tratado localmente."
            )
            return False
        try:
            import google.genai  # noqa: F401
        except Exception as exc:
            logger.warning(
                "google-genai indisponivel (%s); o fundo da thumbnail sera tratado "
                "localmente. Instale com: pip install 'clipador[thumbnail-ai]'",
                exc,
            )
            return False
        return True

    @property
    def available(self) -> bool:
        if self._available is None:
            self._available = self._probe()
        return self._available

    def _default_client(self) -> Any:
        from google import genai

        return genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    @property
    def client(self) -> Any:
        if self._client is None:
            factory = self._client_factory or self._default_client
            self._client = factory()
        return self._client

    def edit(self, frame: Image.Image, prompt: str | None = None) -> Image.Image:
        if not self.available:
            return fallback_treatment(frame)

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=[prompt or self.prompt, frame],
            )
            edited = _first_image(response)
            if edited is None:
                raise ValueError("resposta do Gemini sem imagem")
            return edited.convert("RGB")
        except Exception as exc:
            logger.warning(
                "Tratamento de fundo via Gemini falhou (%s); usando o tratamento local.", exc
            )
            return fallback_treatment(frame)


def build_background_editor(
    category: str = category_module.DEFAULT_CATEGORY,
    client_factory: Callable[[], Any] | None = None,
    model: str = MODEL_ID,
) -> GeminiBackgroundEditor:
    """Fabrica o editor de fundo (fallback em camadas) ja com o prompt da categoria certa."""
    prompt = DEFAULT_PROMPT_BY_CATEGORY[category_module.validate_category(category)]
    return GeminiBackgroundEditor(client_factory=client_factory, model=model, prompt=prompt)
