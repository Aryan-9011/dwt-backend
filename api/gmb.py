"""
GMB Autopilot — self-contained FastAPI endpoint.
All GBP logic inlined — no dependency on scripts/gmb_autopilot.py.
Works identically on Railway (Docker) and local dev.
"""
import os
import json
import base64
import asyncio
from datetime import datetime, date
from pathlib import Path
from typing import Optional, List, Dict, Any

import requests
from fastapi import APIRouter, BackgroundTasks, Body, HTTPException
from fastapi.responses import FileResponse

from services import run_store
from services.package_extractor import load_packages
from models import WorkflowType, RunStatus

router = APIRouter()

# ── Config ────────────────────────────────────────────────────────────────────

GEMINI_API_KEY  = os.environ.get("GEMINI_API_KEY", "AIzaSyCO0g2c42fl7COFiLASbYKS9EZNzrN2mvM")
GBP_CLIENT_ID   = os.environ.get("GBP_CLIENT_ID")
GBP_CLIENT_SECRET = os.environ.get("GBP_CLIENT_SECRET")
GBP_REFRESH_TOKEN = os.environ.get("GBP_REFRESH_TOKEN")
GBP_ACCOUNT_ID  = os.environ.get("GBP_ACCOUNT_ID")
GBP_LOCATION_ID = os.environ.get("GBP_LOCATION_ID")
IMGBB_API_KEY   = os.environ.get("IMGBB_API_KEY")
WHATSAPP        = os.environ.get("DWT_WHATSAPP", "919561967004")

OAUTH_URL = "https://oauth2.googleapis.com/token"
GMB_API   = "https://mybusiness.googleapis.com/v4"

IMGS_DIR = Path(__file__).parent.parent / "outputs" / "gmb-images"

# ── Agent registry ─────────────────────────────────────────────────────────────

AGENTS = [
    {
        "id": "gmb-autopilot",
        "name": "GMB Autopilot",
        "icon": "📍",
        "description": "Posts to Google Business Profile 3x/week. Picks destination rotation, writes the post, generates a travel image, and publishes — fully automated.",
        "schedule": "Mon / Wed / Fri at 9:03am IST",
        "runnable": True,
        "tags": ["google", "automated", "images"],
    },
    {
        "id": "instagram-pipeline",
        "name": "Instagram Pipeline",
        "icon": "📸",
        "description": "The draft gate. Rendered carousels wait here with their caption-lint and AI-detection results. You approve, it publishes. Nothing goes live unreviewed.",
        "schedule": "Weekly intel Mon 6am IST · gate always on",
        "runnable": True,
        "tags": ["instagram", "publishing", "approval"],
    },
    {
        "id": "carousel-pipeline",
        "name": "Carousel Pipeline",
        "icon": "🎠",
        "description": "Picks a trending travel topic, writes slide copy, and generates all images via Gemini. Produces a ready-to-post Instagram carousel in one click.",
        "schedule": "On demand",
        "runnable": True,
        "tags": ["instagram", "design", "content"],
    },
    {
        "id": "reel-pipeline",
        "name": "Reel Pipeline",
        "icon": "🎬",
        "description": "Reads itinerary + researches trends → generates 5 complete production-ready reel scripts with shot-by-shot visuals and voiceover.",
        "schedule": "On demand",
        "runnable": False,
        "tags": ["instagram", "reels", "scripts"],
    },
    {
        "id": "marketing-posts",
        "name": "Marketing Posts",
        "icon": "📱",
        "description": "Type a destination, pick a design inspiration, generate a marketing post image for WhatsApp + Instagram. Auto-saved to history.",
        "schedule": "On demand",
        "runnable": True,
        "tags": ["whatsapp", "instagram", "design"],
    },
    {
        "id": "weekly-growth",
        "name": "Weekly Growth",
        "icon": "📈",
        "description": "Generates a data-driven 7-day Instagram content calendar — right here in the dashboard. Uses real DWT packages and departure dates. Run manually or auto-runs every Monday.",
        "schedule": "Every Monday at 9am IST",
        "runnable": True,
        "tags": ["strategy", "calendar", "instagram"],
    },
    {
        "id": "carousel-ideas",
        "name": "Carousel Ideas",
        "icon": "💡",
        "description": "Researches trending travel topics and generates 5 carousel content ideas — written to Google Sheets for review and approval.",
        "schedule": "Mon / Wed / Fri",
        "runnable": False,
        "tags": ["ideas", "research", "sheets"],
    },
    {
        "id": "landing-pages",
        "name": "Landing Pages",
        "icon": "🌐",
        "description": "Generate production-ready HTML landing pages for tour launches, destinations, audiences, or competitor comparisons. Auto-mines real Google reviews for testimonials.",
        "schedule": "On demand",
        "runnable": True,
        "tags": ["website", "seo", "conversion"],
    },
    {
        "id": "skills-library",
        "name": "Skills Library",
        "icon": "🧠",
        "description": "Run any of the 50+ DWT skills (carousel-copy, blog-seo, ad-creative, marketing-psychology, etc.) directly from the hub. Skill markdown is loaded as a Gemini system prompt with auto-injected brand references.",
        "schedule": "On demand",
        "runnable": True,
        "tags": ["skills", "agents", "gemini"],
    },
]

# ── SEO bias config (drives Mon/Wed/Fri autopilot) ────────────────────────────

# 60% of destination posts should be international (Point C from GMB search audit)
INTERNATIONAL_KEYWORDS = [
    "vietnam", "dubai", "abu dhabi", "thailand", "pattaya", "bangkok",
    "singapore", "malaysia", "bali", "maldives", "bhutan", "sri lanka",
    "mauritius",
]
INTERNATIONAL_TARGET_SHARE = 0.60

# ~25% of posts are authority posts (universal positioning, no package — Point A from audit)
AUTHORITY_TARGET_COUNT_IN_LAST_8 = 2   # i.e. 2/8 ≈ 25%

# Detectable marker used to identify authority posts in recent GBP feed
AUTHORITY_MARKER = "#besttouroperatorinpune"

AUTHORITY_POSTS = [
    # A1 — Track Record
    """✈️ Looking for the best tour operator in Pune? Here's why 50,000+ travellers chose Dream World Tours over the last 16 years.

🏆 Pune's most trusted tour operator
• 50,000+ happy travellers
• 700+ Google reviews at 4.9 ⭐
• 16 years of group tour expertise
• Office in Nanded City, Sinhgad Road, Pune

What we run from Pune:
✅ Kashmir · Leh Ladakh · Sikkim · North-East India
✅ Dubai · Vietnam · Thailand · Singapore-Malaysia · Bali
✅ Char Dham · Amarnath Yatra · Religious tours
✅ Family group tours · Honeymoon packages

Why we're different from other Pune tour agencies:
• Real fixed departures — not just "on request"
• Pune-based tour managers travel with you
• Indian meals guaranteed on every international tour
• Transparent pricing, no hidden costs

Visit our Sinhgad Road office or WhatsApp us.

📍 Nanded City, Sinhgad Road, Pune

#besttouroperatorinpune #tourfrompune #dreamworldtours #grouptourfrompune""",

    # A2 — Social Proof
    """🌟 700+ Google reviews at 4.9 stars — Dream World Tours, Pune.

That number didn't happen by accident. It's what 50,000+ travellers said after their trips with us.

A few things our travellers consistently mention:
✅ "Pune-based tour manager was incredible"
✅ "Indian food on every meal, every day"
✅ "No hidden costs — exactly what was quoted"
✅ "Everything was organised, we just enjoyed"
✅ "Fixed departures actually departed on time"

Searching for the best travel agency in Pune? Read the reviews — that's the most honest comparison.

16 years · 50,000+ travellers · 4.9 ⭐ · 700+ reviews

What we run from Pune:
🇮🇳 Kashmir · Ladakh · Sikkim · North-East · Char Dham
🌍 Vietnam · Dubai · Thailand · Singapore-Malaysia · Bali

📍 Office: Nanded City, Sinhgad Road, Pune

#besttravelagencyinpune #besttouroperatorinpune #tourfrompune #dreamworldtours""",

    # A3 — Fixed Departure Specialist
    """🚀 Looking for a fixed departure group tour from Pune? You're in the right place.

Dream World Tours runs India's most reliable fixed departure tours from Pune — group tours that ACTUALLY depart on the dates we promise.

📅 Confirmed group departures from Pune for 2026:
• Kashmir & Leh Ladakh (8N/9D)
• Amarnath Yatra (5N/6D) — July-August
• Vietnam Luxury (7N/8D)
• Dubai & Abu Dhabi (5N/6D)
• Thailand · Singapore-Malaysia · Bali
• Sikkim-Darjeeling · North-East India · Char Dham

Why travellers trust DWT for fixed departures:
✅ 16 years · 50,000+ travellers · 4.9 ⭐ (700+ reviews)
✅ Real departures — we don't cancel last-minute
✅ Pune-based tour managers escort every batch
✅ All airfare + visas + Indian meals + insurance included
✅ Office in Pune — meet us in person before booking

📍 Nanded City, Sinhgad Road, Pune

#fixeddeparturetour #besttouroperatorinpune #tourfrompune #grouptour""",

    # A4 — Service Differentiator
    """💎 What sets Dream World Tours apart from other tour operators in Pune?

After 16 years and 50,000+ travellers, here's what makes us different:

1️⃣ Pune-based tour managers
We're not a call centre. Our tour managers are from Pune and travel WITH you on every group tour.

2️⃣ Indian meals guaranteed
Every international tour — Vietnam, Dubai, Thailand, Singapore — includes proper Indian meals. No hunting for food, no compromise.

3️⃣ Real fixed departures
We confirm departure dates 3-6 months in advance and stick to them.

4️⃣ Transparent pricing
What we quote is what you pay. No "extra activity charges" surprise on tour.

5️⃣ Office visit welcome
We're in Nanded City, Sinhgad Road, Pune. Come meet us, see the team, ask everything.

700+ Google reviews at 4.9 ⭐ — read them and compare.

#touroperatorsinpune #besttouroperatorinpune #grouptourfrompune #dreamworldtours""",

    # A5 — Local Authority / Office Visit
    """📍 Visit Dream World Tours — Pune's trusted tour operator on Sinhgad Road.

Looking for a tour agency in Sinhgad Road, Pune? We're right here, easy to find:

🏢 Walhekar Properties, 3rd Floor, Office No. 305
Near Destination Center, Nanded City
Sinhgad Road, Pune 411041

What you can do at our office:
✅ Meet the team that will plan your trip
✅ See real photos & feedback from past travellers
✅ Get detailed itineraries printed
✅ Discuss customisations face-to-face
✅ Confirm your booking with peace of mind

What we operate from Pune:
🇮🇳 Kashmir · Ladakh · Sikkim · North-East · Amarnath Yatra
🌍 Vietnam · Dubai · Thailand · Singapore-Malaysia

16 years · 50,000+ travellers · 700+ Google reviews at 4.9 ⭐

Office open Mon-Sat 10am-7pm.

#touragencypune #sinhgadroad #besttouroperatorinpune #travelagencyinpune""",
]


def _is_international(pkg: Dict) -> bool:
    name = (pkg.get("name", "") or "").lower()
    return any(kw in name for kw in INTERNATIONAL_KEYWORDS)


def _post_is_authority(post: Dict) -> bool:
    return AUTHORITY_MARKER in (post.get("summary", "") or "").lower()


def _post_is_international(post: Dict) -> bool:
    summary = (post.get("summary", "") or "").lower()
    return any(kw in summary for kw in INTERNATIONAL_KEYWORDS)


def _should_post_authority(recent_posts: List[Dict]) -> bool:
    """Return True if next post should be an authority post (target ~25% share)."""
    auth_count = sum(1 for p in recent_posts[:8] if _post_is_authority(p))
    return auth_count < AUTHORITY_TARGET_COUNT_IN_LAST_8


def _pick_authority_variant() -> tuple:
    """Pick which of the 5 authority posts to use, rotating by day-of-year. Returns (index, text)."""
    idx = (date.today().timetuple().tm_yday) % len(AUTHORITY_POSTS)
    return idx, AUTHORITY_POSTS[idx]


def _build_authority_image_prompt() -> str:
    """Generic DWT-branded image prompt for authority posts (no destination tied)."""
    return (
        "Premium Google Business Profile image for Dream World Tours, Pune's trusted tour operator. "
        "Square 1024x1024. "
        "BACKGROUND: A warm, aspirational world-travel collage — soft, blurred glimpses of iconic destinations "
        "(Burj Khalifa, Halong Bay, Kashmir Dal Lake, Singapore skyline) blended into a sophisticated golden-hour palette. "
        "CENTER: Bold white text overlay 'PUNE'S MOST TRUSTED TOUR OPERATOR' large condensed sans-serif. "
        "Below in amber (#f5c518): '50,000+ TRAVELLERS · 700+ REVIEWS · 4.9 ★'. "
        "Below in white smaller: '16 YEARS · INDIA & INTERNATIONAL GROUP TOURS'. "
        "TOP-LEFT CORNER: 'DREAM WORLD TOURS' small clean teal #0c6980 pill badge in white text. "
        "BOTTOM-RIGHT CORNER: 'dreamworldtours.in' tiny clean white text. "
        "Clean, premium, editorial. No people. No clutter. Sophisticated travel-brand aesthetic."
    )


# ── GBP helpers ───────────────────────────────────────────────────────────────

def _full_path() -> str:
    if GBP_LOCATION_ID and GBP_LOCATION_ID.startswith("accounts/"):
        return GBP_LOCATION_ID
    return f"{GBP_ACCOUNT_ID}/{GBP_LOCATION_ID}"


def _get_token() -> str:
    resp = requests.post(OAUTH_URL, data={
        "client_id": GBP_CLIENT_ID,
        "client_secret": GBP_CLIENT_SECRET,
        "refresh_token": GBP_REFRESH_TOKEN,
        "grant_type": "refresh_token",
    }, timeout=30)
    token = resp.json().get("access_token")
    if not token:
        raise RuntimeError(f"Token refresh failed: {resp.json()}")
    return token


def _get_recent_gbp_posts(n: int = 8) -> List[Dict]:
    try:
        token = _get_token()
        resp = requests.get(
            f"{GMB_API}/{_full_path()}/localPosts",
            params={"pageSize": n},
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        posts = resp.json().get("localPosts", [])
        result = []
        for p in posts:
            media_urls = [
                m.get("googleUrl") or m.get("sourceUrl")
                for m in p.get("media", [])
                if m.get("googleUrl") or m.get("sourceUrl")
            ]
            result.append({
                "name": p.get("name", ""),
                "summary": p.get("summary", ""),
                "createTime": p.get("createTime", ""),
                "state": p.get("state", ""),
                "mediaUrl": media_urls[0] if media_urls else None,
            })
        return result
    except Exception:
        return []


def _already_posted_today() -> bool:
    today = date.today().isoformat()
    try:
        token = _get_token()
        resp = requests.get(
            f"{GMB_API}/{_full_path()}/localPosts",
            params={"pageSize": 3},
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        for p in resp.json().get("localPosts", []):
            if p.get("createTime", "").startswith(today):
                return True
    except Exception:
        pass
    return False


def _pick_destination(recent_posts: List[Dict]) -> Optional[Dict]:
    """Pick the next destination to post about, biased 60% toward international packages."""
    packages = load_packages()
    if not packages:
        return None

    # Build a ranked list of recently-posted slugs by matching post text to package names/slugs.
    # Match against ALL name words + slug words (not just first 2). Skip generic stopwords.
    STOPWORDS = {"tour", "yatra", "the", "and", "of", "with", "shri", "our", "an", "package", "group", "trip", "from", "pune", "mumbai"}
    recent_slugs: List[str] = []
    for post in recent_posts:
        summary = post.get("summary", "").lower()
        if not summary:
            continue
        for pkg in packages:
            # Collect all identifying words from name + slug
            words = set(pkg["name"].lower().split()) | set(pkg["slug"].lower().replace("-", " ").split())
            # Filter stopwords + very short words
            candidates = [w for w in words if len(w) > 3 and w not in STOPWORDS]
            if any(w in summary for w in candidates):
                recent_slugs.append(pkg["slug"])
                break

    # Also shuffle the packages so we don't always iterate in the same order
    # (deterministic per-day so same day = same rotation but different days = different)
    import random as _random
    _rng = _random.Random(date.today().toordinal())  # deterministic per day

    # Decide preferred pool based on recent international vs domestic split
    # (excluding authority posts which are not destination posts)
    dest_posts = [p for p in recent_posts[:8] if not _post_is_authority(p)]
    intl_recent = sum(1 for p in dest_posts if _post_is_international(p))
    dom_recent  = len(dest_posts) - intl_recent
    total       = intl_recent + dom_recent
    intl_share  = (intl_recent / total) if total > 0 else 0
    prefer_intl = intl_share < INTERNATIONAL_TARGET_SHARE

    intl_pkgs = [p for p in packages if _is_international(p)]
    dom_pkgs  = [p for p in packages if not _is_international(p)]
    # Shuffle both pools with per-day seed so daily rotation cycles through all tours
    _rng.shuffle(intl_pkgs)
    _rng.shuffle(dom_pkgs)
    primary_pool   = intl_pkgs if prefer_intl else dom_pkgs
    fallback_pool  = dom_pkgs  if prefer_intl else intl_pkgs

    # Avoid recently-posted packages within the preferred pool
    avoid_n = max(1, len(packages) // 3)
    avoid = set(recent_slugs[:avoid_n])

    # 1) Try preferred pool first, skipping recents
    for pkg in primary_pool:
        if pkg["slug"] not in avoid:
            return pkg

    # 2) Fall back to other pool, still avoiding recents
    for pkg in fallback_pool:
        if pkg["slug"] not in avoid:
            return pkg

    # 3) All packages were recent — return least-recent from preferred pool, else any
    return (primary_pool or fallback_pool or packages)[0]


def _pick_template(weekday: int) -> str:
    if weekday == 0:
        return "departure"
    elif weekday == 2:
        return "spotlight"
    return "urgency"


def _upcoming_departures(pkg: Dict) -> List[str]:
    """Return only departure dates that are today or in the future.
    Handles both 'DD Mon YYYY' (e.g. '02 Aug 2026') and 'Mon YYYY' (e.g. 'Aug 2026') formats.
    Falls back to original list if all dates are past or parsing fails."""
    import re
    from datetime import datetime as _dt

    MONTHS = {"Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
              "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12}
    today = date.today()

    def parse_dep(s: str):
        """Return (year, month, day) tuple or None if unparseable."""
        s = s.strip()
        # Try "DD Mon YYYY" first
        m = re.match(r"(\d{1,2})\s+([A-Za-z]{3})[a-z]*\s+(\d{4})", s)
        if m:
            d, mon, y = int(m.group(1)), m.group(2)[:3].capitalize(), int(m.group(3))
            if mon in MONTHS:
                return (y, MONTHS[mon], d)
        # Try "Mon YYYY" (assume LAST day of month — treats current month as still upcoming)
        m = re.match(r"([A-Za-z]{3})[a-z]*\s+(\d{4})", s)
        if m:
            mon, y = m.group(1)[:3].capitalize(), int(m.group(2))
            if mon in MONTHS:
                # Last day of month
                import calendar as _cal
                last_day = _cal.monthrange(y, MONTHS[mon])[1]
                return (y, MONTHS[mon], last_day)
        return None

    raw = pkg.get("departures", []) or []
    upcoming = []
    for d_str in raw:
        parsed = parse_dep(d_str)
        if parsed is None:
            # Unparseable — keep it (better to show than lose)
            upcoming.append((None, d_str))
            continue
        y, m, d = parsed
        try:
            dep_date = date(y, m, d)
        except ValueError:
            upcoming.append((None, d_str))
            continue
        if dep_date >= today:
            upcoming.append((dep_date, d_str))

    # Sort chronologically (unparseable at end)
    upcoming.sort(key=lambda t: (t[0] is None, t[0]))
    result = [s for _, s in upcoming]
    # Fallback: if everything filtered out, return original list (better than empty)
    return result if result else raw


def _build_post_text(pkg: Dict, template: str) -> str:
    upcoming = _upcoming_departures(pkg)
    deps = " | ".join(upcoming[:3]) if upcoming else " | ".join(pkg["departures"][:3])
    next_dep = upcoming[0] if upcoming else pkg["departures"][0]
    flights_line = "✅ Return flights included" if pkg["flights"] else "❌ Flights not included — book separately"
    # Strip non-alphanumeric chars so hyphens/ampersands don't break hashtags
    hashtag = "".join(c for c in pkg["name"].lower() if c.isalnum() or c == " ").replace(" ", "")

    intl_or_dom = "international" if _is_international(pkg) else "domestic"

    if template == "departure":
        return f"""✈️ {pkg["name"]} Tour Package from Pune — {pkg["duration"]} Group Tour

Looking for a {pkg["name"]} tour package from Pune? Join our exclusive group departures.

📅 Upcoming Departures: {deps}
💰 Starting {pkg["price_display"]}/person

What's included:
✅ {pkg["highlights"][0]}
✅ {pkg["highlights"][1]}
✅ {pkg["highlights"][2]}
✅ All meals — Indian food guaranteed
{flights_line}
✅ Pune-based DWT tour manager travels with the group

Dream World Tours, Pune — 50,000+ travellers · 700+ reviews at 4.9 ⭐

Seats fill fast. WhatsApp us to confirm your spot 👇

#{hashtag}fromPune #{hashtag}tour #tourfrompune #{intl_or_dom}tourfrompune #dreamworldtours #grouptour2026""".strip()

    elif template == "spotlight":
        return f"""🌟 {pkg["spotlight_fact"]}

{pkg["name"]} Tour Package from Pune | {pkg["duration"]} | {pkg["price_display"]}/person

What you'll experience:
• {pkg["highlights"][0]}
• {pkg["highlights"][1]}
• {pkg["highlights"][2]}
• {pkg["highlights"][3]}
• {pkg["highlights"][4]}
• All meals at Indian restaurants
• Pune-based tour manager travels with the group

📅 Next departure: {next_dep}

Dream World Tours — Pune's most trusted tour operator. 700+ reviews at 4.9 ⭐

DM or WhatsApp us for the detailed itinerary.

#{hashtag}fromPune #{intl_or_dom}tourfrompune #grouptravel #tourfrompune #dreamworldtours""".strip()

    else:  # urgency
        return f"""🚨 Only a Few Seats Left — {pkg["name"]} Tour Package from Pune ({pkg["duration"]})

📅 Next departure: {next_dep}
💰 {pkg["price_display"]}/person | {"Flights from Pune included ✅" if pkg["flights"] else "Flights not included — book separately"}

Don't miss out:
✅ {pkg["highlights"][0]}
✅ {pkg["highlights"][1]}
✅ {pkg["highlights"][2]}
✅ All meals — Indian food, every day
✅ Pune-based DWT tour manager

This batch is almost full. WhatsApp us NOW to check availability 👇

Dream World Tours, Pune · 50,000+ travellers · 4.9 ⭐

#{hashtag}fromPune #{hashtag}tour #dreamworldtours #tourfrompune #{intl_or_dom}tourfrompune #lastfewseats""".strip()


def _build_image_prompt(pkg: Dict) -> str:
    return (
        f"Premium Google Business Profile post image for Dream World Tours travel agency. "
        f"Square 1024x1024. "
        f"BACKGROUND: Ultra-photorealistic {pkg['scene']}. Golden hour lighting. National Geographic quality. "
        f"OVERLAY: Dark teal (#0c6980) gradient bar covering bottom 22% of image, semi-transparent. "
        f"LEFT of bar: Bold white '{pkg['name']}' large font | '{pkg['duration']}' smaller white below. "
        f"CENTER of bar: Thin white vertical divider line. "
        f"RIGHT of bar: '{pkg['price_display']}' bold amber (#f5c518) large | "
        f"'per person | {'Flights Incl.' if pkg['flights'] else 'Flights Excl.'}' small white below. "
        f"TOP-LEFT CORNER: Small dark teal pill badge 'DREAM WORLD TOURS' in white text. "
        f"Clean, premium, aspirational. No people in foreground. No clutter."
    )


async def _generate_image(prompt: str, save_path: Path) -> tuple:
    """Returns (success: bool, error_msg: str).
    Uses gemini-3-pro-image-preview — same model as nano-banana MCP (proven to work).
    Falls back to gemini-2.0-flash-preview-image-generation.
    """
    loop = asyncio.get_event_loop()

    def _call(model: str, body: dict):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
        return requests.post(url, json=body, timeout=120)

    def _extract_image(data: dict):
        for cand in data.get("candidates", []):
            for part in cand.get("content", {}).get("parts", []):
                b64 = part.get("inlineData", {}).get("data", "")
                if b64:
                    return b64
        return None

    # — Attempt 1: gemini-3-pro-image-preview (same as nano-banana MCP) —
    body1 = {"contents": [{"parts": [{"text": prompt}]}]}
    err1 = "not tried"
    try:
        resp = await loop.run_in_executor(None, lambda: _call("gemini-3-pro-image-preview", body1))
        data = resp.json()
        if "error" not in data:
            b64 = _extract_image(data)
            if b64:
                save_path.parent.mkdir(parents=True, exist_ok=True)
                save_path.write_bytes(base64.b64decode(b64))
                return True, ""
        err1 = data.get("error", {}).get("message") or f"No image in response. Keys: {list(data.keys())}"
    except Exception as e:
        err1 = str(e)

    # — Attempt 2: gemini-2.0-flash-preview-image-generation —
    body2 = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseModalities": ["IMAGE", "TEXT"]},
    }
    try:
        resp = await loop.run_in_executor(
            None, lambda: _call("gemini-2.0-flash-preview-image-generation", body2)
        )
        data = resp.json()
        if "error" in data:
            err2 = data["error"].get("message", str(data["error"]))
            return False, f"gemini-3-pro: {err1} | flash: {err2}"
        b64 = _extract_image(data)
        if b64:
            save_path.parent.mkdir(parents=True, exist_ok=True)
            save_path.write_bytes(base64.b64decode(b64))
            return True, ""
        return False, f"gemini-3-pro: {err1} | flash: no image in response"
    except Exception as e:
        return False, f"gemini-3-pro: {err1} | flash: {str(e)}"


def _upload_to_imgbb(image_path: Path) -> str:
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    resp = requests.post(
        "https://api.imgbb.com/1/upload",
        data={"key": IMGBB_API_KEY, "image": b64, "name": image_path.stem},
        timeout=60,
    )
    result = resp.json()
    if not result.get("success"):
        raise RuntimeError(f"imgbb upload failed: {result}")
    return result["data"]["url"]


def _post_to_gbp(text: str, image_path: Optional[Path]) -> Dict:
    token = _get_token()

    image_url = None
    if image_path and image_path.exists() and IMGBB_API_KEY:
        try:
            image_url = _upload_to_imgbb(image_path)
        except Exception as e:
            # Graceful fallback: if imgbb is down or fails, post text-only
            # (better than failing the whole GMB post over a hosting outage)
            print(f"[gmb] ⚠️ imgbb upload failed — posting text-only. Error: {e}")
            image_url = None

    body: Dict = {
        "languageCode": "en-US",
        "summary": text,
        "topicType": "STANDARD",
        "callToAction": {
            "actionType": "LEARN_MORE",
            "url": f"https://wa.me/{WHATSAPP}",
        },
    }
    if image_url:
        body["media"] = [{"mediaFormat": "PHOTO", "sourceUrl": image_url}]

    resp = requests.post(
        f"{GMB_API}/{_full_path()}/localPosts",
        json=body,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=60,
    )
    data = resp.json()
    if "name" in data:
        return {"success": True, "post_name": data["name"], "image_url": image_url}
    return {"success": False, "error": data.get("error", {}).get("message", str(data))}


# ── Pipeline (reused by endpoint + APScheduler) ───────────────────────────────

async def run_gmb_pipeline(run_id: str, force: bool = False):
    run_store.update_run(run_id, status="running")
    loop = asyncio.get_event_loop()

    try:
        # NOTE: Duplicate-post guard removed per user request (2026-07-22).
        # User wants to post freely at any time; scheduled cron runs on its own cadence.
        # _already_posted_today() function is kept in the file for reference/future use.

        # Step 1: Prepare
        await run_store.push_event(run_id, "preparing", "Picking post mode (authority vs destination)...", 5)
        recent = await loop.run_in_executor(None, lambda: _get_recent_gbp_posts(8))
        today = date.today()
        today_str = today.strftime("%Y-%m-%d")

        # Decide post mode: authority (~25%) or destination (~75%, biased 60% international)
        use_authority = _should_post_authority(recent)

        if use_authority:
            auth_idx, post_text = _pick_authority_variant()
            template     = f"authority-{auth_idx + 1}"
            image_prompt = _build_authority_image_prompt()
            image_path   = IMGS_DIR / f"gmb-authority-{auth_idx + 1}-{today_str}.png"
            pkg          = None
            display_name = f"Pune Tour Operator Authority (#{auth_idx + 1})"

            await run_store.push_event(
                run_id, "prepared",
                f"Ready: {display_name} / {template}",
                20,
                {
                    "destination": display_name,
                    "template": template,
                    "post_text": post_text,
                    "day": today.strftime("%A"),
                    "mode": "authority",
                },
            )
        else:
            pkg = _pick_destination(recent)
            if not pkg:
                err = "No packages found. Add PDFs to reference/itineraries/ and run sync."
                run_store.fail_run(run_id, err)
                await run_store.push_event(run_id, "error", err, 0)
                return
            template     = _pick_template(today.weekday())
            post_text    = _build_post_text(pkg, template)
            image_prompt = _build_image_prompt(pkg)
            image_path   = IMGS_DIR / f"gmb-{pkg['slug']}-{today_str}.png"
            display_name = pkg["name"]

            await run_store.push_event(
                run_id, "prepared",
                f"Ready: {display_name} / {template} ({'intl' if _is_international(pkg) else 'domestic'})",
                20,
                {
                    "destination": display_name,
                    "template": template,
                    "post_text": post_text,
                    "day": today.strftime("%A"),
                    "mode": "destination",
                    "is_international": _is_international(pkg),
                },
            )

        # Step 1.5: Stop-slop pass — remove AI writing patterns before posting
        await run_store.push_event(run_id, "polishing", "Polishing post (stop-slop)...", 25)
        from services.stop_slop import clean as stop_slop_clean
        post_text_original = post_text
        slop_result = await stop_slop_clean(post_text)
        post_text = slop_result["cleaned"]
        if slop_result["changed"]:
            print(f"[stop-slop] GMB post revised — {len(post_text_original)} → {len(post_text)} chars")

        # Step 2: Generate image
        await run_store.push_event(
            run_id, "generating_image",
            f"Generating {display_name} image via Gemini...",
            30,
        )
        image_ok, image_err = await _generate_image(image_prompt, image_path)
        image_serve_url = None

        if image_ok:
            image_serve_url = f"/api/gmb/images/{image_path.name}"
            await run_store.push_event(
                run_id, "image_ready",
                f"Image generated: {image_path.name}",
                60,
                {"image_url": image_serve_url},
            )
        else:
            await run_store.push_event(
                run_id, "image_ready",
                f"Image generation failed — posting text only. ({image_err})",
                60,
                {"error": image_err},
            )

        # Step 3: Post
        await run_store.push_event(run_id, "posting", "Posting to Google Business Profile...", 70)
        result = await loop.run_in_executor(
            None,
            lambda: _post_to_gbp(post_text, image_path if image_ok else None),
        )

        if result["success"]:
            complete_data = {
                "destination": display_name,
                "template": template,
                "post_name": result.get("post_name"),
                "image_url": result.get("image_url"),       # imgbb permanent URL
                "local_image_url": image_serve_url,
                "post_text": post_text,
                "post_text_original": post_text_original,    # pre-stop-slop version
                "stop_slop_applied": slop_result.get("changed", False),
                "stop_slop_error": slop_result.get("error"),
                "day": today.strftime("%A"),
                "mode": "authority" if use_authority else "destination",
                "is_international": _is_international(pkg) if pkg else None,
            }
            run_store.complete_run(
                run_id,
                topic=f"{display_name} — {template}",
                slides=[],
                caption=post_text,
            )
            await run_store.push_event(
                run_id, "complete",
                "Posted to Google Business Profile ✓",
                100,
                complete_data,
            )
            from services import db as _db
            _db.save_run(run_id, "gmb", "complete",
                         topic=f"{display_name} — {template}", result=complete_data)
        else:
            run_store.fail_run(run_id, result["error"])
            await run_store.push_event(run_id, "error", result["error"], 0)
            from services import db as _db
            _db.save_run(run_id, "gmb", "failed", error=result["error"])

    except Exception as e:
        run_store.fail_run(run_id, str(e))
        await run_store.push_event(run_id, "error", str(e), 0)
        raise


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/gmb/agents")
async def list_agents():
    return AGENTS


@router.get("/gmb/history")
async def gmb_history():
    loop = asyncio.get_event_loop()
    posts = await loop.run_in_executor(None, lambda: _get_recent_gbp_posts(8))
    return {"posts": posts}


@router.post("/gmb/run")
async def run_gmb(background_tasks: BackgroundTasks, force: bool = False):
    run_id = run_store.new_run(WorkflowType.GMB)
    background_tasks.add_task(run_gmb_pipeline, run_id=run_id, force=force)
    return {
        "run_id": run_id,
        "workflow": "gmb",
        "status": "queued",
        "message": f"Pipeline started. Stream at /api/stream/{run_id}",
    }


@router.get("/gmb/images/{filename}")
async def serve_gmb_image(filename: str):
    img_path = IMGS_DIR / filename
    if not img_path.exists():
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(str(img_path), media_type="image/png")


# ─── GMB Audit ────────────────────────────────────────────────────────────────

@router.get("/gmb/audit")
async def gmb_audit():
    """Run full audit of DWT's GBP profile. ~5-10s (multiple API calls)."""
    from services import gmb_audit as audit_svc
    try:
        result = await asyncio.to_thread(audit_svc.run_audit)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=f"Audit failed: {str(e)[:300]}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected: {str(e)[:300]}")
    return result


# ─── GMB Competitor + Keyword Intel ──────────────────────────────────────────

@router.post("/gmb/competitors")
async def gmb_competitors(payload: dict = Body(default={})):
    """
    Scrape DWT's competitors via Apify (Google Maps reviews scraper).
    Body (all optional):
      names: list of competitor search queries (defaults to DWT preset)
      force_refresh: bool (default False; uses 7d cache)
    Returns: [{name, place_name, rating, review_count, reviews, ...}]
    """
    from services import gmb_competitor_intel as ci

    names = payload.get("names") or None
    force = bool(payload.get("force_refresh", False))

    try:
        # 5 competitors × Apify scrape can take 2-3 min if no cache; offload to thread
        results = await asyncio.to_thread(ci.scrape_competitors, names, force)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=f"Competitor scrape failed: {str(e)[:300]}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected: {str(e)[:300]}")
    return {"competitors": results, "count": len(results)}


@router.post("/gmb/keyword-themes")
async def gmb_keyword_themes(payload: dict = Body(default={})):
    """
    Extract praise/complaint themes from a set of reviews via Claude.
    Body:
      source: 'dwt' (default) — pulls DWT reviews via GBP API
              'competitor' — uses payload.competitor_name to read cached competitor reviews
      competitor_name: required if source='competitor'
    Returns: {praise_themes, complaint_themes, notable_quotes, review_count}
    """
    from services import gmb_audit as audit_svc
    from services import gmb_competitor_intel as ci

    source = (payload.get("source") or "dwt").lower().strip()

    if source == "dwt":
        try:
            token = await asyncio.to_thread(audit_svc.get_access_token)
            gbp_reviews = await asyncio.to_thread(audit_svc.fetch_reviews, token)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Fetching DWT reviews failed: {str(e)[:300]}")
        # GBP review shape → normalized
        star_map = {"FIVE": 5, "FOUR": 4, "THREE": 3, "TWO": 2, "ONE": 1}
        reviews = [
            {"text": r.get("comment", ""), "stars": star_map.get(r.get("starRating", ""), 0)}
            for r in gbp_reviews if r.get("comment")
        ]
        brand_label = "Dream World Tours"
    elif source == "competitor":
        name = (payload.get("competitor_name") or "").strip()
        if not name:
            raise HTTPException(400, "competitor_name required when source='competitor'")
        # Pull from cache only — caller should run /competitors first
        cached = ci._load_cache(name)
        if not cached or not cached.get("found"):
            raise HTTPException(404, f"No cached data for '{name}'. Run /api/gmb/competitors first.")
        reviews = cached.get("reviews", []) or []
        brand_label = cached.get("place_name") or name
    else:
        raise HTTPException(400, "source must be 'dwt' or 'competitor'")

    try:
        themes = await asyncio.to_thread(ci.extract_keyword_themes, reviews, brand_label)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=f"Theme extraction failed: {str(e)[:300]}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected: {str(e)[:300]}")

    themes["source"] = source
    themes["brand_label"] = brand_label
    return themes


# ─── GMB Review Auto-Reply (draft → approve → post) ──────────────────────────

@router.get("/gmb/reviews")
async def gmb_reviews(draft: bool = True, limit: int = 30):
    """
    List recent DWT reviews.
    Query:
      draft: bool (default True) — if True, generate Claude reply drafts for unreplied reviews
      limit: int (default 30, max 100)
    """
    from services import gmb_review_responder as rr

    limit = max(1, min(100, int(limit)))

    try:
        token = await asyncio.to_thread(rr.get_access_token)
        reviews = await asyncio.to_thread(rr.fetch_pending_reviews, token, limit)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Fetching reviews failed: {str(e)[:300]}")

    if draft:
        try:
            reviews = await asyncio.to_thread(rr.draft_replies_bulk, reviews)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Drafting replies failed: {str(e)[:300]}")

    pending_count = sum(1 for r in reviews if r.get("needs_reply"))
    return {"reviews": reviews, "count": len(reviews), "pending_count": pending_count}


@router.post("/gmb/reviews/reply")
async def gmb_post_reply(payload: dict = Body(...)):
    """
    Post an approved reply to a Google review.
    Body:
      review_name: full GBP resource name (accounts/X/locations/Y/reviews/Z)
      reply_text: the approved reply text
    """
    from services import gmb_review_responder as rr

    review_name = (payload.get("review_name") or "").strip()
    reply_text = (payload.get("reply_text") or "").strip()

    if not review_name:
        raise HTTPException(400, "review_name is required")
    if not reply_text:
        raise HTTPException(400, "reply_text is required")
    if len(reply_text) > 4000:
        raise HTTPException(400, "reply_text exceeds 4000 chars")

    try:
        token = await asyncio.to_thread(rr.get_access_token)
        result = await asyncio.to_thread(rr.post_reply, token, review_name, reply_text)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Reply post failed: {str(e)[:400]}")

    return {"status": "posted", "review_name": review_name, "gbp_response": result}


@router.post("/gmb/reviews/draft")
async def gmb_redraft_reply(payload: dict = Body(...)):
    """
    Regenerate a draft for a single review (user clicks 'Re-draft').
    Body:
      comment: review text
      stars: 1-5
      reviewer_name: optional
    """
    from services import gmb_review_responder as rr

    comment = (payload.get("comment") or "").strip()
    stars = int(payload.get("stars", 5))
    reviewer_name = (payload.get("reviewer_name") or "").strip()

    try:
        reply = await asyncio.to_thread(rr.draft_reply, comment, stars, reviewer_name)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Draft failed: {str(e)[:300]}")

    return {"draft_reply": reply}
