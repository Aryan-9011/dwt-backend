"""
Weekly content calendar generator for DWT Agent Hub.
Uses Gemini API to produce 7 data-driven content ideas from real package data.
"""
import os
import json
from pathlib import Path
from datetime import datetime, timedelta
import google.generativeai as genai

PACKAGES_JSON = Path(__file__).parent.parent / "data" / "packages.json"


def _package_context() -> str:
    """Return a compact summary of active DWT packages."""
    if not PACKAGES_JSON.exists():
        return "DWT destinations: Kashmir, Vietnam, Dubai, Thailand, Singapore+Malaysia, Bali"
    try:
        packages = json.loads(PACKAGES_JSON.read_text())
        lines = []
        for p in packages[:14]:
            name = p.get("name", "")
            duration = p.get("duration", "")
            pricing = p.get("pricing", {})
            price_str = " | ".join(f"{k}: {v}" for k, v in list(pricing.items())[:2]) if pricing else ""
            deps = p.get("upcoming_departures", [])[:2]
            dep_str = ", ".join(deps) if deps else "on request"
            lines.append(f"- {name} ({duration}) {price_str} | Next dep: {dep_str}")
        return "\n".join(lines)
    except Exception:
        return "DWT destinations: Kashmir, Vietnam, Dubai, Thailand, Singapore+Malaysia"


def _dwt_destination_keywords() -> list:
    """Return list of destination keywords DWT operates (from packages.json + curated extras)."""
    base = [
        "vietnam","thailand","dubai","abu dhabi","bali","singapore","malaysia",
        "maldives","bhutan","sri lanka","mauritius","kenya",
        "kashmir","ladakh","leh","sikkim","kerala","himachal","arunachal","spiti",
        "darjeeling","assam","meghalaya","andaman","amarnath",
    ]
    if not PACKAGES_JSON.exists():
        return base
    try:
        packages = json.loads(PACKAGES_JSON.read_text())
        for p in packages:
            name = (p.get("name") or "").lower()
            for word in name.replace("&", " ").replace("+", " ").replace("-", " ").split():
                if len(word) > 3 and word not in base:
                    base.append(word)
        return base
    except Exception:
        return base


def _clean_json(raw: str) -> list:
    raw = raw.strip()
    if raw.startswith("```"):
        for part in raw.split("```"):
            stripped = part.lstrip("json").strip()
            if stripped.startswith("["):
                raw = stripped
                break
    return json.loads(raw)


def generate_growth_calendar(recent_topics: list = None, intel: dict = None, web_research: dict = None) -> dict:
    """
    Generate a 7-day Instagram content calendar using Gemini.
    `intel`        (optional): dict from instagram_intel.gather_intel() with DWT + competitor metrics.
    `web_research` (optional): dict from web_research.research_travel_trends() with trending articles.
    Returns dict with 'week_of', 'generated_at', 'calendar' list, 'intel', 'web_research'.
    """
    genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
    today = datetime.now()

    # Find next Monday
    days_ahead = (7 - today.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    next_mon = today + timedelta(days=days_ahead)

    week_dates = [(next_mon + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]
    week_days  = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

    pkg_ctx = _package_context()
    avoid   = ", ".join(recent_topics[:10]) if recent_topics else "none yet"
    month   = next_mon.strftime("%B %Y")

    # Build live Instagram intel block (if available)
    intel_block = ""
    if intel and intel.get("available"):
        from services.instagram_intel import intel_to_prompt_block
        intel_block = "\n\n" + intel_to_prompt_block(intel) + "\n"

    # Build web research block (if available)
    web_block = ""
    if web_research and web_research.get("available"):
        from services.web_research import trends_to_prompt_block
        web_block = "\n\n" + trends_to_prompt_block(web_research) + "\n"

    prompt = f"""You are the Chief Instagram Growth Strategist for Dream World Tours (DWT), a premium group tour agency from Pune, India.

Today is {today.strftime("%B %d, %Y")}. Generate a 7-day Instagram content calendar for {month} ({next_mon.strftime("%b %d")}–{(next_mon+timedelta(days=6)).strftime("%b %d")}).

ACTIVE DWT PACKAGES (use these exact names and prices):
{pkg_ctx}

RECENTLY USED TOPICS (do NOT repeat these):
{avoid}{intel_block}{web_block}

═══════ HARD RULES (these are non-negotiable) ═══════

MANDATORY CONTENT MIX:
- At least 3 Reels
- At least 2 Carousels
- At least 1 Social Proof post (testimonial / trip photos / customer video)
- At least 2 Promotional posts: real package name + real price (USD or INR) + actual departure date + "Comment X to check seats" CTA
- No two consecutive posts of the same content_type

MANDATORY PACKAGE TIE-IN (the #1 rule):
- AT LEAST 6 OF THE 7 ITEMS must have a non-empty "dwt_package" field — only 1 item may be a pure brand/content marketing post without a package tie-in.
- Copy the EXACT package name from the ACTIVE DWT PACKAGES list above into the "dwt_package" field. Do not paraphrase.
- If a trending article or web research item is about a destination DWT does NOT operate (e.g. Uzbekistan, Maharashtra weekend trips), DO NOT include that topic. Instead pivot to a similar DWT destination — e.g. "Uzbekistan budget travel" → "Vietnam: feel like a millionaire" using DWT's Luxury Vietnam package.
- A "Promotional" item with empty dwt_package = INVALID — fix it.

MANDATORY POSTING-GAP HANDLING:
- The LIVE INSTAGRAM INTEL section lists days DWT didn't post last week. Schedule your HIGHEST virality_score items on those days. Don't waste them on days DWT already posts regularly.

MANDATORY REEL NOTES:
- If the TRENDING AUDIO list is provided in the web research, the "notes" field of EVERY Reel item MUST reference one specific trending audio name from that list (e.g. "Use audio: 'Sunset on Hua Hin' — currently viral").
- If no trending audio is provided, the notes must specify a concrete production detail (lighting, shot type, opening visual).

SCORING RULES (lead_score is NEVER 0 — must be 1-10):
- virality_score 9-10: Reel with shocking hook + strong emotional trigger + comment CTA
- virality_score 7-8: strong hook + good format match (carousel for tips, reel for visuals)
- virality_score 4-6: solid content but generic hook OR mediocre format choice
- virality_score 1-3: weak hook OR boring format
- lead_score 9-10: REAL package + REAL price + REAL departure date + "Comment KEYWORD to check seats" CTA (direct conversion path)
- lead_score 7-8: specific destination + soft CTA (DM us / link in bio) + builds buying intent
- lead_score 4-6: educational/inspirational content that builds trust toward future purchase
- lead_score 1-3: pure entertainment / awareness only, no conversion path

PROMOTIONAL CTA QUALITY:
- BAD: "Last minute deal inside!" / "DM us to know more"
- GOOD: "Only 4 seats left on the May 31 departure — Comment KASHMIR to check seats" / "₹65,000 all-inclusive, June 12 departure — Comment KASHMIR"

ENGAGEMENT GAP CLOSURE:
- Look at the engagement gap data in the IG INTEL block. Your top-scoring item should be designed to beat the competitor's best post by mirroring its winning format and hook structure (not the content).

Return ONLY a valid JSON array of exactly 7 objects. No markdown fences. No explanation.

Each object schema:
{{
  "date": "YYYY-MM-DD",
  "day": "Monday",
  "content_type": "Reel",
  "topic": "short punchy topic",
  "hook": "exact scroll-stopping first line, under 15 words",
  "objective": "Awareness | Engagement | Lead Generation | Social Proof | Brand Authority",
  "emotional_angle": "FOMO | Aspiration | Relief | Family | Pride | Wanderlust",
  "cta": "exact CTA text",
  "production_type": "AI avatar reel | Existing footage reel | Carousel design | Founder selfie | Customer testimonial",
  "production_complexity": "Low | Medium | High",
  "virality_score": 8,
  "lead_score": 7,
  "assigned_agent": "reel-pipeline-manager | carousel-content-writer | marketing-post-manager | manual",
  "dwt_package": "exact package name from list, or empty string",
  "notes": "one-line specific production note"
}}

Dates: {", ".join(f"{week_days[i]} {week_dates[i]}" for i in range(7))}

IMPORTANT: Return ONLY the JSON array. No markdown. No explanation."""

    model = genai.GenerativeModel("gemini-2.5-flash")
    response = model.generate_content(prompt)
    calendar = _clean_json(response.text)

    return {
        "week_of": f"{week_dates[0]} to {week_dates[6]}",
        "generated_at": today.isoformat(),
        "calendar": calendar,
        "intel": intel if (intel and intel.get("available")) else None,
        "web_research": web_research if (web_research and web_research.get("available")) else None,
    }
