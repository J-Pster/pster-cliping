"""Geracao da thumbnail COMPLETA (fundo + texto + seta) numa unica chamada ao Gemini Image
(apelidado "Nano Banana"), em vez de compositar fundo/recorte/texto em camadas com Pillow.

A composicao em camadas (`composer.py` original: `background.py` + `cutout.py` + texto/seta
desenhados a mao) ficou com cara de amador (seta crua, headline colidindo com banner). O
Gemini 3 Flash/Pro Image renderiza texto legivel de verdade (ao contrario de geracoes de
imagem mais antigas, incluindo o Gemini 2.5 Flash Image usado em `background.py`), entao
vale deixar o proprio modelo desenhar a composicao inteira a partir do frame de referencia.

Sem `GEMINI_API_KEY`, sem o SDK, sem headline, ou com a chamada falhando (quota, timeout,
modelo em alta demanda), `generate()` devolve None: quem chamar (`ThumbnailComposer`) cai
pro pipeline antigo em camadas, que continua existindo como rede de seguranca.
"""

from __future__ import annotations

import io
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv
from PIL import Image

from clipador import category as category_module
from clipador.thumbnail.face_library import PoliticalFigure

logger = logging.getLogger(__name__)

load_dotenv(override=True)  # .env do projeto sempre vence env var solta do sistema

# Flash (nao Pro): mais rapido e barato, e o teste real mostrou qualidade de texto/rosto
# boa o suficiente. O Pro (`gemini-3-pro-image-preview`) e mais fiel mas, no teste real,
# devolveu 503 (alta demanda) - fica configuravel pra quem quiser tentar trocar.
MODEL_ID = "gemini-3.1-flash-image-preview"

# A API espera a razao como string literal (ex.: "9:16"), nao um enum - os valores aceitos
# sao '1:1','1:4','1:8','2:3','3:2','3:4','4:1','4:3','4:5','5:4','8:1','9:16','16:9','21:9'.
DEFAULT_ASPECT_RATIO = "9:16"

# Padrao de marca do canal (Missao / Commit Civico), fixado pelo usuario apos aprovar a
# geracao completa via IA: titulo embaixo (nao mais no topo), seta LARANJA com contorno
# preto (era amarela), paleta preto+amarelo+branco (maior contraste testado, ver pesquisa
# da sessao), mascote onca pintada como CONTEXTO disponivel pra IA usar com bom senso, nunca
# obrigatorio - a maioria das thumbnails nao deve incluir a onca.
#
# Refinamentos de uma segunda rodada de feedback (usuario viu um lote de 24 thumbnails
# reais): (1) fundo estava virando sempre um estudio escuro generico, perdendo o ambiente
# real do video (entrevista, sala especifica etc) - agora pede inspiracao na cena real; (2)
# composicao sempre defaultava pra rosto no centro, mesmo quando o assunto era sobre um
# objeto especifico aparecendo na cena (ex.: um livro sendo mostrado) - agora da liberdade
# de focar no objeto quando fizer mais sentido pro headline; (3) quantidade de linha do
# texto era fixa (1-2) pros dois formatos, gerando repeticao/esticamento de palavra pra
# forcar 2 linhas em titulo curto - agora e por aspect ratio E deixa explicito "so quebra
# linha se precisar de verdade, nunca force".
_POLITICS_PERSON_PROMPT_TEMPLATE = """Design a professional, high-CTR YouTube thumbnail using the person and scene in this reference image, following this channel's visual brand described below.

Face Consistency: keep the person's facial features, hairstyle, skin tone and identity exactly the same as the reference image. Do not distort, reimagine, or change the face or the person's identity. You may slightly intensify the expression to look more engaged and intense.

{face_reference_instruction}

Composition: usually make the person the focal point of the image, framed from chest up. HOWEVER, if the headline text below is actually about a specific object, document or prop that is visible in the reference image (e.g. a book, a paper, an item being discussed), you may instead make THAT object the visual focus of the thumbnail, with or without the person alongside it - use your judgment based on what the headline is actually about, do not always default to a floating head shot when the real subject is an object in the scene.

Graphics: add one bold orange curved arrow with a thick black outline pointing from a top corner of the frame toward the main focal point of the image (the person's face, or the featured object if that is the focus this time).

Text: overlay bold text reading exactly "{headline}", positioned in the BOTTOM area of the frame with a clear margin from the edges - avoid the bottom-right corner specifically, that spot is covered by YouTube's own duration badge. {text_lines_instruction} Primary text color white with a thick black outline and a subtle drop shadow; you may render part of the text (e.g. one key word) in yellow as an accent for extra pop. Condensed sans-serif impact-style font, all caps, perfectly legible and spelled exactly as written, no other text anywhere in the image.

Background: take inspiration from the actual environment visible in the reference image (the room, studio, or setting the video was actually shot in) instead of replacing it with a fully generic backdrop - keep it recognizably related to the original scene. Apply a dark, cinematic treatment on top of that real environment: dramatic side lighting, high contrast, a subtle vignette on the edges, decluttered, no other people, no logos, no watermarks.

Brand palette: this channel's brand colors are black, yellow and white - favor this palette across text, graphics and accents (black as the dominant base tone, yellow as accent, white for primary text/highlights).

Brand context (optional, use with good judgment): this channel's mascot is a jaguar ("onca pintada"). You may OPTIONALLY include a subtle nod to a jaguar (a small silhouette, spotted-pattern accent, or occasionally the mascot itself) ONLY if it fits this specific moment naturally - do not force it in, most thumbnails should NOT include it.

Style: professional YouTube thumbnail used by large creators, clean composition, {aspect_ratio} aspect ratio."""

# Categoria jogos: sem marca/mascote fixos (produto generico pra qualquer canal de
# gameplay). Composicao livre em cima do frame de gameplay (que pode ou nao ter webcam
# do jogador), seta/circulo destacando a ACAO do highlight em vez da pessoa, paleta
# vibrante de 2-3 cores escolhida por momento (evita vermelho/preto/branco puro, que se
# perdem contra a propria UI do YouTube - pesquisa de mercado 2025-2026 de thumbnail de
# gaming), sem tratamento escuro/cinematografico (gameplay ja e vibrante por natureza).
_GAMING_PROMPT_TEMPLATE = """Design a professional, high-CTR YouTube gaming thumbnail using the gameplay frame and, if visible, the player's webcam reaction in this reference image.

Face Consistency: if a player's webcam/facecam is visible in the reference image, keep their facial features, hairstyle, skin tone and identity exactly the same - do not distort or reimagine the face. You may slightly intensify the expression (more shocked, more hyped) to look more engaged.

{face_reference_instruction}

Composition: usually make the exact moment of the gameplay highlight (the kill, the clutch play, the key action visible on screen) the focal point, with the player's facecam reaction (if present in the reference image) as a secondary element in a corner, sized like a typical gaming thumbnail facecam overlay. If there is no visible facecam, the gameplay action itself is the sole focal point - do not invent a face that is not in the reference image.

Graphics: add one bold circle, highlight ring, or curved arrow with a thick outline pointing at or circling the key action/target in the gameplay frame (the eliminated enemy, the critical moment) - this should look like it is calling out exactly what happened, gaming-highlight style.

Text: overlay bold text reading exactly "{headline}", positioned in the BOTTOM area of the frame with a clear margin from the edges - avoid the bottom-right corner specifically, that spot is covered by YouTube's own duration badge. {text_lines_instruction} High-contrast text with a thick black outline and a strong drop shadow so it stays legible over a busy gameplay background. Condensed sans-serif impact-style font, all caps, perfectly legible and spelled exactly as written, no other text anywhere in the image.

Background: keep the actual gameplay scene visible in the reference image recognizable (the map, the HUD, the environment) - do not replace it with a generic backdrop. Boost contrast and saturation to make the scene pop, but do NOT apply a dark cinematic treatment - gaming thumbnails read best bright and punchy, not dim.

Color palette: pick 2 or 3 vibrant, high-contrast accent colors for the graphics and text that suit this specific moment (favor colors like orange, teal, yellow, purple, or green over plain red/black/white, which blend into YouTube's own interface) - do not force a fixed brand palette, choose what pops most against this specific frame.

Style: professional gaming YouTube thumbnail used by large gaming creators, energetic and punchy, clean composition, {aspect_ratio} aspect ratio."""

# Categoria livro/audiobook, reescrito em 2026-09-04 depois de rodar de ponta a ponta:
# o template anterior mandava fazer da PESSOA LENDO + livro fisico o foco, e o resultado
# real foi ruim nos dois formatos. Dois motivos:
#
# 1. Video de leitura costuma ser plano fixo de cima pra baixo sobre a mesa, sem rosto em
#    quadro. O prompt pedia um rosto que simplesmente nao existe no frame de referencia.
# 2. Mesmo quando ha rosto, "pessoa segurando livro" e a mesma imagem em todo clipe do
#    canal: nao diz nada sobre o assunto DAQUELE trecho, e e o assunto que faz clicar.
#
# A direcao agora e a mesma linguagem visual da categoria politico/pessoa (marca preto/
# amarelo/branco, seta laranja, texto impact, tratamento escuro cinematografico), trocando
# o retrato central por uma imagem CONCEITUAL do que esta sendo dito no trecho. O frame do
# video vira contexto de ambiente, nao o sujeito.
_BOOK_AUDIOBOOK_PROMPT_TEMPLATE = """Design a professional, high-CTR YouTube thumbnail for a clip of a book reading/audiobook video, following this channel's visual brand described below.

Subject: the thumbnail must be about the IDEA in the headline, not about the act of reading. Build a strong conceptual image that represents what is being discussed in this specific excerpt - the institution, the object, the place, the mechanism, the conflict or the consequence that the headline names. Think editorial illustration or news-magazine cover art: one clear, dramatic central image that a viewer instantly connects to the topic.

{face_reference_instruction}

People: there does NOT need to be any person in this thumbnail, and there is no required face. Do not build the image around a reader, a narrator, or a generic person holding a book, and do not invent a portrait of someone who is not clearly the subject of the headline. If the headline is specifically about a real, named public figure, you may depict that figure; otherwise prefer objects, places, symbols and scenes over people.

Composition: one dominant focal element, centered or slightly off-center, with clear separation from the background and enough empty space in the bottom area for the text. Avoid clutter and avoid collage - a single strong image reads better at thumbnail size than several small ones.

Graphics: add one bold orange curved arrow with a thick black outline pointing from a top corner of the frame toward the main focal point of the image.

Text: overlay bold text reading exactly "{headline}", positioned in the BOTTOM area of the frame with a clear margin from the edges - avoid the bottom-right corner specifically, that spot is covered by YouTube's own duration badge. {text_lines_instruction} Primary text color white with a thick black outline and a subtle drop shadow; you may render part of the text (e.g. one key word) in yellow as an accent for extra pop. Condensed sans-serif impact-style font, all caps, perfectly legible and spelled exactly as written, no other text anywhere in the image.

Background: a dark, cinematic treatment that supports the central subject: dramatic lighting, high contrast, a subtle vignette on the edges, decluttered, no other people, no logos, no watermarks. You do NOT need to reproduce the desk or room visible in the reference image - that frame only tells you the video's setting, it is not the subject. Use it for tone if helpful, otherwise build the scene the headline calls for.

Brand palette: this channel's brand colors are black, yellow and white - favor this palette across text, graphics and accents (black as the dominant base tone, yellow as accent, white for primary text/highlights).

Brand context (optional, use with good judgment): this channel's mascot is a jaguar ("onca pintada"). You may OPTIONALLY include a subtle nod to a jaguar (a small silhouette, spotted-pattern accent, or occasionally the mascot itself) ONLY if it fits this specific moment naturally - do not force it in, most thumbnails should NOT include it.

Style: professional YouTube thumbnail used by large creators covering serious non-fiction (politics, strategy, business, a technical subject) - credible and substantive, dramatic without being cartoonish, clean composition, {aspect_ratio} aspect ratio."""

PROMPT_TEMPLATE_BY_CATEGORY: dict[str, str] = {
    category_module.POLITICS_PERSON: _POLITICS_PERSON_PROMPT_TEMPLATE,
    category_module.GAMING: _GAMING_PROMPT_TEMPLATE,
    category_module.BOOK_AUDIOBOOK: _BOOK_AUDIOBOOK_PROMPT_TEMPLATE,
}

# Mantido para quem ainda importa o nome antigo diretamente: sempre a variante politico/pessoa.
PROMPT_TEMPLATE = _POLITICS_PERSON_PROMPT_TEMPLATE

# 16:9 (video longo) tem pouco espaco vertical: so 1-2 linhas cabem bem. 9:16 (Shorts) tem
# espaco de sobra: ate 3 linhas cabem, mas 3 NAO e obrigatorio - so quando o headline
# precisar mesmo, nunca forcando quebra/repeticao de palavra so pra preencher linha.
_TEXT_LINES_16_9 = (
    "Break the text into 1 or 2 short lines (this is a horizontal thumbnail with limited "
    "vertical space) - use 2 lines only if the headline naturally needs it, never force a "
    "line break or repeat/stretch a word just to fill a second line."
)
_TEXT_LINES_9_16 = (
    "Break the text into however many short lines it naturally needs, up to 3 (this is a "
    "vertical thumbnail with more vertical space available) - do NOT force 2 or 3 lines "
    "when 1 line already fits well, and never repeat or stretch a word just to fill more "
    "lines."
)


FACE_REFERENCE_INSTRUCTION_TEMPLATE = (
    "Face reference library: {count} additional close-up photos of {person_name}'s real "
    "face are attached after the main reference image. If the person shown in the main "
    "reference image above is {person_name}, cross-reference these additional photos to "
    "lock in his exact facial identity, bone structure and likeness with full consistency "
    "- his face has been generated inconsistently in past attempts, treat these extra "
    "photos as the ground truth for what he actually looks like. If the main reference "
    "image shows a DIFFERENT person, ignore these additional reference photos completely "
    "and just follow the Face Consistency instruction above using only the main reference "
    "image."
)


def _text_lines_instruction(aspect_ratio: str) -> str:
    return _TEXT_LINES_16_9 if aspect_ratio == "16:9" else _TEXT_LINES_9_16


def _first_image(response: Any) -> Image.Image | None:
    for candidate in getattr(response, "candidates", None) or []:
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", None) or []:
            inline = getattr(part, "inline_data", None)
            data = getattr(inline, "data", None)
            if data:
                return Image.open(io.BytesIO(data))
    return None


class AIThumbnailGenerator:
    """Gera a thumbnail inteira via Gemini Image, com fallback (`None`) sempre garantido."""

    def __init__(
        self,
        client_factory: Callable[[], Any] | None = None,
        model: str = MODEL_ID,
        prompt_template: str = PROMPT_TEMPLATE,
        face_reference_dir: Path | None = None,
        face_reference_person: str = "",
    ) -> None:
        self.model = model
        self.prompt_template = prompt_template
        # Fallback estatico usado SO quando `generate()` e chamado sem `subject` (ex.:
        # construcao direta/testes). No pipeline normal, quem decide a referencia facial
        # e o `subject` escolhido POR CLIPE (ver `thumbnail.subject`), nunca um default
        # fixo por categoria - era assim que um clipe sobre outra pessoa acabava herdando
        # o rosto do apresentador do canal so porque a categoria e "politico_pessoa".
        self.face_reference_dir = face_reference_dir
        self.face_reference_person = face_reference_person
        self._client_factory = client_factory
        self._client: Any | None = None
        self._available: bool | None = None
        self._face_reference_cache: dict[Path, list[Image.Image]] = {}

    def _probe(self) -> bool:
        if self._client_factory is not None:
            return True
        if not os.environ.get("GEMINI_API_KEY"):
            logger.warning(
                "GEMINI_API_KEY nao definida; geracao completa de thumbnail via IA desativada."
            )
            return False
        try:
            import google.genai  # noqa: F401
        except Exception as exc:
            logger.warning(
                "google-genai indisponivel (%s); geracao completa de thumbnail via IA "
                "desativada. Instale com: pip install 'clipador[thumbnail-ai]'",
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

    def _load_face_references(self, face_reference_dir: Path | None = None) -> list[Image.Image]:
        """Carrega as fotos de `face_reference_dir` (ou do default da instancia quando
        omitido), com cache POR DIRETORIO - clipes diferentes do mesmo run podem escolher
        `subject` diferentes, entao o cache nao pode ser um unico slot fixo."""
        directory = face_reference_dir if face_reference_dir is not None else self.face_reference_dir
        if directory is None:
            return []
        if directory in self._face_reference_cache:
            return self._face_reference_cache[directory]

        images: list[Image.Image] = []
        if directory.is_dir():
            paths = sorted(
                p for p in directory.iterdir() if p.suffix.lower() in (".png", ".jpg", ".jpeg")
            )
            for path in paths:
                try:
                    images.append(Image.open(path).convert("RGB"))
                except Exception as exc:
                    logger.warning(
                        "Nao foi possivel carregar foto de referencia facial %s (%s); pulando.",
                        path,
                        exc,
                    )

        self._face_reference_cache[directory] = images
        return images

    def generate(
        self,
        frame: Image.Image,
        headline: str,
        aspect_ratio: str = DEFAULT_ASPECT_RATIO,
        subject: PoliticalFigure | None = None,
    ) -> Image.Image | None:
        headline = (headline or "").strip()
        if not self.available or not headline:
            return None

        try:
            from google.genai import types

            config = types.GenerateContentConfig(
                image_config=types.ImageConfig(aspect_ratio=aspect_ratio)
            )
            reference_dir = subject.reference_dir if subject is not None else self.face_reference_dir
            reference_person = subject.display_name if subject is not None else self.face_reference_person
            reference_images = self._load_face_references(reference_dir)
            face_reference_instruction = (
                FACE_REFERENCE_INSTRUCTION_TEMPLATE.format(
                    count=len(reference_images), person_name=reference_person
                )
                if reference_images
                else ""
            )
            prompt = self.prompt_template.format(
                headline=headline.upper(),
                aspect_ratio=aspect_ratio,
                text_lines_instruction=_text_lines_instruction(aspect_ratio),
                face_reference_instruction=face_reference_instruction,
            )
            chat = self.client.chats.create(model=self.model, config=config)
            response = chat.send_message([prompt, frame, *reference_images])
            image = _first_image(response)
            if image is None:
                raise ValueError("resposta do Gemini sem imagem")
            return image.convert("RGB")
        except Exception as exc:
            logger.warning(
                "Geracao completa da thumbnail via Gemini falhou (%s); composicao em "
                "camadas sera usada no lugar.",
                exc,
            )
            return None


@dataclass(frozen=True)
class ThumbnailCategoryDefaults:
    """Prompt-base por categoria pra construir `AIThumbnailGenerator`. Referencia facial
    NAO e mais um default fixo por categoria (era assim que um clipe sobre outra pessoa
    acabava herdando o rosto do apresentador do canal so por a categoria ser "politico/
    pessoa") - agora e sempre uma decisao POR CLIPE, ver `thumbnail.subject.
    select_thumbnail_subject` e o parametro `subject` de `AIThumbnailGenerator.generate`."""

    prompt_template: str


_THUMBNAIL_DEFAULTS_BY_CATEGORY: dict[str, ThumbnailCategoryDefaults] = {
    category_module.POLITICS_PERSON: ThumbnailCategoryDefaults(
        prompt_template=_POLITICS_PERSON_PROMPT_TEMPLATE,
    ),
    category_module.GAMING: ThumbnailCategoryDefaults(
        prompt_template=_GAMING_PROMPT_TEMPLATE,
    ),
    category_module.BOOK_AUDIOBOOK: ThumbnailCategoryDefaults(
        prompt_template=_BOOK_AUDIOBOOK_PROMPT_TEMPLATE,
    ),
}


def build_thumbnail_generator(
    category: str = category_module.DEFAULT_CATEGORY,
    client_factory: Callable[[], Any] | None = None,
    model: str = MODEL_ID,
) -> AIThumbnailGenerator:
    """Fabrica o gerador ja configurado com o template e a paleta certos pra categoria -
    e o jeito recomendado de construir `AIThumbnailGenerator` fora de teste (quem precisar
    de um template customizado continua livre pra instanciar `AIThumbnailGenerator(...)`
    direto). Referencia facial nao entra aqui: e passada por clipe via `generate(subject=...)`."""
    defaults = _THUMBNAIL_DEFAULTS_BY_CATEGORY[category_module.validate_category(category)]
    return AIThumbnailGenerator(
        client_factory=client_factory,
        model=model,
        prompt_template=defaults.prompt_template,
    )
