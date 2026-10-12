"""
Marketing Post Generator — single-image WhatsApp/Instagram marketing posts.

Generates square 1080×1080 posts via Gemini image API (gemini-3-pro-image-preview),
uploads to imgbb for permanent URLs, and persists to Postgres via db.save_run().

Inspirations are curated style templates (Editorial Luxury, Cinematic Yellow, etc.).
Each inspiration has a prompt_builder that takes (destination, details) and returns a full Gemini prompt.
"""
import os
import io
import base64
import uuid
from pathlib import Path

import requests
from PIL import Image

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
IMGBB_API_KEY  = os.environ.get("IMGBB_API_KEY")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

# Feature flag: route image-prompt building through the marketing-post-designer
# agent (rich brand context, ~85% better quality) vs. the hardcoded inspiration
# templates. Default ON; set USE_SKILL_PROMPTS=false to revert to templates.
USE_SKILL_PROMPTS = os.environ.get("USE_SKILL_PROMPTS", "true").lower() == "true"

# Locked: nano-banana pro (gemini-3-pro-image-preview) is the ONLY Gemini image model.
# No fallback to lesser models — if 3-pro fails, the error surfaces so the user knows.
GEMINI_MODEL = "gemini-3-pro-image-preview"

# Locked: OpenAI image-2 (gpt-image-2) is the primary OpenAI model.
# Falls back to gpt-image-1 only if gpt-image-2 isn't available on this account yet.
OPENAI_IMAGE_MODELS = ["gpt-image-2", "gpt-image-1"]

OUTPUT_DIR = Path(__file__).parent.parent / "outputs" / "marketing-posts"


# ─── Style brief helpers ───────────────────────────────────────────────────────

def _editorial_luxury_prompt(d: dict) -> str:
    headline = d['title_line_1'].strip()
    price = d['price_line'].strip()
    departures = d.get('departures', '').strip()
    highlights = (d.get('highlights') or [])[:4]
    incl_lines = "\n".join(f"     ✦ {h}" for h in highlights)
    return f"""A premium editorial travel poster in the style of a Condé Nast Traveler magazine cover or Aman Resorts brochure. Square format, 1080×1080.

LAYOUT: TOP 55% is a single ultra-photorealistic cinematic photograph of {d['photo_direction']}. Golden hour light, rich saturated colors, no people in foreground. Magazine-quality landscape photography.

BOTTOM 45% is a clean off-white cream panel (warm ivory). Two columns inside the panel:

LEFT COLUMN (60% width) — vertical stack with generous whitespace:
  • A large refined serif headline in dark charcoal, all caps, tight letter-spacing: "{headline}"
  • A short warm amber horizontal rule, ~80px wide, directly below the headline
  • In smaller charcoal sans-serif, the price line: "{price}"
  {"• Below price in tiny charcoal italic: " + chr(34) + departures + chr(34) if departures else ""}

RIGHT COLUMN (40% width) — small "WHAT'S INCLUDED" callout:
  • Tiny amber italic serif label on top: "WHAT'S INCLUDED"
  • Below the label, exactly {len(highlights)} dark-charcoal sans-serif lines, each with a small amber ✦ diamond bullet:
{incl_lines}

In the top-right corner of the photo, a small refined wordmark reading "DREAM WORLD TOURS" in white, letter-spaced, all caps.

That is the ENTIRE design. No other text, no decorative elements, no footer band.

The aesthetic is restrained, sophisticated, expensive — Aman Resorts, The Hoshinoya, Belmond. Premium serif typography. Every rendered word must be perfectly sharp and legible — no garbled letters, no doubled text. Bullets must render as clean ✦ diamonds, not as random symbols."""


def _cinematic_yellow_prompt(d: dict) -> str:
    headline = d['title_line_1'].strip()
    highlight = d.get('highlight_word', headline.split()[0] if headline else 'INDIA').strip().upper()
    price = d['price_line'].strip()
    departures = d.get('departures', '').strip()
    highlights = (d.get('highlights') or [])[:4]
    incl_lines = "\n".join(f"     • {h}" for h in highlights)
    return f"""A cinematic National Geographic-style travel poster. Square format, 1080×1080.

Full-bleed dark moody photograph of {d['photo_direction']}. Dramatic low light — late golden hour, blue hour, or atmospheric mist. Deep saturated colors. Editorial photojournalism quality. No people in foreground.

A soft dark gradient fades up from the bottom edge, occupying the lower 55% of the image for text legibility.

LOWER-LEFT TEXT BLOCK (anchored at the bottom, left-aligned):

  1. A large bold sans-serif headline in pure white, all caps, two lines max: "{headline}"
     — within the headline, the single word "{highlight}" sits on a solid bright yellow rectangle (marker-highlight effect), the word itself in jet-black on the yellow
  2. Directly below in white sans-serif (medium weight): "{price}"
  {"3. Below the price in tiny white sans-serif: " + chr(34) + departures + chr(34) if departures else ""}

LOWER-RIGHT INCLUSIONS COLUMN — small "INCLUDES" callout:
  • Tiny bright yellow uppercase label: "INCLUDES"
  • Below the label, exactly {len(highlights)} white sans-serif lines, each prefixed with a small yellow • bullet dot, tight line-height:
{incl_lines}

In the top-right corner, a small "DREAM WORLD TOURS" wordmark in white, letter-spaced.

That is the ENTIRE design. No other text, no decorative elements.

The aesthetic is bold, cinematic, scroll-stopping — like a Vanity Fair editorial spread or a National Geographic cover. The yellow marker highlight is the focal point. Every rendered character must be perfectly sharp and legible — no garbled letters."""


def _vibrant_tropical_prompt(d: dict) -> str:
    headline = d['title_line_1'].strip()
    highlight = d.get('highlight_word', headline.split()[0] if headline else 'PARADISE').strip().upper()
    price = d['price_line'].strip()
    departures = d.get('departures', '').strip()
    highlights = (d.get('highlights') or [])[:4]
    incl_lines = "\n".join(f"     ✓ {h}" for h in highlights)
    return f"""A bold, vibrant tropical travel poster in the style of a high-end resort billboard. Square format, 1080×1080.

Full-bleed ultra-saturated photograph of {d['photo_direction']}. Vivid turquoise water or lush vivid greens, brilliant blue sky, aspirational atmosphere. Editorial Travel + Leisure quality. No people in foreground.

A soft dark gradient at the top edge for the headline area, and a translucent dark band across the lower 40% for text legibility.

DESIGN ELEMENTS (in order, top to bottom):

  1. UPPER-CENTER — a large bold sans-serif headline in white, all caps: "{headline}"
     — within it, the single word "{highlight}" sits on a solid bright yellow rectangle marker-highlight, jet-black text on the yellow

  2. MIDDLE — a clean "INCLUDES" callout block, centered on the dark lower band:
     • Small yellow uppercase label: "WHAT'S INCLUDED"
     • Below, exactly {len(highlights)} white sans-serif lines, each prefixed with a small bright yellow ✓ checkmark:
{incl_lines}

  3. PRICE LINE in clean white sans-serif right below the inclusions: "{price}"
  {"4. Tiny white text under price: " + chr(34) + departures + chr(34) if departures else ""}

  4. BOTTOM-CENTER — a single bright amber pill-shaped CTA button with bold white text reading "WhatsApp to Book"

In the top-right corner, a small white "DREAM WORLD TOURS" wordmark, letter-spaced.

That is the ENTIRE design. No other text or decorative elements.

The aesthetic is bright, confident, conversion-focused — like a premium beach resort billboard. The yellow marker + checkmark inclusions are the focal points. Every rendered word must be perfectly sharp and legible. Checkmarks must render as clean ✓ glyphs, not as random symbols."""


def _polaroid_scrapbook_prompt(d: dict) -> str:
    headline = d['title_line_1'].strip()
    price = d['price_line'].strip()
    departures = d.get('departures', '').strip()
    highlights = (d.get('highlights') or [])[:4]
    incl_lines = "\n".join(f"        ★ {h}" for h in highlights)
    return f"""An authentic travel journal page in the style of a Moleskine notebook spread or vintage scrapbook layout. Square format, 1080×1080.

Background: warm cream paper texture with very faint grid lines, like a designer's notebook.

In the UPPER-CENTER, two polaroid-style photographs of {d['photo_direction']}, slightly overlapping, each tilted at a gentle 5-degree angle. White polaroid borders with soft realistic cast shadows on the paper. Photos look like real printed travel snapshots.

TEXT ELEMENTS, all in handwritten-style ink (chunky brush-pen + flowing script):

  1. AT THE TOP, above the polaroids — a bold dark charcoal hand-lettered headline (chunky brush-pen): "{headline}"

  2. TO THE RIGHT of the polaroids, an "INCLUDED ✦" callout box drawn as a hand-sketched rounded rectangle in black ink:
     • Tiny hand-printed header: "WHAT'S INCLUDED"
     • Below, exactly {len(highlights)} hand-printed dark ink lines, each prefixed with a small hand-drawn ★ star bullet:
{incl_lines}

  3. BELOW the polaroids, in flowing dark ink script: "{price}"
  {"4. Directly below in tiny pencil text: " + chr(34) + departures + chr(34) if departures else ""}

  4. Tiny clean text in the very bottom-right corner: "Dream World Tours"

One subtle piece of warm beige washi tape across the top corner of one polaroid. Nothing else — no doodles, no birds, no stars, no postcard stamps, no scattered elements.

The aesthetic is authentic, personal, save-worthy — like a real travel journal someone would screenshot. Premium scrapbook restraint. Every handwritten word must be sharp and legible. Stars and bullets must render as clean glyphs, not garbled marks."""


def _minimal_modern_prompt(d: dict) -> str:
    headline = d['title_line_1'].strip()
    price = d['price_line'].strip()
    departures = d.get('departures', '').strip()
    highlights = (d.get('highlights') or [])[:4]
    incl_lines = "\n".join(f"     · {h}" for h in highlights)
    return f"""A minimal Vogue-cover-style travel poster in the style of an Apple keynote slide. Square format, 1080×1080.

A single full-bleed ultra-photorealistic cinematic photograph of {d['photo_direction']}. Premium aspirational quality, single hero subject, magazine-cover composition. No people in foreground. A very subtle dark edge vignette + a soft darker gradient on the bottom 30% for text legibility.

TEXT ELEMENTS:

  1. CENTERED in the upper-middle of the image, a large refined serif headline in pure white, single line: "{headline}"

  2. BOTTOM-LEFT corner — vertical stack with tight line-spacing:
     • Tiny uppercase white sans-serif label: "INCLUDES"
     • Below the label, exactly {len(highlights)} white sans-serif lines, each prefixed with a small white middle-dot · :
{incl_lines}

  3. BOTTOM-RIGHT corner — vertical stack, right-aligned:
     • Clean white sans-serif: "{price}"
     {"• Tiny white sans-serif below: " + chr(34) + departures + chr(34) if departures else ""}

In the very top-left corner, a tiny "DREAM WORLD TOURS" wordmark in white, all caps, letter-spaced.

That is the ENTIRE design. No badge, no pill, no decorative dots beyond the bullet dots, no rules, no website URL, no phone number.

The aesthetic is pure typographic restraint — like the cover of a Vogue travel issue or a Cartier campaign. Photo dominates. Every rendered word must be perfectly sharp and legible."""


def _seasonal_festival_prompt(d: dict) -> str:
    headline = d['title_line_1'].strip()
    price = d['price_line'].strip()
    departures = d.get('departures', '').strip()
    eyebrow = d.get('eyebrow', 'Limited Departure').strip()
    highlights = (d.get('highlights') or [])[:4]
    incl_lines = "\n".join(f"     ◆ {h}" for h in highlights)
    return f"""A premium festival-season travel poster in the style of a luxury Diwali campaign or year-end holiday brochure (think Taj Hotels or Oberoi seasonal campaigns). Square format, 1080×1080.

Full-bleed ultra-photorealistic cinematic photograph of {d['photo_direction']}. Warm festive lighting — golden candle-glow, lantern light, or sunset. Rich saturated warm color palette. Editorial premium quality. No people in foreground.

A soft warm dark gradient at the top edge and a darker gradient covering the bottom 50% for text legibility.

TEXT ELEMENTS:

  1. TOP-CENTER, small refined italic script in soft amber: "{eyebrow}"

  2. UPPER-MIDDLE of the composition, a large bold sans-serif headline in pure white, all caps: "{headline}"

  3. CENTER — an "INCLUDES" callout, centered on the dark band:
     • Small uppercase amber label: "PACKAGE INCLUDES"
     • Below, exactly {len(highlights)} white sans-serif lines, each prefixed with a warm amber ◆ diamond bullet:
{incl_lines}

  4. PRICE LINE in clean white sans-serif right below the inclusions block: "{price}"
  {"5. Tiny white text below price: " + chr(34) + departures + chr(34) if departures else ""}

  5. BOTTOM-CENTER — a single solid warm amber pill-shaped CTA button with bold dark text reading "Book on WhatsApp"

In the top-right corner, a small "DREAM WORLD TOURS" wordmark in white, letter-spaced.

That is the ENTIRE design. No confetti, no lanterns, no sparkles, no ribbons, no banners, no website URL.

The aesthetic is celebratory but restrained — premium festival luxury, not loud or cluttered. Every rendered word must be perfectly sharp and legible. Diamond bullets must render as clean ◆ glyphs."""


# ─── Inspiration registry ──────────────────────────────────────────────────────

INSPIRATIONS = [
    {
        "id": "editorial-luxury",
        "name": "Editorial Luxury",
        "tagline": "Condé Nast magazine-style with split photo + clean editorial panel",
        "aesthetic": "premium · refined · sophisticated",
        "best_for": "Premium international tours, luxury positioning, all destinations",
        "preview_url": "https://images.unsplash.com/photo-1528127269322-539801943592?w=600&q=80&auto=format&fit=crop",
        "color_hint": "off-white + amber + dark charcoal",
        "prompt_builder": _editorial_luxury_prompt,
    },
    {
        "id": "cinematic-yellow",
        "name": "Cinematic Yellow Accent",
        "tagline": "Dark moody photo with bold yellow marker-highlight on key word",
        "aesthetic": "cinematic · dramatic · scroll-stopping",
        "best_for": "Spiritual/cultural tours, Northeast India, Kashmir winter, dramatic destinations",
        "preview_url": "https://images.unsplash.com/photo-1567157577867-05ccb1388e66?w=600&q=80&auto=format&fit=crop",
        "color_hint": "dark moody + bright yellow highlight",
        "prompt_builder": _cinematic_yellow_prompt,
    },
    {
        "id": "vibrant-tropical",
        "name": "Vibrant Tropical",
        "tagline": "High-engagement bold colors with yellow marker accents + clear CTA",
        "aesthetic": "vibrant · bold · conversion-focused",
        "best_for": "Thailand, Bali, beach destinations, family-friendly campaigns",
        "preview_url": "https://images.unsplash.com/photo-1552465011-b4e21bf6e79a?w=600&q=80&auto=format&fit=crop",
        "color_hint": "vivid teal + bright yellow + white",
        "prompt_builder": _vibrant_tropical_prompt,
    },
    {
        "id": "polaroid-scrapbook",
        "name": "Polaroid Scrapbook",
        "tagline": "DWT signature — handwritten travel journal with tilted polaroid photos",
        "aesthetic": "authentic · personal · save-worthy",
        "best_for": "Family tours, narrative storytelling, listicle-style posts",
        "preview_url": "https://images.unsplash.com/photo-1488646953014-85cb44e25828?w=600&q=80&auto=format&fit=crop",
        "color_hint": "warm cream paper + black ink + tape washi",
        "prompt_builder": _polaroid_scrapbook_prompt,
    },
    {
        "id": "minimal-modern",
        "name": "Minimal Modern",
        "tagline": "Apple-keynote restraint — single hero photo, minimal typography",
        "aesthetic": "minimal · confident · upscale",
        "best_for": "Luxury Vietnam/Dubai, honeymoon, sophisticated single-destination",
        "preview_url": "https://images.unsplash.com/photo-1571401835393-8c5f35328320?w=600&q=80&auto=format&fit=crop",
        "color_hint": "photo-dominant + white serif text",
        "prompt_builder": _minimal_modern_prompt,
    },
    {
        "id": "seasonal-festival",
        "name": "Seasonal Festival",
        "tagline": "Celebratory but premium — for festival/seasonal launches",
        "aesthetic": "celebratory · warm · urgency-driven",
        "best_for": "Diwali, monsoon launches, year-end campaigns, religious yatras",
        "preview_url": "https://images.unsplash.com/photo-1542038784456-1ea8e935640e?w=600&q=80&auto=format&fit=crop",
        "color_hint": "warm festive + amber CTA + celebratory",
        "prompt_builder": _seasonal_festival_prompt,
    },
]


def get_inspirations() -> list:
    """Public-facing inspirations list (without the prompt_builder function)."""
    return [{k: v for k, v in i.items() if k != "prompt_builder"} for i in INSPIRATIONS]


def _find_inspiration(insp_id: str) -> dict | None:
    return next((i for i in INSPIRATIONS if i["id"] == insp_id), None)


def _build_image_prompt_via_skill(destination: str, insp: dict, details: dict) -> str:
    """
    Use the marketing-post-designer agent to build a brand-aware image prompt.
    The agent has full DWT context (colors, tour types, voice, inspiration patterns)
    that the hardcoded templates lack. Output is a single prompt string ready
    for nano-banana / gpt-image-2.

    Falls through to the hardcoded prompt_builder if anything fails.
    """
    # Import here to avoid circular dependency at module load
    from services.skill_runner import run_skill

    highlights_block = "\n".join(f"  - {h}" for h in (details.get('highlights') or [])[:5])

    brief = f"""DWT MARKETING POST BRIEF — output an image generation prompt only.

DESTINATION: {destination}

DESIGN STYLE: {insp['name']} — {insp['tagline']}
  Aesthetic: {insp['aesthetic']}
  Color hint: {insp.get('color_hint', '')}
  Best for: {insp['best_for']}

CONTENT TO BAKE INTO THE IMAGE:
  Title line 1: {details.get('title_line_1', '')}
  Title line 2: {details.get('title_line_2', '')}
  Eyebrow label: {details.get('eyebrow', '')}
  Price line: {details.get('price_line', '')}
  Departures: {details.get('departures', '')}
  Subline: {details.get('subline', '')}
  Photo direction: {details.get('photo_direction', '')}
  Marker-highlight word (for yellow accent on this word): {details.get('highlight_word', '')}

INCLUSIONS to render as bullet list inside the design (use ✓ or ✦ glyphs):
{highlights_block or '  (none — use generic DWT inclusions: all meals, Pune-based tour manager, premium stays, all sightseeing)'}

YOUR JOB:
Output ONE detailed image generation prompt (~250-400 words) for a square 1080×1080 WhatsApp/Instagram marketing post. The prompt must:
- Match the "{insp['name']}" aesthetic exactly
- Specify text placement, color palette, typography
- Bake ALL the text content above (headline, price, departures, inclusions, CTA, "Dream World Tours" wordmark) into the image
- Include hard requirement that every rendered word is sharp and legible (no garbled letters)
- NOT actually call any image tool — just return the prompt as a single block of text

CRITICAL: Output ONLY the image prompt. No preamble, no markdown headers, no "Here is the prompt:" line. Start directly with the prompt text."""

    result = run_skill(
        name="marketing-post-designer",
        args=brief,
        smart=True,           # use Gemini 2.5 Pro — better creative output
        expect_json=False,
        max_tokens=3000,
    )
    prompt = (result.get("output") or "").strip()
    if not prompt or len(prompt) < 150:
        raise RuntimeError("marketing-post-designer returned an empty/too-short prompt")
    return prompt


# ─── Generation ────────────────────────────────────────────────────────────────

def _call_gemini_image(prompt: str) -> tuple:
    """Generate via nano-banana pro (gemini-3-pro-image-preview). Returns (PIL Image, model used)."""
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY not set")
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseModalities": ["IMAGE", "TEXT"]},
    }
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    try:
        resp = requests.post(url, json=body, timeout=120)
        data = resp.json()
        if "error" in data:
            raise RuntimeError(f"{GEMINI_MODEL} error: {data['error'].get('message', str(data['error']))[:200]}")
        for cand in data.get("candidates", []):
            for part in cand.get("content", {}).get("parts", []):
                b64 = part.get("inlineData", {}).get("data", "")
                if b64:
                    return Image.open(io.BytesIO(base64.b64decode(b64))), GEMINI_MODEL
        raise RuntimeError(f"{GEMINI_MODEL}: no image in response")
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f"Gemini image generation failed: {str(e)[:200]}")


def _call_openai_image(prompt: str) -> tuple:
    """Generate via OpenAI gpt-image-2 (falls back to gpt-image-1 if -2 unavailable).
    Returns (PIL Image, model used).
    """
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY not set")
    url = "https://api.openai.com/v1/images/generations"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}

    last_err = "no models tried"
    for model in OPENAI_IMAGE_MODELS:
        body = {
            "model": model,
            "prompt": prompt[:4000],
            "size": "1024x1024",
            "quality": "high",
            "n": 1,
        }
        try:
            resp = requests.post(url, json=body, headers=headers, timeout=180)
            data = resp.json()
            if "error" in data:
                err_msg = data["error"].get("message", str(data["error"]))
                last_err = f"{model}: {err_msg[:200]}"
                # Only fall back if model-not-found error (e.g., gpt-image-2 not yet on this account)
                if "model" in err_msg.lower() and ("not found" in err_msg.lower() or "does not exist" in err_msg.lower() or "invalid" in err_msg.lower()):
                    print(f"[marketing_post] {model} not available, trying next: {err_msg[:120]}")
                    continue
                # Real error (auth, quota, etc.) — don't keep trying
                raise RuntimeError(last_err)
            first = (data.get("data") or [{}])[0]
            if first.get("b64_json"):
                return Image.open(io.BytesIO(base64.b64decode(first["b64_json"]))), model
            if first.get("url"):
                img_resp = requests.get(first["url"], timeout=60)
                img_resp.raise_for_status()
                return Image.open(io.BytesIO(img_resp.content)), model
            last_err = f"{model}: no image in response"
        except RuntimeError:
            raise
        except Exception as e:
            last_err = f"{model}: {str(e)[:200]}"
            continue
    raise RuntimeError(f"OpenAI image generation failed: {last_err}")


def _generate_image(prompt: str, model_provider: str = "gemini") -> tuple:
    """Dispatch to chosen provider. No cross-provider fallback — user's choice is honored
    (errors surface so they know which model failed)."""
    provider = (model_provider or "gemini").lower().strip()
    if provider in ("openai", "gpt", "gpt-image"):
        return _call_openai_image(prompt)
    # Default: nano-banana (Gemini)
    return _call_gemini_image(prompt)


def _upload_imgbb(image_path: Path, name: str) -> str | None:
    if not IMGBB_API_KEY:
        return None
    try:
        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        r = requests.post(
            "https://api.imgbb.com/1/upload",
            data={"key": IMGBB_API_KEY, "image": b64, "name": name},
            timeout=60,
        )
        if r.status_code == 200 and r.json().get("success"):
            return r.json()["data"]["url"]
    except Exception as e:
        print(f"[marketing_post] imgbb upload failed: {str(e)[:120]}")
    return None


def generate_post(destination: str, inspiration_id: str, details: dict | None = None, model_provider: str = "gemini") -> dict:
    """
    Generate a marketing post.

    Args:
        destination: e.g. "Vietnam", "Bhutan", "Kashmir Apple Blossom"
        inspiration_id: one of INSPIRATIONS ids
        details: optional dict with overrides — title_line_1, title_line_2, price_line,
                 departures, highlights, photo_direction, etc.
        model_provider: "gemini" (nano-banana, default) or "openai" (gpt-image-1)

    Returns dict: {run_id, destination, inspiration_id, image_url, local_path, model_used, provider_used}
    """
    insp = _find_inspiration(inspiration_id)
    if not insp:
        raise ValueError(f"Unknown inspiration_id '{inspiration_id}'. Available: {[i['id'] for i in INSPIRATIONS]}")

    # Merge defaults with caller-provided details
    details = dict(details or {})
    dest_clean = destination.strip().title()
    details.setdefault("title_line_1", dest_clean.upper())
    details.setdefault("title_line_2", "")
    details.setdefault("eyebrow", "Group Tour from Pune")
    details.setdefault("price_line", "Group tour from Pune · WhatsApp to confirm")
    details.setdefault("departures", "")
    details.setdefault("subline", f"Curated group tour with Pune-based tour manager")
    details.setdefault("photo_direction", f"iconic cinematic destination shot of {dest_clean}, golden hour, vivid colors, no people in foreground")
    details.setdefault("highlight_word", dest_clean.split()[0].upper() if dest_clean else "PUNE")

    # Smart fallback: if user didn't supply highlights, use DWT-generic inclusions
    # so the post never looks empty. Smart Generate / explicit user input overrides this.
    if not details.get("highlights"):
        details["highlights"] = [
            "All meals included",
            "Pune-based tour manager",
            "Premium hotel stays",
            "All sightseeing covered",
        ]

    # Build the image prompt — prefer skill-driven (brand-aware) over hardcoded templates
    prompt_source = "template"
    if USE_SKILL_PROMPTS:
        try:
            prompt = _build_image_prompt_via_skill(destination, insp, details)
            prompt_source = "skill:marketing-post-designer"
        except Exception as e:
            print(f"[marketing_post] Skill prompt failed, falling back to template: {str(e)[:200]}")
            prompt = insp["prompt_builder"](details)
    else:
        prompt = insp["prompt_builder"](details)

    # Generate image via chosen provider (with cross-fallback if one fails)
    img, model_used = _generate_image(prompt, model_provider=model_provider)
    provider_used = "openai" if model_used and "gpt-image" in model_used else "gemini"

    # Resize to square 1080
    if img.size != (1080, 1080):
        img = img.resize((1080, 1080), Image.LANCZOS)

    # Save locally with unique ID
    run_id = uuid.uuid4().hex[:8]
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    slug = "".join(c for c in destination.lower() if c.isalnum() or c == "-").strip("-") or "post"
    filename = f"{slug}-{inspiration_id}-{provider_used}-{run_id}.png"
    local_path = OUTPUT_DIR / filename
    img.save(local_path, "PNG")

    # Upload to imgbb for permanent URL (survives Railway redeploys)
    permanent_url = _upload_imgbb(local_path, filename)
    local_url = f"/api/marketing-posts/image/{filename}"
    final_url = permanent_url or local_url

    return {
        "run_id": run_id,
        "destination": dest_clean,
        "inspiration_id": inspiration_id,
        "inspiration_name": insp["name"],
        "image_url": final_url,
        "local_path": str(local_path),
        "filename": filename,
        "permanent_url": permanent_url,
        "model_used": model_used,
        "provider_used": provider_used,
        "model_requested": model_provider,
        "prompt_source": prompt_source,
        "prompt_excerpt": prompt[:200] + "...",
    }
