"""Gerador standalone de logos/brasoes via Gemini Image ("Nano Banana"), separado do
motor de cortes (`engine/`). Roda com o mesmo interpretador Python do motor (ja tem
`google-genai` e `Pillow` instalados):

    ../engine/.venv/Scripts/python generate.py --variant emblema
    ../engine/.venv/Scripts/python generate.py --variant banner
    ../engine/.venv/Scripts/python generate.py --variant emblema --refine "deixe o dourado mais saturado e o contorno branco mais grosso"
    ../engine/.venv/Scripts/python generate.py --compose commit_civico_banner

Le GEMINI_API_KEY de `.env` local se existir, senao cai pro `../engine/.env` (mesma
chave usada pelo motor pra gerar thumbnail). Cada variante e uma unica chamada de imagem
(sem historico entre execucoes); `--refine` reenvia a MESMA variante com uma instrucao de
ajuste extra anexada ao prompt base, nao um chat continuo entre execucoes separadas.

`--compose` NAO usa IA: recompoe a arte original do Commit Civico (references/commit_civico_banner.png)
sobre um fundo branco com grade de pontos, com posicionamento exato via PIL - usado porque o
Gemini nao respeitava a safe zone do YouTube de forma confiavel num canvas 16:9 largo.
"""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from PIL import Image

HERE = Path(__file__).resolve().parent
REFERENCES_DIR = HERE / "references"
OUTPUT_DIR = HERE / "output"

MODEL_ID = "gemini-3.1-flash-image-preview"

# Aspect ratios aceitos pela API do Gemini Image como string literal (nao enum):
# '1:1','1:4','1:8','2:3','3:2','3:4','4:1','4:3','4:5','5:4','8:1','9:16','16:9','21:9'.

BRAND_BLOCK = """Brand identity: this is a military-themed tactical gaming YouTube/Instagram/TikTok channel called "Comando Onca" (a Brazilian channel about military-style video games). Mascot: a jaguar ("onca pintada"), rendered with its natural spotted rosette fur pattern (real jaguar rosettes, NOT stylized icons, brackets or symbols inside the spots). Brand color palette, used strictly: black as the dominant base, white for line-work/highlights/contrast, and a warm amber-gold-orange accent close to hex #ECB405 as the main accent color for the jaguar and metallic trim details. The Brazilian flag (green, blue, yellow, white five-pointed stars) appears as a small heraldic design element integrated into the crest (e.g. a ribbon banner, a small shield insert, or a sash) - keep it small and tasteful, it must never dominate over the black/white/gold palette."""

CREST_DESCRIPTION = """Create a professional military heraldic crest (brasao militar / coat of arms), circular badge or shield-shaped emblem. Central figure: a fierce jaguar, either a three-quarter head portrait or a full body in an alert/pouncing stance, with natural spotted rosette fur. Frame the jaguar with classic military crest elements: a laurel wreath or a pair of stylized tactical wings on the sides, a five-pointed star or two crossed rifles/bayonets above or below as a military motif, a ribbon banner arcing along the bottom rim bearing small Brazilian flag colors. Flat vector illustration style, like a professional esports team crest or military unit patch - NOT photorealistic, NOT 3D render, bold thick clean outlines, sharp geometric shapes, high contrast, must stay legible when shrunk down to a small social media profile picture."""

TEXT_INSTRUCTION = """Text: arc the words "COMANDO ONCA" in a bold condensed all-caps military stencil-style font along the rim of the crest (top or bottom banner), spelled exactly as written, no accents needed, no other text anywhere in the image."""

REFERENCE_STYLE_NOTE = """Style reference: the attached images are the existing brand identity of a sibling channel ("Commit Civico") built by the same creator - study ONLY the flat vector illustration technique, the confident jaguar pose/anatomy, the bold black outline weight, and the black/gold/white color language. Do NOT copy its code-bracket spot pattern, its ">"/cursor icon, or the text "Commit Civico" - this is a DIFFERENT, military-themed brand with its own crest composition described above."""

FIERCE_CREST_DESCRIPTION = """Create a professional military heraldic crest (brasao militar / coat of arms), circular badge or shield-shaped emblem, with a noticeably FIERCER, more aggressive attitude than a standard clean crest. Central figure: a snarling jaguar head or front-facing bust, mouth open baring teeth and fangs, ears pinned back, eyes narrowed and intense, muscles/fur rendered with sharper, more angular, more dynamic linework than a calm heraldic crest - it should read as ready-for-combat, not decorative. Frame it with sharper, more jagged versions of classic military crest elements: torn/tattered ribbon edges instead of a smooth ribbon, angular aggressive wing shapes (like blades) instead of soft feathered wings, a five-pointed star or two crossed rifles/bayonets as a military motif. Flat vector illustration style, like a hardcore tactical esports team crest or special-forces unit patch - NOT photorealistic, NOT 3D render, bold thick clean outlines, sharp aggressive geometric shapes, high contrast, must stay legible when shrunk down to a small social media profile picture."""

BANNER_SAFE_ZONE_MARGIN = """Keep the lockup small and comfortably centered: it should occupy well under three-quarters of the frame's width and under a third of the frame's height, with generous, clearly visible empty space around all four sides of it. Nothing in the lockup should ever come close to touching an edge. This is a finished, polished piece of artwork, exactly like a banner you'd see on a real popular YouTube channel today - plain background art plus the logo lockup, nothing else."""

COMMIT_CIVICO_BRAND_BLOCK = """Brand identity: this is an existing YouTube/Instagram/TikTok channel called "Commit Civico" (tech/dev-culture channel). Mascot: a jaguar ("onca pintada") walking, rendered in a flat geometric vector style where its rosette spots are stylized as code symbols - curly braces {}, parentheses (), small solid squares - plus a white belly/chest highlight, a black lower body/legs, and a small ">" terminal-prompt chevron near the front leg and a black cursor-arrow icon trailing behind the tail. Wordmark "COMMIT CIVICO" in a bold, geometric, tightly-tracked condensed sans-serif, all caps. Color palette strictly: black, white, and a warm amber-gold close to hex #ECB405 for the jaguar body."""

COMMIT_CIVICO_REFERENCE_NOTE = """Reference images attached: these ARE the official existing logo of this exact brand - match them as closely and faithfully as possible (same jaguar illustration, same code-symbol spot pattern, same cursor-arrow tail detail, same wordmark letterforms and weight, same exact colors). This is not inspiration for a new brand, it IS the brand - reproduce it faithfully, just recomposed into the banner layout described below."""

OVERLAY_TEXTURE_BASE = """This is PURE BACKGROUND ART for a live-stream overlay band. Absolutely NO text, NO letters, NO words, NO numbers, NO logo, NO emblem, NO crest, NO badge, NO jaguar face or animal figure, NO icons, NO UI widgets, NO watermark anywhere in the image. Only abstract texture.

Palette, strictly: near-black charcoal (#0B0B0D to #16161A) as the dominant base, with a warm amber-gold accent close to hex #ECB405 used only sparingly as faint rim-light and thin glints. Keep the whole image VERY DARK and VERY LOW CONTRAST: white and gold interface elements will be drawn on top of it and must stay perfectly readable, so nothing in the texture may be bright, busy or attention-grabbing."""

VARIANTS: dict[str, dict[str, Any]] = {
    "overlay_band_bottom": {
        "aspect_ratio": "8:1",
        "filename": "overlay_band_bottom_8x1.png",
        "base_references": False,
        "prompt": f"""Create an extremely wide, short horizontal background texture band for the lower third of a military-themed tactical gaming stream overlay.

{OVERLAY_TEXTURE_BASE}

Texture content: a large-scale jaguar rosette pattern (real spotted jaguar rosettes) rendered as very low-contrast dark-on-dark shapes, blended with angular dark military camouflage facets and a subtle brushed-metal / fine film-grain micro texture. Dramatic but restrained side lighting from the upper edge, cinematic vignette darkening toward the far left and far right ends of the band, and a faint warm amber glow bleeding down from the top edge as if light spills from the screen above. Composition must stay flat and even across the full width, with no focal point and no object anyone would read as a subject.""",
    },
    "overlay_band_top": {
        "aspect_ratio": "8:1",
        "filename": "overlay_band_top_8x1.png",
        "base_references": False,
        "prompt": f"""Create an extremely wide, short horizontal background texture strip to be used as a thin header bar above gameplay footage in a military-themed tactical gaming stream overlay.

{OVERLAY_TEXTURE_BASE}

Texture content: dark brushed gunmetal with fine horizontal machining lines, overlaid with a very faint large-scale jaguar rosette pattern and angular dark camouflage facets, plus a subtle warm amber sheen running along the horizontal center as a soft specular highlight. The design must read correctly when only a thin horizontal slice through the middle of this image is used, so keep the texture uniform top to bottom, with no composition that depends on the upper or lower portion of the frame.""",
    },
    "commit_civico_banner": {
        "aspect_ratio": "16:9",
        "filename": "commit_civico_banner_16x9.png",
        "prompt": f"""Create a YouTube channel banner (16:9 widescreen, exported at 2560x1440) for the existing brand described below. The background MUST be WHITE / very light - this brand's identity is a white background with a black wordmark and a gold-and-black jaguar, exactly like the reference logo images attached. Do not use a dark or black background under any circumstance, that is the wrong brand look for this channel.

The jaguar mascot and the full "COMMIT CIVICO" wordmark, with no letters cut off, need to read clearly even when only the very middle strip of this banner is visible (that's how YouTube shows it on phones), so keep them grouped together right in the middle of the frame, well clear of the top, bottom, left and right edges. Use a COMPACT HORIZONTAL LOCKUP: the walking jaguar mascot on the left, and the "COMMIT CIVICO" wordmark to its right on the same horizontal line, both vertically centered together, wordmark in solid BLACK (matching the reference logo's black text, NOT white text - white text would be invisible on this white background). {BANNER_SAFE_ZONE_MARGIN} Be strict about this: the whole lockup, measured from the tip of the jaguar's nose or the tip of its tail (whichever sticks out further) all the way to the last letter of "CIVICO", must span no more than 45% of the full canvas width, horizontally centered, so there is at least about a quarter of the canvas width left empty as background on each side of the lockup. This is a WIDE banner, not a square logo - the jaguar and wordmark need to be rendered noticeably SMALLER, relative to the canvas, than they appear in the attached square reference logo images. Make the lockup much smaller than your first instinct - it is far better to leave generous open background on both sides than to risk any part touching the left or right edge region.

{COMMIT_CIVICO_BRAND_BLOCK}

{COMMIT_CIVICO_REFERENCE_NOTE}

Background: keep it WHITE, matching the reference logo exactly - but make it an actual designed banner instead of a flat empty stretch: add a very subtle, barely-visible light-grey pattern across the white (faint thin monospace code lines, or a faint dot/grid pattern) so it has a touch of texture and depth, staying light and airy overall, never competing with the black wordmark or the gold/black jaguar for attention, and never darkening the overall canvas. Do not place any dark panel, box or rectangle behind the jaguar or the wordmark - they sit directly on the white/light background. Wide cinematic 16:9 composition, professional YouTube channel banner quality.""",
    },
    "emblema": {
        "aspect_ratio": "1:1",
        "filename": "comando_onca_emblema_1x1.png",
        "prompt": f"""{CREST_DESCRIPTION}

{TEXT_INSTRUCTION}

{BRAND_BLOCK}

{REFERENCE_STYLE_NOTE}

Composition: crest centered with even padding on all sides, background a solid flat dark color (near-black) with no scene, gradient clutter or texture behind it, so it works cleanly as a profile picture for Instagram, TikTok and YouTube (channel icon, avatar) and as a stamped logo on post graphics. Square 1:1 format.""",
    },
    "emblema_feroz": {
        "aspect_ratio": "1:1",
        "filename": "comando_onca_emblema_feroz_1x1.png",
        "prompt": f"""{FIERCE_CREST_DESCRIPTION}

{TEXT_INSTRUCTION}

{BRAND_BLOCK}

{REFERENCE_STYLE_NOTE}

Composition: crest centered with even padding on all sides. Background: NOT a flat solid color this time - instead the same dark tactical banner treatment used for this brand's YouTube banner: dark charcoal-black backdrop with a subtle low-contrast jaguar rosette pattern or camouflage-inspired texture, dramatic side lighting, cinematic vignette toward the edges, decluttered, no other logos or watermarks - so this emblem shares the same moody, tactical atmosphere as the channel banner instead of looking flat and isolated. Square 1:1 format, must still stay legible when shrunk down to a small profile picture despite the added background texture (keep the texture subtle/dark enough that the crest always reads clearly on top of it).""",
    },
    "banner": {
        "aspect_ratio": "16:9",
        "filename": "comando_onca_banner_16x9.png",
        "prompt": f"""Create a YouTube channel banner (16:9 widescreen, exported at 2560x1440).

Everything that matters - the jaguar emblem, the "COMANDO ONCA" text, and the small Brazilian flag element - needs to read clearly even when only the very middle strip of this banner is visible (that's how YouTube shows it on phones), so keep it all grouped together right in the middle of the frame, well clear of the top, bottom, left and right edges. Do NOT design a tall stacked circular badge with text below it, that gets too tall to stay centered well. Instead use a COMPACT HORIZONTAL LOCKUP: a small-to-medium circular jaguar crest/badge on the left, with the bold condensed all-caps wordmark "COMANDO ONCA" to its right on the same horizontal line (both vertically centered together, roughly the same height), so the whole lockup is short and wide rather than tall. The small Brazilian flag element sits as a tiny accent right next to or below the wordmark. {BANNER_SAFE_ZONE_MARGIN}

{CREST_DESCRIPTION.replace('circular badge or shield-shaped emblem', 'compact circular badge (this time only the badge itself, smaller and simpler, NOT paired with a separate bottom text ribbon since the wordmark sits beside it instead)')}

{TEXT_INSTRUCTION}

{BRAND_BLOCK}

{REFERENCE_STYLE_NOTE}

Background: dark tactical/military atmosphere - subtle jaguar rosette pattern or camouflage-inspired texture, dramatic side lighting, cinematic vignette, decluttered, no other logos or watermarks. Wide cinematic 16:9 composition.""",
    },
    "banner_v1_recreate": {
        "aspect_ratio": "16:9",
        "filename": "comando_onca_banner_16x9_v1_recreate.png",
        "extra_references": [HERE / "references" / "comando_onca_extra" / "typografia_v1.png"],
        "prompt": f"""Create a YouTube channel banner (16:9 widescreen, exported at 2560x1440).

The LAST attached reference image shows a wordmark typography treatment from an earlier version of this exact banner that the client loved and wants recreated: a two-line stacked wordmark reading "COMANDO" on top and "ONCA" below, in a bold, chunky, military stencil-cutout font (thin gaps inside the letterforms like a real stencil), both words white, sitting on their own dark rounded panel, with a thin gold horizontal bar underneath the panel that has the small Brazilian flag centered on it. Recreate that exact wordmark treatment faithfully - font style, two-line stacking, dark panel backing, gold bar, and flag placement all included.

Everything that matters - the jaguar crest badge on the left and this two-line wordmark lockup on the right - needs to read clearly even when only the very middle strip of this banner is visible (that's how YouTube shows it on phones), so keep it all grouped together right in the middle of the frame, well clear of the top, bottom, left and right edges. {BANNER_SAFE_ZONE_MARGIN}

{CREST_DESCRIPTION.replace('circular badge or shield-shaped emblem', 'compact circular badge (this time only the badge itself, smaller and simpler, NOT paired with a separate bottom text ribbon since the wordmark sits beside it instead)')}

{BRAND_BLOCK}

{REFERENCE_STYLE_NOTE}

Background: dark tactical/military atmosphere - subtle jaguar rosette pattern or camouflage-inspired texture, dramatic side lighting, cinematic vignette, decluttered, no other logos or watermarks. Wide cinematic 16:9 composition.""",
    },
    "banner_alt": {
        "aspect_ratio": "16:9",
        "filename": "comando_onca_banner_16x9_alt.png",
        "prompt": f"""Create a YouTube channel banner (16:9 widescreen, exported at 2560x1440) - an ALTERNATIVE typography concept, deliberately different from a typical stacked two-tone wordmark treatment.

Everything that matters - the jaguar crest badge and the "COMANDO ONCA" text - needs to read clearly even when only the very middle strip of this banner is visible (that's how YouTube shows it on phones), so keep it all grouped together right in the middle of the frame, well clear of the top, bottom, left and right edges. {BANNER_SAFE_ZONE_MARGIN}

Layout: a circular jaguar crest badge on the left, and to its right the words "COMANDO ONCA" on a SINGLE line (not stacked), set in a rugged, slightly distressed/worn military stencil font, entirely in the warm amber-gold accent color (no white, no dark panel backing behind the text - the letters sit directly on the background art), with a subtle worn/scratched texture inside the letterforms for a battle-worn feel. Directly beneath the wordmark, a thin straight line of small Brazilian-flag-colored chevrons or a slim tricolor bar as the only extra accent - keep it minimal, no big panel or box around the text.

{CREST_DESCRIPTION.replace('circular badge or shield-shaped emblem', 'compact circular badge (this time only the badge itself, smaller and simpler, NOT paired with a separate bottom text ribbon since the wordmark sits beside it instead)')}

{BRAND_BLOCK}

{REFERENCE_STYLE_NOTE}

Background: dark tactical/military atmosphere - subtle jaguar rosette pattern or camouflage-inspired texture, dramatic side lighting, cinematic vignette, decluttered, no other logos or watermarks. Wide cinematic 16:9 composition.""",
    },
}


def _load_api_key() -> str:
    load_dotenv(HERE / ".env")
    load_dotenv(HERE.parent / "engine" / ".env")
    import os

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY nao encontrada (nem em logo-generator/.env, nem em engine/.env)."
        )
    return api_key


def _load_reference_images(
    extra_paths: list[Path] | None = None, base_references: bool = True
) -> list[Image.Image]:
    images = []
    if base_references:
        for path in sorted(REFERENCES_DIR.glob("*.png")):
            images.append(Image.open(path).convert("RGB"))
    for path in extra_paths or []:
        images.append(Image.open(path).convert("RGB"))
    return images


def _first_image(response: Any) -> Image.Image | None:
    for candidate in getattr(response, "candidates", None) or []:
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", None) or []:
            inline = getattr(part, "inline_data", None)
            data = getattr(inline, "data", None)
            if data:
                return Image.open(io.BytesIO(data))
    return None


def generate(variant_key: str, refine: str | None, model: str) -> Path:
    variant = VARIANTS[variant_key]
    prompt = variant["prompt"]
    if refine:
        prompt = f"{prompt}\n\nAdditional refinement instruction: {refine}"
    prompt = f"{prompt}\n\nGenerate the image now. Output the finished image directly - do not reply with only a text description of what you would create."

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=_load_api_key())
    config = types.GenerateContentConfig(
        image_config=types.ImageConfig(aspect_ratio=variant["aspect_ratio"])
    )
    chat = client.chats.create(model=model, config=config)
    reference_images = _load_reference_images(
        variant.get("extra_references"), variant.get("base_references", True)
    )
    response = chat.send_message([prompt, *reference_images])

    image = _first_image(response)
    if image is None:
        text = getattr(response, "text", None)
        raise RuntimeError(f"Gemini nao devolveu imagem. Resposta: {text!r}")

    OUTPUT_DIR.mkdir(exist_ok=True)
    out_path = OUTPUT_DIR / variant["filename"]
    image.convert("RGB").save(out_path)
    return out_path


def compose_commit_civico_banner(
    source_logo: Path = REFERENCES_DIR / "commit_civico_banner.png",
    lockup_width_fraction: float = 0.42,
    dot_spacing: int = 48,
    dot_radius: int = 3,
    dot_color: tuple[int, int, int] = (222, 222, 222),
) -> Path:
    """Compoe o banner do Commit Civico via PIL puro, sem IA: usa a arte ORIGINAL da
    marca (fiel, sem risco de a IA distorcer o jaguar ou o texto) sobre um fundo branco
    com uma grade sutil de pontos, posicionada com matematica exata dentro da safe zone
    do YouTube (1546x423 centralizado num canvas 2560x1440) - depois de varias tentativas
    via prompt onde o Gemini insistia em vazar a safe zone ou pesar demais o fundo, esse
    caminho determinista resolveu de primeira."""
    import numpy as np
    from PIL import ImageDraw

    lockup = Image.open(source_logo).convert("RGBA")
    arr = np.array(lockup)
    rgb = arr[:, :, :3].astype(int)
    near_white = rgb.sum(axis=2) > 250 * 3
    mask = ~near_white
    ys, xs = np.where(mask)
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    lockup = lockup.crop((x0, y0, x1 + 1, y1 + 1))
    arr = np.array(lockup)
    rgb = arr[:, :, :3].astype(int)
    arr[:, :, 3] = np.where(rgb.sum(axis=2) > 250 * 3, 0, 255)
    lockup = Image.fromarray(arr, "RGBA")

    width, height = 2560, 1440
    canvas = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(canvas)
    for y in range(dot_spacing, height, dot_spacing):
        for x in range(dot_spacing, width, dot_spacing):
            draw.ellipse((x - dot_radius, y - dot_radius, x + dot_radius, y + dot_radius), fill=dot_color)

    target_w = int(width * lockup_width_fraction)
    scale = target_w / lockup.width
    target_h = int(lockup.height * scale)
    lockup = lockup.resize((target_w, target_h), Image.LANCZOS)

    paste_x = (width - target_w) // 2
    paste_y = (height - target_h) // 2
    canvas = canvas.convert("RGBA")
    canvas.alpha_composite(lockup, (paste_x, paste_y))

    OUTPUT_DIR.mkdir(exist_ok=True)
    out_path = OUTPUT_DIR / "commit_civico_banner_16x9_composed.png"
    canvas.convert("RGB").save(out_path)
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", choices=sorted(VARIANTS))
    parser.add_argument("--refine", default=None, help="Instrucao extra de ajuste, ex: 'deixe o dourado mais saturado'")
    parser.add_argument("--model", default=MODEL_ID)
    parser.add_argument(
        "--compose",
        choices=["commit_civico_banner"],
        help="Compoe o banner via PIL a partir da arte original (sem IA), em vez de gerar via Gemini",
    )
    args = parser.parse_args()

    if args.compose == "commit_civico_banner":
        out_path = compose_commit_civico_banner()
        print(f"Gerado: {out_path}")
        return

    if not args.variant:
        parser.error("--variant e obrigatorio quando --compose nao e usado")

    out_path = generate(args.variant, args.refine, args.model)
    print(f"Gerado: {out_path}")


if __name__ == "__main__":
    main()
