"""
Generate carousel slide images using Gemini API.
Replicates the nano-banana MCP tool behaviour directly.
"""
import os
import io
import base64
from pathlib import Path
import google.generativeai as genai
from PIL import Image

genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

MODEL = "gemini-2.0-flash-preview-image-generation"


def _gen(prompt: str) -> Image.Image:
    model = genai.GenerativeModel(MODEL)
    response = model.generate_content(
        contents=prompt,
        generation_config=genai.GenerationConfig(
            response_modalities=["IMAGE", "TEXT"],
        ),
    )
    for part in response.candidates[0].content.parts:
        if hasattr(part, "inline_data") and part.inline_data:
            return Image.open(io.BytesIO(part.inline_data.data))
    raise RuntimeError("Gemini returned no image")


def generate_slide(prompt: str, output_path: str) -> str:
    """Generate a single slide image and save to output_path. Returns the path."""
    img = _gen(prompt)
    # Resize to exactly 1080×1350 if needed
    if img.size != (1080, 1350):
        img = img.resize((1080, 1350), Image.LANCZOS)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path, "PNG")
    return output_path


# ── Inspiration 4 prompt builders ──────────────────────────────────────────

def insp4_cover_prompt(data: dict) -> str:
    return f"""Portrait 1080×1350px Instagram carousel cover slide. Premium sophisticated editorial design.

BACKGROUND: Full-bleed cinematic aerial/scenic photo: {data['photo_direction']}. Vivid, rich colors, magazine-quality.

OVERLAY: Dark gradient covers TOP 55% — heavier at top, fading to transparent toward lower half.

TOP-LEFT: "@dreamworldtours" very small light white

HEADLINE — left-aligned, very large bold condensed white sans-serif, stacked:
"{data['headline_line_1']}"
"{data['headline_line_2']}"
"{data.get('headline_line_3', '')}"

Below headline: teal #00a8a8 horizontal rule 3px, 80px wide

Below rule: "{data['subtitle']}" small regular white, left-aligned

Bottom-left: "{data['bottom_left']}" small light white
Bottom-right: "Dream World Tours" small clean white

NO boxes, NO badges, NO borders. Clean editorial. Portrait 1080×1350px. High-fidelity text. Professional quality."""


def insp4_inner_prompt(data: dict) -> str:
    loc2 = f'\n"{data["location_line_2"]}"' if data.get("location_line_2") else ""
    return f"""Portrait 1080×1350px Instagram carousel inner slide. Sophisticated editorial travel design.

BACKGROUND: Full-bleed cinematic {data['photo_direction']}. Vivid rich colors.

OVERLAY: Subtle dark gradient BOTTOM 35% ONLY — transparent at top, semi-dark at bottom.

TOP-LEFT: "@dreamworldtours" very small light white
TOP-RIGHT: "{data['slide_counter']}" small clean white light weight

BOTTOM-LEFT text block:
- "{data['location_line_1']}" — very large bold condensed white, left-aligned{loc2}
- "{data['city_state']}" — small teal #00a8a8, light weight
- Short teal rule 3px, 60px
- "{data['descriptor_1']}" — small regular white
- "{data['descriptor_2']}" — small regular white

NO boxes, NO panels, NO badges. Text directly on gradient. Editorial clean. Portrait 1080×1350px. High-fidelity text. Professional quality."""


def insp4_cta_prompt(data: dict) -> str:
    col1 = " / ".join(data.get("items_col_1", []))
    col2 = " / ".join(data.get("items_col_2", []))
    return f"""Portrait 1080×1350px Instagram carousel final CTA slide. Sophisticated editorial travel design.

BACKGROUND: Full-bleed cinematic {data['photo_direction']}. Vivid and dreamy.

OVERLAY: Dark gradient covers TOP 60% — heavier at top, lighter toward bottom.

TOP-LEFT: "@dreamworldtours" very small light white

HEADLINE left-aligned, large bold white:
"{data['question_line_1']}"
"{data['question_line_2']}"

Below: teal #00a8a8 rule 3px, 80px wide
Below rule: "{data['save_prompt']}" small regular white

2-COLUMN LIST small regular white:
Left: {col1}
Right: {col2}

SOLID TEAL #00a8a8 wide pill button centered: "{data['cta_button']}" bold white
Below button: "dreamworldtours.in  |  Dream World Tours" small white centered

NO boxes around text. Editorial clean. Portrait 1080×1350px. High-fidelity text. Professional quality."""


# ── Inspiration 5 prompt builders ──────────────────────────────────────────

def insp5_cover_prompt(data: dict) -> str:
    collage_desc = "; ".join(data.get("cover_collage_photos", []))
    return f"""Portrait 1080×1350px Instagram carousel cover slide. Editorial travel poster design.

BACKGROUND: Off-white textured paper with faint grid/graph paper lines. Warm paper tone #f5f0e8.

Large flat amber/gold circle (45% of image width) center-right, behind the photo collage.

TYPOGRAPHY left-aligned:
- Small amber italic serif: "{data['season_label']}"
- Massive ultra-bold condensed dark charcoal headline:
  "{data['cover_headline_1']}"
  "{data['cover_headline_2']}"
  "{data.get('cover_headline_3', '')}"
- Bold navy condensed smaller: "{data['cover_subhead']}"

PHOTO COLLAGE overlapping amber circle: {collage_desc}. 4–5 photos with natural cutout edges, slightly overlapping, some tilted slightly.

Scattered 6–8 small black bird silhouettes across the image.

Bottom center: "@dreamworldtours" small dark serif text.

NO gradient. NO full-bleed photo background. Raw editorial magazine poster. High-fidelity text. Portrait 1080×1350px."""


def insp5_inner_prompt(data: dict) -> str:
    name2 = f'\n"{data["name_line_2"]}"' if data.get("name_line_2") else ""
    return f"""Portrait 1080×1350px Instagram carousel inner slide. Editorial travel journal design.

BACKGROUND: Full-bleed cinematic {data['photo_direction']}. Vivid. NO gradient overlay — photo fully visible.

TOP-LEFT text block:
- Thin vertical dark charcoal line 3px ~60px tall on left edge
- "{data['name_line_1']}" large bold condensed dark charcoal/near-black, left-aligned — on the lighter sky/bright area{name2}
- "{data['descriptor']}" small regular italic white below name

TOP-RIGHT: "{data.get('slide_counter', '')}" small clean white light-weight

BOTTOM-CENTER: "@dreamworldtours" very small text

NO gradient. NO background box. NO overlay. Text directly on photo natural tones. Editorial raw. High-fidelity text. Portrait 1080×1350px."""


def insp5_cta_prompt(data: dict) -> str:
    return f"""Portrait 1080×1350px Instagram carousel final slide. Editorial travel journal design.

BACKGROUND: Full-bleed cinematic {data['photo_direction']}. Vivid, bright sky at top.

TOP-LEFT text block:
- Thin vertical dark charcoal line 3px ~80px tall on left edge
- "{data['name_line_1']}" large bold condensed dark charcoal, left-aligned
- "{data['name_line_2']}" same style, second line
- "{data['descriptor']}" small regular italic white below

BOTTOM-CENTER: "@dreamworldtours" very small text

NO gradient overlay. NO background box. Editorial raw. High-fidelity text. Portrait 1080×1350px."""
