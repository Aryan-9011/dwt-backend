"""
Web research service for DWT Agent Hub.
Uses Gemini's Google Search grounding to find current trending
travel articles that can be repurposed as Instagram content.
"""
import os
import json
import requests
from datetime import datetime

GEMINI_KEY = lambda: os.environ.get("GEMINI_API_KEY")
# gemini-2.5-flash supports google_search grounding and has working quota on this account.
# gemini-2.0-flash + 2.5-pro are quota-exhausted on this key. Order matters.
_MODELS = ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-flash-latest"]


def _clean_json_array(raw: str) -> list:
    raw = raw.strip()
    if "```" in raw:
        for part in raw.split("```"):
            stripped = part.lstrip("json").strip()
            if stripped.startswith("["):
                raw = stripped
                break
    # Strip leading/trailing text around the JSON array
    start = raw.find("[")
    end = raw.rfind("]")
    if start != -1 and end != -1:
        raw = raw[start:end + 1]
    return json.loads(raw)


def _call_gemini_with_search(prompt: str) -> str:
    """POST to Gemini REST API with google_search tool enabled. Returns text."""
    api_key = GEMINI_KEY()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set")

    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "tools": [{"google_search": {}}],
    }

    last_err = "no models tried"
    for model in _MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        try:
            resp = requests.post(url, json=body, timeout=90)
            data = resp.json()
            if "error" in data:
                last_err = data["error"].get("message", str(data["error"]))
                # If google_search tool not supported on this model, try fallback w/o tools
                if "tool" in last_err.lower() or "google_search" in last_err.lower():
                    body_no_tool = {"contents": [{"parts": [{"text": prompt}]}]}
                    resp = requests.post(url, json=body_no_tool, timeout=90)
                    data = resp.json()
                    if "error" in data:
                        last_err = data["error"].get("message", str(data["error"]))
                        continue
                else:
                    continue
            text = ""
            for cand in data.get("candidates", []):
                for part in cand.get("content", {}).get("parts", []):
                    text += part.get("text", "")
            if text:
                return text
            last_err = "empty response"
        except Exception as e:
            last_err = str(e)
            continue

    raise RuntimeError(f"Gemini search failed: {last_err[:200]}")


DWT_DESTINATIONS_LOWER = [
    "vietnam", "thailand", "dubai", "abu dhabi", "bali", "singapore", "malaysia",
    "maldives", "bhutan", "sri lanka", "mauritius", "kenya",
    "kashmir", "ladakh", "leh", "sikkim", "kerala", "himachal", "arunachal", "spiti",
    "darjeeling", "assam", "meghalaya", "andaman", "pune", "amarnath",
]


def _classify_article(article: dict) -> dict:
    """Tag article as 'actionable' (matches a DWT destination) or 'inspirational' (doesn't).
    Also detect if it's a trending-sounds article and extract audio cues."""
    blob = " ".join([
        article.get("title", ""),
        article.get("summary", ""),
        " ".join(article.get("key_items", []) or []),
    ]).lower()

    matched_destinations = sorted({d for d in DWT_DESTINATIONS_LOWER if d in blob})
    article["actionable"] = bool(matched_destinations)
    article["dwt_destinations_matched"] = matched_destinations

    # Trending sounds detection
    blob_title = (article.get("title") or "").lower()
    is_sounds = any(k in blob_title for k in ["sound", "audio", "song", "reel music", "trending music"])
    article["is_trending_sounds"] = is_sounds
    return article


def research_travel_trends(dwt_destinations: list = None) -> dict:
    """
    Find currently trending travel articles relevant to Indian travelers.
    Prioritizes articles about destinations DWT actually operates.
    Returns {"available": bool, "articles": [...], "trending_audio": [...], ...}
    """
    today = datetime.now().strftime("%B %Y")
    dest_hint = ", ".join((dwt_destinations or DWT_DESTINATIONS_LOWER)[:20])

    prompt = f"""Search the web for 6 currently trending travel articles, listicles, or blog posts that would resonate with Indian travelers in {today}.

PRIORITIZE articles about these destinations Dream World Tours (DWT) actually operates:
{dest_hint}

Also include 1 article about CURRENT INSTAGRAM TRENDS (trending sounds, viral reel formats, hashtags) for May–June 2026.

For each article extract these fields:
- title (string)
- source (publication name)
- summary (one-line)
- key_items (3-5 destinations or items mentioned)
- content_angle (what makes this Instagram-worthy)
- audio_names (if this is about trending sounds/audio — list the actual audio names)

Return ONLY a valid JSON array — no markdown, no explanation. Schema:
[
  {{
    "title": "...",
    "source": "...",
    "summary": "...",
    "key_items": ["...", "..."],
    "content_angle": "...",
    "audio_names": []
  }}
]"""

    try:
        text = _call_gemini_with_search(prompt)
        articles = _clean_json_array(text)
        if not isinstance(articles, list):
            return {"available": False, "reason": "response was not a JSON array"}

        articles = articles[:6]
        articles = [_classify_article(a) for a in articles]

        # Collect any trending audio names found across articles
        trending_audio = []
        for a in articles:
            if a.get("is_trending_sounds"):
                for name in (a.get("audio_names") or []):
                    if name and name not in trending_audio:
                        trending_audio.append(name)

        return {
            "available": True,
            "articles": articles,
            "trending_audio": trending_audio[:10],
            "fetched_at": datetime.now().isoformat(),
        }
    except Exception as e:
        return {"available": False, "reason": str(e)[:200]}


def trends_to_prompt_block(research: dict) -> str:
    """Format the web research output into a directive prompt block."""
    if not research or not research.get("available"):
        return "TRENDING TRAVEL ARTICLES: (web research unavailable — skip this signal)"

    articles = research.get("articles") or []
    if not articles:
        return "TRENDING TRAVEL ARTICLES: (no articles found this week)"

    actionable    = [a for a in articles if a.get("actionable")]
    inspirational = [a for a in articles if not a.get("actionable")]
    trending_audio = research.get("trending_audio") or []

    lines = ["═══════ TRENDING WEB ARTICLES ═══════"]

    if actionable:
        lines.append("")
        lines.append("✅ ACTIONABLE — these map directly to DWT destinations (use these for calendar items):")
        for i, a in enumerate(actionable, 1):
            title = (a.get("title") or "").strip()
            src   = (a.get("source") or "").strip()
            summ  = (a.get("summary") or "").strip()
            items = a.get("key_items") or []
            angle = (a.get("content_angle") or "").strip()
            matched = a.get("dwt_destinations_matched") or []
            lines.append(f"  {i}. \"{title}\" ({src})")
            lines.append(f"     Summary: {summ}")
            lines.append(f"     DWT destinations matched: {', '.join(matched)}")
            lines.append(f"     Key items: {', '.join(items[:5]) if items else '-'}")
            if angle:
                lines.append(f"     IG angle: {angle}")

    if inspirational:
        lines.append("")
        lines.append("💡 INSPIRATIONAL — these don't map to DWT destinations. Do NOT use as topics — only as hook-style inspiration:")
        for a in inspirational:
            lines.append(f"  - \"{a.get('title','')}\" ({a.get('source','')}) — about: {', '.join(a.get('key_items',[])[:3])}")

    if trending_audio:
        lines.append("")
        lines.append(f"🎵 TRENDING AUDIO RIGHT NOW: {', '.join(trending_audio[:8])}")
        lines.append("    → REQUIRED: reference one of these audio names in the 'notes' field of EVERY Reel item you propose.")

    lines.append("")
    lines.append("HOW TO USE THIS RESEARCH (mandatory):")
    lines.append("1. Derive at least 2 calendar items from the ACTIONABLE articles above.")
    lines.append("2. NEVER propose a calendar item about a destination DWT doesn't operate — pivot the angle to a similar DWT destination instead.")
    lines.append("3. Translate listicle articles into Carousel topics; translate single-destination features into Reel hooks.")
    return "\n".join(lines)
