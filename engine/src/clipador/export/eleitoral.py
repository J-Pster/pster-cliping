"""Tarja de propaganda eleitoral: texto rotacionado, pequeno, junto de uma borda lateral
do clipe, nos dois formatos (curto 9:16 e longo 16:9).

Isto renderiza so a IMAGEM (PNG transparente do tamanho do quadro). A sobreposicao no
video em si reusa `WatermarkOverlay.apply` (mesmo `export/watermark.py`), que ja faz
exatamente o ffmpeg de "PNG por cima do video inteiro, escalado/padded pra resolucao real
do clipe" - nao ha ffmpeg novo aqui, so o Pillow que desenha o PNG. `render_disclaimer_image`
e chamada uma vez por formato (o quadro curto e o longo tem proporcao diferente, entao a
tarja de cada um e uma imagem separada), sempre na borda direita do quadro.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from clipador.subtitles.fonts import DEFAULT_FONTS_DIR, font_file_for

FONT_NAME = "Montserrat ExtraBold"
FONT_SIZE = 10
# Padding entre o texto rotacionado e a borda da tarja, dos dois lados perpendiculares
# ao texto (topo/base do texto original, que viram esquerda/direita da tarja apos girar).
BAR_PADDING = 8
# Preto semi-opaco (nao 100% opaco) por baixo do texto branco: garante legibilidade sobre
# QUALQUER fundo de video, inclusive um fundo claro onde o texto branco sozinho sumiria.
BAR_ALPHA = 160


def render_disclaimer_image(
    text: str,
    output_path: Path,
    *,
    frame_width: int = 1080,
    frame_height: int = 1920,
    fonts_dir: Path | str = DEFAULT_FONTS_DIR,
) -> Path:
    """PNG RGBA do tamanho do quadro com a tarja de aviso na borda direita, ou totalmente
    transparente quando `text` e vazio/so espaco (sem tarja nenhuma) - assim o chamador
    pode chamar isto incondicionalmente sem checar o texto antes."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas = Image.new("RGBA", (frame_width, frame_height), (0, 0, 0, 0))

    stripped = text.strip()
    if not stripped:
        canvas.save(output_path)
        return output_path

    font_path = font_file_for(FONT_NAME, fonts_dir)
    font = ImageFont.truetype(str(font_path), FONT_SIZE)

    # Mede o texto num draw descartavel antes de saber o tamanho da imagem que vai
    # contê-lo: o bbox inclui o offset de ascenders/descenders, que precisa ser anulado
    # (deslocando o desenho por -left/-top) pra o glifo nao cortar na borda da imagem.
    measurer = ImageDraw.Draw(canvas)
    left, top, right, bottom = measurer.textbbox((0, 0), stripped, font=font)
    text_width = right - left
    text_height = bottom - top

    text_layer = Image.new("RGBA", (text_width, text_height), (0, 0, 0, 0))
    ImageDraw.Draw(text_layer).text((-left, -top), stripped, font=font, fill=(255, 255, 255, 255))

    # ROTATE_90 gira sentido anti-horario (a base do texto original fica virada para a
    # direita da tarja): o aviso passa a se ler de baixo para cima ao longo da lateral.
    rotated = text_layer.transpose(Image.ROTATE_90)

    bar_width = rotated.width + 2 * BAR_PADDING
    bar_height = frame_height
    bar = Image.new("RGBA", (bar_width, bar_height), (0, 0, 0, BAR_ALPHA))

    bar_x = frame_width - bar_width
    canvas.alpha_composite(bar, (bar_x, 0))

    text_x = bar_x + (bar_width - rotated.width) // 2
    text_y = (bar_height - rotated.height) // 2
    canvas.alpha_composite(rotated, (text_x, text_y))

    canvas.save(output_path)
    return output_path
