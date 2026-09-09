"""Composicao da thumbnail: `compose()` gera via Gemini (unica via usada pelo pipeline hoje,
ver decisao abaixo). `compose_layered()` e a composicao antiga em camadas (fundo tratado +
recorte da pessoa + headline + destaque, tudo em Pillow) - nao e mais chamada
automaticamente, existe como caminho explicito caso um modo sem-IA volte a ser oferecido.

A headline vem do LLM de metadados (`ClipMetadata.thumbnail_headline`) e e um gancho, nunca
a fala literal que ja aparece na legenda queimada do video.

Decisao do projeto: `compose()` NAO cai mais pra `compose_layered()` quando o Gemini falha
ou esta indisponivel. Levanta `ThumbnailError` (ver `AIThumbnailGenerator.generate`) e a
etapa "thumbnail" desse clipe falha visivelmente (`ClipStageError` em `clipador.pipeline`,
que isola a falha sem derrubar os outros clipes) - uma thumbnail degradada saindo sem
aviso nenhum era pior que o clipe ficar sem thumbnail e marcado como falho.

Dentro de `compose_layered()`, cada sub-etapa (deteccao de rosto, tratamento de fundo,
recorte, texto, destaque) continua opcional por construcao: se qualquer uma falhar, e
pulada com log de warning e a composicao segue - essa degradacao gradual so vale AQUI,
nunca como substituto silencioso da geracao via IA.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from clipador.reframe.models import FaceBox
from clipador.thumbnail.ai_thumbnail import AIThumbnailGenerator
from clipador.thumbnail.background import GeminiBackgroundEditor
from clipador.thumbnail.cutout import PersonCutout
from clipador.thumbnail.face_library import PoliticalFigure

logger = logging.getLogger(__name__)

ARROW = "arrow"
CIRCLE = "circle"
MIN_FONT_SIZE = 16
# Desenha seta/circulo numa tela 4x maior e reduz no fim: ImageDraw nao antialiasa
# formas nativamente, so texto: supersample + resize com LANCZOS e o jeito padrao
# de conseguir borda lisa sem depender de lib grafica extra.
SUPERSAMPLE = 4


@dataclass
class ThumbnailStyle:
    """Aparencia do texto e do elemento de destaque desenhados por cima do frame."""

    text_color: tuple[int, int, int] = (255, 255, 255)
    stroke_color: tuple[int, int, int] = (0, 0, 0)
    # Laranja com contorno preto: padrao de marca fixado pelo usuario (era amarelo) - o
    # contorno preto grosso ja desenhado em cima disso evita o laranja se perder em tom
    # de pele, risco que a pesquisa da sessao apontou pra essa cor especifica.
    accent_color: tuple[int, int, int] = (255, 140, 0)
    font_path: Path | None = None
    # Fracoes da altura da imagem: mantem a composicao igual em qualquer resolucao.
    font_scale: float = 0.13
    margin_scale: float = 0.04
    highlight: str | None = ARROW
    # Faixa escura em gradiente atras do texto: garante leitura do headline em cima de
    # QUALQUER fundo (inclusive banner/marca d'agua ja queimados no video original),
    # independente do que o tratamento de fundo (Gemini ou fallback) devolveu.
    text_band_frac: float = 0.30


class ThumbnailComposer:
    """Monta a imagem final a partir do frame escolhido pelo ranker."""

    def __init__(
        self,
        cutout: PersonCutout | None = None,
        background_editor: GeminiBackgroundEditor | None = None,
        face_detector: Any | None = None,
        style: ThumbnailStyle | None = None,
        ai_generator: AIThumbnailGenerator | None = None,
    ) -> None:
        self.cutout = cutout or PersonCutout()
        self.background_editor = background_editor or GeminiBackgroundEditor()
        self.face_detector = face_detector
        self.style = style or ThumbnailStyle()
        # Geracao completa via IA (fundo+texto+seta numa chamada so): unico caminho de
        # `compose()`, sem fallback pra composicao em camadas (ver decisao no topo do
        # modulo).
        self.ai_generator = ai_generator or AIThumbnailGenerator()

    def compose(
        self,
        frame_path: str | Path,
        headline: str,
        aspect_ratio: str = "9:16",
        subject: PoliticalFigure | None = None,
    ) -> Image.Image:
        """Levanta `ThumbnailError` (propagada de `AIThumbnailGenerator.generate`) se o
        Gemini nao gerar a imagem - sem fallback, ver decisao no topo do modulo."""
        frame_path = Path(frame_path)
        base = Image.open(frame_path).convert("RGB")
        image = self.ai_generator.generate(base, headline, aspect_ratio, subject=subject)
        return image.convert("RGB")

    def compose_layered(
        self,
        frame_path: str | Path,
        headline: str,
    ) -> Image.Image:
        """Composicao antiga em camadas, sem IA. Nao chamada por `compose()` (ver decisao
        no topo do modulo); existe como caminho explicito."""
        frame_path = Path(frame_path)
        base = Image.open(frame_path).convert("RGB")
        face = self._detect_face(base)
        canvas = self._treated_background(base)
        canvas = self._paste_person(canvas, frame_path)
        canvas = self._draw_headline(canvas, headline, face)
        return self._draw_highlight(canvas, face)

    def _detect_face(self, image: Image.Image) -> FaceBox | None:
        if self.face_detector is None:
            return None
        try:
            import numpy as np

            # O detector segue a convencao do OpenCV (BGR); PIL entrega RGB.
            frame = np.asarray(image)[:, :, ::-1]
            faces = self.face_detector.detect_faces(frame)
            return max(faces, key=lambda box: box.area) if faces else None
        except Exception as exc:
            logger.warning("Deteccao de rosto na thumbnail falhou (%s); seguindo sem rosto.", exc)
            return None

    def _treated_background(self, base: Image.Image) -> Image.Image:
        try:
            treated = self.background_editor.edit(base)
            if treated.size != base.size:
                treated = treated.resize(base.size)
            return treated.convert("RGB")
        except Exception as exc:
            logger.warning("Tratamento do fundo falhou (%s); usando o frame original.", exc)
            return base

    def _paste_person(self, canvas: Image.Image, frame_path: Path) -> Image.Image:
        try:
            person = self.cutout.cut(frame_path)
            if person is None:
                return canvas
            if person.size != canvas.size:
                person = person.resize(canvas.size)
            canvas.paste(person, (0, 0), person)
            return canvas
        except Exception as exc:
            logger.warning("Colagem do recorte da pessoa falhou (%s); seguindo sem ela.", exc)
            return canvas

    def _font(self, size: int) -> Any:
        font_path = self.style.font_path
        if font_path is not None and Path(font_path).is_file():
            try:
                return ImageFont.truetype(str(font_path), size)
            except OSError as exc:
                logger.info("Fonte %s ilegivel (%s); usando a fonte default.", font_path, exc)
        return ImageFont.load_default(size=size)

    def _fit_font(self, draw: ImageDraw.ImageDraw, text: str, canvas: Image.Image) -> tuple[Any, int]:
        """Maior fonte que ainda cabe na largura da imagem, para a headline nunca ser cortada."""
        max_width = canvas.width - 2 * int(canvas.height * self.style.margin_scale)
        size = max(MIN_FONT_SIZE, int(canvas.height * self.style.font_scale))
        while True:
            font = self._font(size)
            stroke_width = max(2, int(size * 0.12))
            left, _, right, _ = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_width)
            if right - left <= max_width or size <= MIN_FONT_SIZE:
                return font, stroke_width
            size = max(MIN_FONT_SIZE, int(size * 0.9))

    def _headline_position(self, canvas: Image.Image, face: FaceBox | None) -> str:
        """'bottom' por padrao (padrao de marca fixado pelo usuario: titulo sempre embaixo);
        'top' so quando o proprio rosto ja ocupa a base da imagem."""
        if face is not None and (face.y + face.height) > canvas.height * 0.78:
            return "top"
        return "bottom"

    def _draw_scrim(self, canvas: Image.Image, position: str) -> Image.Image:
        """Faixa preta em gradiente (mais escura na borda, transparente pro centro) atras
        do texto - garante contraste do headline independente do fundo por baixo."""
        band_h = max(1, int(canvas.height * self.style.text_band_frac))
        y0 = canvas.height - band_h if position == "bottom" else 0

        gradient = Image.new("L", (1, band_h), 0)
        for y in range(band_h):
            t = (y / band_h) if position == "bottom" else ((band_h - y) / band_h)
            gradient.putpixel((0, y), int(200 * (t**1.6)))
        gradient = gradient.resize((canvas.width, band_h))

        region = canvas.crop((0, y0, canvas.width, y0 + band_h))
        black = Image.new("RGB", region.size, (0, 0, 0))
        canvas.paste(Image.composite(black, region, gradient), (0, y0))
        return canvas

    def _draw_headline(
        self, canvas: Image.Image, headline: str, face: FaceBox | None
    ) -> Image.Image:
        text = (headline or "").strip().upper()
        if not text:
            return canvas

        try:
            position = self._headline_position(canvas, face)
            canvas = self._draw_scrim(canvas, position)

            draw = ImageDraw.Draw(canvas)
            font, stroke_width = self._fit_font(draw, text, canvas)
            left, top, right, bottom = draw.textbbox(
                (0, 0), text, font=font, stroke_width=stroke_width
            )
            margin = int(canvas.height * self.style.margin_scale)

            x = (canvas.width - (right - left)) // 2 - left
            y = (margin - top) if position == "top" else (canvas.height - margin - (bottom - top) - top)

            draw.text(
                (x, y),
                text,
                font=font,
                fill=self.style.text_color,
                stroke_width=stroke_width,
                stroke_fill=self.style.stroke_color,
            )
            return canvas
        except Exception as exc:
            logger.warning("Escrita da headline falhou (%s); thumbnail sem texto.", exc)
            return canvas

    def _composite_with_shadow(
        self, canvas: Image.Image, layer: Image.Image, offset: tuple[int, int], blur: int
    ) -> None:
        """Cola `layer` (RGBA) sobre `canvas` (RGB) com uma sombra desfocada por baixo -
        e o que da o efeito de "sticker" das setas/destaques de thumbnail de creator."""
        alpha = layer.split()[-1]
        shadow_alpha = alpha.filter(ImageFilter.GaussianBlur(blur))
        black = Image.new("RGB", canvas.size, (0, 0, 0))
        canvas.paste(black, offset, shadow_alpha)
        canvas.paste(layer.convert("RGB"), (0, 0), alpha)

    def _draw_highlight(self, canvas: Image.Image, face: FaceBox | None) -> Image.Image:
        if face is None or self.style.highlight is None:
            return canvas

        try:
            layer = (
                self._render_circle_layer(canvas.size, face)
                if self.style.highlight == CIRCLE
                else self._render_arrow_layer(canvas.size, face)
            )
            self._composite_with_shadow(canvas, layer, offset=(5, 7), blur=6)
            return canvas
        except Exception as exc:
            logger.warning("Elemento de destaque falhou (%s); thumbnail sem destaque.", exc)
            return canvas

    def _render_circle_layer(self, size: tuple[int, int], face: FaceBox) -> Image.Image:
        big = Image.new("RGBA", (size[0] * SUPERSAMPLE, size[1] * SUPERSAMPLE), (0, 0, 0, 0))
        draw = ImageDraw.Draw(big)
        pad = face.width * 0.25
        box = [
            ((face.x - pad) * SUPERSAMPLE, (face.y - pad) * SUPERSAMPLE),
            (
                (face.x + face.width + pad) * SUPERSAMPLE,
                (face.y + face.height + pad) * SUPERSAMPLE,
            ),
        ]
        width = max(6, int(size[1] * 0.012)) * SUPERSAMPLE
        # contorno preto por baixo, mais largo, depois a cor de destaque por cima e mais
        # fina - e o "stroke" que da o acabamento solido de sticker, nao uma linha crua.
        draw.ellipse(box, outline=(0, 0, 0, 255), width=width + int(width * 0.6))
        draw.ellipse(box, outline=(*self.style.accent_color, 255), width=width)
        return big.resize(size, Image.LANCZOS)

    def _arrow_endpoints(
        self, size: tuple[int, int], face: FaceBox
    ) -> tuple[tuple[float, float], tuple[float, float]]:
        """Sai de um canto superior (o mais longe do rosto) em diagonal ate a altura dos
        olhos - padrao de thumbnail de creator (seta "de fora pra dentro"), nao uma linha
        reta na lateral do rosto (isso apontava pra orelha, sem indicar nada de verdade)."""
        margin = size[0] * 0.05
        target_y = face.y + face.height * 0.35
        space_left = face.x
        space_right = size[0] - (face.x + face.width)

        if space_left >= space_right:
            tail = (margin, size[1] * 0.08)
            tip = (face.x - face.width * 0.12, target_y)
        else:
            tail = (size[0] - margin, size[1] * 0.08)
            tip = (face.x + face.width * 1.12, target_y)
        return tail, tip

    def _render_arrow_layer(self, size: tuple[int, int], face: FaceBox) -> Image.Image:
        tail, tip = self._arrow_endpoints(size, face)
        big = Image.new("RGBA", (size[0] * SUPERSAMPLE, size[1] * SUPERSAMPLE), (0, 0, 0, 0))
        draw = ImageDraw.Draw(big)

        t_tail = (tail[0] * SUPERSAMPLE, tail[1] * SUPERSAMPLE)
        t_tip = (tip[0] * SUPERSAMPLE, tip[1] * SUPERSAMPLE)
        # curva suave via bezier quadratica (sem lib extra): ponto de controle deslocado
        # pra cima do meio do segmento, uma seta reta lisa e o que ficava "sem graca".
        control = (
            (t_tail[0] + t_tip[0]) / 2,
            (t_tail[1] + t_tip[1]) / 2 - size[1] * 0.06 * SUPERSAMPLE,
        )
        points = [_quadratic_bezier(t_tail, control, t_tip, i / 24) for i in range(25)]

        width = max(6, int(size[1] * 0.014)) * SUPERSAMPLE
        outline_width = width + int(width * 0.6)
        accent = (*self.style.accent_color, 255)
        draw.line(points, fill=(0, 0, 0, 255), width=outline_width, joint="curve")
        draw.line(points, fill=accent, width=width, joint="curve")

        head_len = max(18, size[1] * 0.045) * SUPERSAMPLE
        direction = _direction(points[-2], points[-1])
        _draw_arrow_head(draw, points[-1], direction, head_len * 1.25, (0, 0, 0, 255))
        _draw_arrow_head(draw, points[-1], direction, head_len, accent)

        return big.resize(size, Image.LANCZOS)


def _quadratic_bezier(
    p0: tuple[float, float], p1: tuple[float, float], p2: tuple[float, float], t: float
) -> tuple[float, float]:
    x = (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t**2 * p2[0]
    y = (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t**2 * p2[1]
    return (x, y)


def _direction(p_from: tuple[float, float], p_to: tuple[float, float]) -> tuple[float, float]:
    dx, dy = p_to[0] - p_from[0], p_to[1] - p_from[1]
    length = max(1e-6, math.hypot(dx, dy))
    return (dx / length, dy / length)


def _draw_arrow_head(
    draw: ImageDraw.ImageDraw,
    tip: tuple[float, float],
    direction: tuple[float, float],
    length: float,
    fill: tuple[int, int, int, int],
) -> None:
    angle = math.atan2(direction[1], direction[0])
    spread = math.radians(28)
    p1 = (tip[0] - length * math.cos(angle - spread), tip[1] - length * math.sin(angle - spread))
    p2 = (tip[0] - length * math.cos(angle + spread), tip[1] - length * math.sin(angle + spread))
    draw.polygon([tip, p1, p2], fill=fill)
