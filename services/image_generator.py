"""
Generate carousel slide images using Gemini REST API directly.
Uses requests (same approach as gmb.py) to avoid SDK version conflicts.
"""
import os
import io
import base64
from pathlib import Path
import requests
from PIL import Image

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
_MODELS = [
    "gemini-3-pro-image-preview",
    "gemini-2.0-flash-preview-image-generation",
]


def _gen(prompt: str) -> tuple:
    """Returns (Image, model_used)."""
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseModalities": ["IMAGE", "TEXT"]},
    }
    last_err = "no models tried"
    for model in _MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
        try:
            resp = requests.post(url, json=body, timeout=120)
            data = resp.json()
            if "error" in data:
                last_err = data["error"].get("message", str(data["error"]))
                print(f"[image_gen] {model} failed: {last_err[:120]}")
                continue
            for cand in data.get("candidates", []):
                for part in cand.get("content", {}).get("parts", []):
                    b64 = part.get("inlineData", {}).get("data", "")
                    if b64:
                        print(f"[image_gen] SUCCESS using {model}")
                        return Image.open(io.BytesIO(base64.b64decode(b64))), model
            last_err = "no image in response"
            print(f"[image_gen] {model}: no image in response")
        except Exception as e:
            last_err = str(e)
            print(f"[image_gen] {model} exception: {last_err[:120]}")
    raise RuntimeError(f"Gemini image generation failed: {last_err}")


def generate_slide(prompt: str, output_path: str) -> str:
    """Generate a single slide image and save to output_path. Returns the path."""
    img, model_used = _gen(prompt)
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


# ── Inspiration 6 prompt builders — Split-Screen "Country Has Place" style ─────
# Modeled after @luxuryvacations_abroad's high-engagement carousel format:
# - Cover: hook headline + iconic single destination photo
# - Inner: SPLIT-SCREEN 50/50 — two destinations per slide, each labeled "[COUNTRY] Has [PLACE]"
# - CTA: dark gradient + yellow highlight box + WhatsApp number

def insp6_cover_prompt(data: dict) -> str:
    return f"""Portrait 1080×1350px Instagram carousel cover slide. High-engagement vibrant travel design.

BACKGROUND: Full-bleed ultra-photorealistic cinematic photo of {data['photo_direction']}. Vivid saturated colors — turquoise water, vibrant skies, lush greens. Aspirational tropical/iconic travel destination. National Geographic quality, dynamic composition.

OVERLAY: Subtle dark gradient TOP 40% only — heavier at top, fading to fully transparent at the photo's lower half.

TOP-RIGHT: small clean "Dream World Tours" pill badge, semi-transparent white background, dark teal #0c6980 text.

HEADLINE — centered or top-left, very large bold white sans-serif with HIGHLIGHTED key words:
- Background of key phrase has a solid YELLOW (#FFEB3B) highlight rectangle behind it (like a marker highlight effect)
- Large bold white text on yellow: "{data['headline_line_1']}"
- Below in plain bold white (no highlight): "{data['headline_line_2']}"
- Below smaller plain bold white: "{data.get('headline_line_3', '')}"

Below headline: small white regular text: "{data['subtitle']}"

BOTTOM-RIGHT: small white text "Swipe to discover →" in italic

NO clutter. Bold, vibrant, scroll-stopping. Portrait 1080×1350px. High-fidelity rendered text. Modern Instagram travel aesthetic."""


def insp6_paired_inner_prompt(data: dict) -> str:
    """Split-screen inner slide showing 2 destinations stacked vertically.
    Required keys: top_country, top_place, top_photo, bottom_country, bottom_place, bottom_photo, slide_counter
    """
    return f"""Portrait 1080×1350px Instagram carousel inner slide. Split-screen 2-destination vibrant travel design.

LAYOUT: Vertical 50/50 split — TOP HALF (540px) and BOTTOM HALF (540px), each a full-bleed photo. NO gap between halves — touching edges directly.

TOP HALF (upper 540px):
- Full-bleed ultra-photorealistic cinematic photo: {data['top_photo']}. Vivid saturated colors, scroll-stopping composition.
- BOTTOM-CENTER text overlay (anchored to lower portion of the top half):
  - YELLOW (#FFEB3B) bold large sans-serif: "{data['top_country']}"
  - immediately followed by WHITE bold same-size text: "Has {data['top_place']}"
  - All on one line, centered. Yellow country + space + white place.
  - Text should have subtle dark shadow for readability over photo.

BOTTOM HALF (lower 540px):
- Full-bleed ultra-photorealistic cinematic photo: {data['bottom_photo']}. Vivid saturated colors, equally striking composition.
- BOTTOM-CENTER text overlay (anchored to lower portion of the bottom half):
  - YELLOW (#FFEB3B) bold large sans-serif: "{data['bottom_country']}"
  - immediately followed by WHITE bold same-size text: "Has {data['bottom_place']}"
  - All on one line, centered, same shadow treatment.

TOP-RIGHT corner of overall image: small dark pill badge with "{data['slide_counter']}" white text — semi-transparent dark fill.
TOP-RIGHT corner: small "Dream World Tours" branding pill in white text on semi-transparent dark fill — positioned just below the slide counter or beside it.

NO border between the two halves. NO extra text. NO destination descriptions. Just country + iconic place per half. Portrait 1080×1350px. High-fidelity text. Bold vibrant travel poster style."""


# ── Inspiration 7 prompt builders — Cinematic Yellow-Accent Storytelling ──────
# Modeled after @luxuryvacations_abroad's "Top Spiritual Places in India 2026" carousel
# (707 likes, 146 shares — strong engagement).
# Key signature:
# - Single destination per slide (NOT split-screen)
# - Bottom-anchored text block
# - Yellow accent on destination/key words, white descriptor below
# - Cinematic dark/moody full-bleed photography
# - Marker-style yellow highlight on a key word in the cover headline

def insp7_cover_prompt(data: dict) -> str:
    return f"""Portrait 1080×1350px Instagram carousel cover slide. Cinematic dramatic storytelling design.

BACKGROUND: Full-bleed ultra-photorealistic cinematic photo of {data['photo_direction']}. DARK MOODY atmosphere — golden hour, candle-lit, evening, or low-light dramatic lighting. Rich saturated colors with deep shadows. Editorial National Geographic quality.

OVERLAY: NO gradient at top. Subtle dark gradient ONLY at bottom 40% — barely-there to ensure text legibility. Photo dominates the entire frame.

TOP-RIGHT corner: Small "Dream World Tours" pill badge — semi-transparent white background with dark teal #0c6980 text.

BOTTOM TEXT BLOCK (anchored at lower portion of image, left-aligned, generous bottom margin):
- Large bold white uppercase sans-serif (NOT condensed, standard width): "{data['headline_line_1']}"
- Next line, same style: "{data.get('headline_line_2', '')}"
- Highlighted segment within the headline: the word "{data.get('highlight_word', 'INDIA')}" appears with a SOLID YELLOW (#FFEB3B) rectangle background behind it, with the word in DARK NAVY/BLACK text on the yellow — marker highlight effect, like a physical text highlighter
- The highlight should sit inline within the line of text, not as a separate badge

NO subtitle, NO description, NO CTAs on the cover — just the title with marker highlight.

Editorial cinematic. Bold scroll-stopping. Portrait 1080×1350px. High-fidelity rendered text."""


def insp7_inner_prompt(data: dict) -> str:
    return f"""Portrait 1080×1350px Instagram carousel inner slide. Cinematic single-destination design.

BACKGROUND: Full-bleed ultra-photorealistic cinematic photo of {data['photo_direction']}. Vivid rich colors, dramatic composition, golden hour or dramatic lighting. Editorial National Geographic quality.

OVERLAY: Subtle dark gradient ONLY at bottom 35% — gentle, ensures text readability without obscuring photo.

TOP-RIGHT corner area:
- Small slide counter pill — dark semi-transparent fill: "{data['slide_counter']}" white text small
- Below or beside it: tiny "Dream World Tours" branding pill — same dark fill, white text

BOTTOM TEXT BLOCK (anchored at lower portion of image, centered horizontally):
- YELLOW (#FFEB3B) large bold uppercase sans-serif (NOT condensed): "{data['destination_name']}"
- Subtle dark text shadow for legibility against varied backgrounds
- Below in WHITE smaller regular sans-serif (NOT italic), centered, 2 lines max: "{data['descriptor']}"
- White text also with subtle dark shadow

NO destination subtitle, NO city/state line, NO emojis. Just the bold yellow destination name + white descriptor.

Cinematic editorial storytelling. Bold visual hierarchy. Portrait 1080×1350px. High-fidelity rendered text."""


def insp7_cta_prompt(data: dict) -> str:
    return f"""Portrait 1080×1350px Instagram carousel final CTA slide. Cinematic conversion-focused design.

BACKGROUND: Full-bleed ultra-photorealistic cinematic photo of {data['photo_direction']}. Dramatic golden hour or moody lighting. Editorial quality.

OVERLAY: Dark gradient covering BOTTOM 55% — heavier toward the bottom, fading transparent at the middle.

TOP-RIGHT: Small "Dream World Tours" pill badge — semi-transparent white background with teal #0c6980 text.

BOTTOM TEXT BLOCK (anchored at lower portion, left-aligned):
- Bold white uppercase sans-serif: "{data['hook_line_1']}"
- Same line continuing OR next line, same style: "{data.get('hook_line_2', '')}"
- Within these lines, the word "{data.get('highlight_word', 'TODAY')}" gets the YELLOW MARKER highlight (solid yellow #FFEB3B rectangle behind, dark navy text on yellow) — same marker-highlighter style as the cover
- Below in WHITE regular smaller text: "{data['save_prompt']}"

BELOW THAT (still in bottom block):
- A thin yellow horizontal line OR a small yellow CTA-style text: "WhatsApp us at {data['contact_phone']} →"
- Tiny white text below: "dreamworldtours.in"

NO clutter. Yellow marker highlight is the focal point. Portrait 1080×1350px. High-fidelity rendered text."""


def insp6_cta_prompt(data: dict) -> str:
    return f"""Portrait 1080×1350px Instagram carousel final CTA slide. Vibrant high-conversion travel design.

BACKGROUND: Full-bleed ultra-photorealistic cinematic photo of {data['photo_direction']}. Vivid saturated colors, aspirational iconic travel scene.

OVERLAY: Dark gradient covering TOP 50% — heavier at the very top fading to transparent at the middle.

TOP-RIGHT: small "Dream World Tours" pill badge — semi-transparent white background with teal #0c6980 text.

CENTERED in upper portion of image:
- YELLOW (#FFEB3B) solid highlight rectangle with bold large dark navy text: "{data['hook_line_1']}"
- Below in plain bold large WHITE text (no highlight): "{data['hook_line_2']}"
- Below in plain bold medium WHITE text: "{data['hook_line_3']}"

BELOW THAT (centered):
- A yellow-bordered transparent box (1080×~90px) — yellow #FFEB3B border 3px, no fill
- Inside the box in white text, centered: "Call or WhatsApp us at {data['contact_phone']} For Details"

BOTTOM-CENTER: very small white text: "dreamworldtours.in · @dreamworldtours_"

NO clutter. Bold, vibrant, conversion-focused. Yellow highlight + yellow-bordered box are the visual focal points. Portrait 1080×1350px. High-fidelity rendered text."""
