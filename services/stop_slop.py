"""
Stop-slop service — removes AI writing patterns from generated content.
Based on the `stop-slop` skill (.claude/skills/stop-slop/).

Applied as a post-processing step on:
- Carousel captions (pipeline_runner.py)
- GMB autopilot posts (gmb.py)

Uses Gemini 2.5-flash (same model proven to work for web research).
Falls back gracefully — if cleaning fails, original text is returned unchanged.
"""
import os
import asyncio
import google.generativeai as genai

STOP_SLOP_SYSTEM = """You are a ruthless editor removing AI writing patterns from prose.

CORE RULES (apply ALL):
1. Cut filler phrases — REMOVE every instance of: "Here's what...", "It's important to note", "Looking for...?", "Discover...", "Embark on...", "Unleash...", "Unlock...", "Seek...", "Enjoy...", "Experience...", "Explore..." when used as throat-clearing openers.
2. Remove all adverbs (-ly words) and filler adjectives ("sacred", "romantic", "magical", "stunning", "dedicated", "vibrant", "tranquil", "enchanting", "breathtaking") unless they convey concrete information.
3. NO passive voice — find the actor, make them the subject.
4. NO em dashes (—). Use periods or commas instead.
5. NO "It's not X, it's Y" contrasts. State Y directly.
6. NO vague declaratives. Replace "the implications are significant" with the specific implication.
7. State facts directly. Skip softening, justification, hand-holding.
8. Vary sentence rhythm. Mix lengths. Avoid metronomic bullet patterns.
9. Cut sentences that sound like pull-quotes.
10. Trust the reader. No "as you can see" or "it's worth noting".

PRESERVE STRICTLY:
- Emojis (🇮🇳 ✈️ 📅 💰 ✅ 👇 etc.) — keep all of them in original positions
- Hashtags (#tourfrompune etc.) — keep all of them
- Specific numbers (₹65,000, 7N/8D, 25,000+, 4.9 ★, 700+) — never change these
- Phone numbers, addresses, URLs — never change these
- Structural formatting — line breaks, bullet symbols (✅), section headers
- The core meaning and offer — do not change what's being sold

OUTPUT: Return ONLY the revised text. No explanation. No preamble. No "Here is the revised version".
"""


_MODELS = ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-flash-latest"]


def _call_gemini(prompt: str) -> str:
    """Synchronous Gemini call with model fallback."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set")
    genai.configure(api_key=api_key)
    last_err = "no models tried"
    for model_name in _MODELS:
        try:
            model = genai.GenerativeModel(model_name)
            resp = model.generate_content(prompt)
            text = (resp.text or "").strip()
            if text:
                return text
            last_err = f"{model_name} returned empty"
        except Exception as e:
            last_err = f"{model_name}: {str(e)[:120]}"
            continue
    raise RuntimeError(f"stop-slop Gemini call failed: {last_err}")


async def clean(text: str) -> dict:
    """
    Apply stop-slop rules to text via Gemini.
    Returns {"original": str, "cleaned": str, "changed": bool, "error": str|None}.
    Never raises — falls back to original on any failure.
    """
    if not text or not text.strip():
        return {"original": text, "cleaned": text, "changed": False, "error": None}

    prompt = f"{STOP_SLOP_SYSTEM}\n\nORIGINAL:\n{text}\n\nREVISED:"

    try:
        cleaned = await asyncio.to_thread(_call_gemini, prompt)
        # Strip common Gemini preambles if they leak through
        for prefix in ("REVISED:", "Revised:", "Here is the revised text:",
                       "Here's the revised version:", "Here is the revised version:"):
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):].strip()
        if not cleaned:
            cleaned = text
        return {
            "original": text,
            "cleaned": cleaned,
            "changed": cleaned.strip() != text.strip(),
            "error": None,
        }
    except Exception as e:
        # Never break the pipeline — return original on failure
        print(f"[stop-slop] cleaning failed, returning original: {str(e)[:120]}")
        return {"original": text, "cleaned": text, "changed": False, "error": str(e)[:200]}


def clean_sync(text: str) -> dict:
    """Sync wrapper for use in places like gmb.py that aren't async."""
    if not text or not text.strip():
        return {"original": text, "cleaned": text, "changed": False, "error": None}
    prompt = f"{STOP_SLOP_SYSTEM}\n\nORIGINAL:\n{text}\n\nREVISED:"
    try:
        cleaned = _call_gemini(prompt)
        for prefix in ("REVISED:", "Revised:", "Here is the revised text:",
                       "Here's the revised version:", "Here is the revised version:"):
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):].strip()
        if not cleaned:
            cleaned = text
        return {
            "original": text,
            "cleaned": cleaned,
            "changed": cleaned.strip() != text.strip(),
            "error": None,
        }
    except Exception as e:
        print(f"[stop-slop] cleaning failed, returning original: {str(e)[:120]}")
        return {"original": text, "cleaned": text, "changed": False, "error": str(e)[:200]}
