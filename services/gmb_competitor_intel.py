"""
GMB Competitor + Keyword Intel — scrape competitors' Google Maps profiles via Apify,
extract review themes via Claude, compare to DWT.

Two public functions:
  scrape_competitors(names: list[str]) → list of competitor profiles
  extract_keyword_themes(reviews: list[dict]) → {themes, gaps, top_quotes}
"""
import json
import os
import time
from pathlib import Path

import requests

from services.llm_chat import gemini_chat_json

APIFY_TOKEN = os.environ.get("APIFY_TOKEN")

# Same scraper that review_miner.py uses — already known to work
APIFY_ACTOR = "compass~google-maps-reviews-scraper"
APIFY_RUN_URL = f"https://api.apify.com/v2/acts/{APIFY_ACTOR}/run-sync-get-dataset-items"

CACHE_DIR = Path(__file__).parent.parent / "outputs" / "review-cache"
COMPETITOR_CACHE_TTL_HOURS = 24 * 7  # weekly refresh

# Default DWT competitor set — Pune travel agencies that appeared in search terms report
DEFAULT_COMPETITORS = [
    "Kesari Tours Pune",
    "Veena World Pune",
    "Thomas Cook Pune",
    "SOTC Travel Pune",
    "Girikand Travels Pune",
]


def _cache_path(name: str) -> Path:
    safe = "".join(c if c.isalnum() else "_" for c in name.lower())[:60]
    return CACHE_DIR / f"competitor_{safe}.json"


def _load_cache(name: str) -> dict | None:
    p = _cache_path(name)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text())
        cached_at = data.get("cached_at", 0)
        if (time.time() - cached_at) > COMPETITOR_CACHE_TTL_HOURS * 3600:
            return None
        return data
    except Exception:
        return None


def _save_cache(name: str, payload: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    payload["cached_at"] = time.time()
    _cache_path(name).write_text(json.dumps(payload, ensure_ascii=False, indent=2))


def _scrape_one(name: str, max_reviews: int = 30) -> dict:
    """Run Apify scraper for a single competitor search query."""
    if not APIFY_TOKEN:
        raise RuntimeError("APIFY_TOKEN not set")

    body = {
        "searchStringsArray": [name],
        "maxCrawledPlacesPerSearch": 1,
        "maxReviews": max_reviews,
        "language": "en",
        "reviewsSort": "newest",
    }
    headers = {"Content-Type": "application/json"}
    url = f"{APIFY_RUN_URL}?token={APIFY_TOKEN}"

    try:
        r = requests.post(url, json=body, headers=headers, timeout=180)
        r.raise_for_status()
    except requests.RequestException as e:
        raise RuntimeError(f"Apify scrape failed for {name}: {str(e)[:200]}")

    items = r.json() if r.content else []
    if not items:
        return {"name": name, "found": False, "error": "No results from Apify"}

    place = items[0]
    reviews = place.get("reviews", []) or []

    return {
        "name": name,
        "found": True,
        "place_name": place.get("title") or place.get("name"),
        "address": place.get("address"),
        "rating": place.get("totalScore"),
        "review_count": place.get("reviewsCount"),
        "categories": place.get("categories") or [],
        "phone": place.get("phone"),
        "website": place.get("website"),
        "image_url": place.get("imageUrl"),
        "located_in": place.get("locatedIn"),
        "permanently_closed": place.get("permanentlyClosed"),
        "reviews": [
            {
                "name": rv.get("name"),
                "stars": rv.get("stars"),
                "text": rv.get("text") or "",
                "published_at": rv.get("publishedAtDate"),
                "owner_reply": (rv.get("responseFromOwnerText") or "")[:500],
            }
            for rv in reviews[:max_reviews]
        ],
    }


def scrape_competitors(names: list[str] | None = None, force_refresh: bool = False) -> list[dict]:
    """Get profile + reviews for each competitor. Uses cache (7d TTL) unless force_refresh."""
    names = names or DEFAULT_COMPETITORS
    results = []
    for name in names:
        if not force_refresh:
            cached = _load_cache(name)
            if cached:
                cached["from_cache"] = True
                results.append(cached)
                continue
        try:
            data = _scrape_one(name)
            data["from_cache"] = False
            _save_cache(name, data)
            results.append(data)
        except Exception as e:
            results.append({"name": name, "found": False, "error": str(e)[:200], "from_cache": False})
    return results


# ─── Keyword / theme extraction via Gemini ────────────────────────────────────

def extract_keyword_themes(reviews: list[dict], brand_label: str = "Dream World Tours") -> dict:
    """
    Use Gemini to extract praise themes, complaint themes, and notable quotes from reviews.
    Input: list of {text, stars} dicts. Returns structured themes.
    """
    if not reviews:
        return {"praise_themes": [], "complaint_themes": [], "notable_quotes": [], "review_count": 0}

    # Compact the reviews for the prompt — first ~80 reviews, trimmed text
    snippet = []
    for rv in reviews[:80]:
        text = (rv.get("text") or "").strip()
        if not text:
            continue
        stars = rv.get("stars") or rv.get("starRating")
        snippet.append(f"[{stars}★] {text[:280]}")

    if not snippet:
        return {"praise_themes": [], "complaint_themes": [], "notable_quotes": [], "review_count": 0}

    reviews_block = "\n".join(f"R{i+1}. {s}" for i, s in enumerate(snippet))

    system = (
        f"You are analyzing Google reviews for {brand_label}, a Pune-based travel tour operator. "
        "Extract structured themes from the reviews. Return JSON only."
    )
    user = f"""Reviews ({len(snippet)} total):
{reviews_block}

Return JSON with this exact schema:
{{
  "praise_themes": [
    {{"theme": "short label (3-5 words)", "mentions": <int>, "example": "<short representative quote, <100 chars>"}}
  ],
  "complaint_themes": [
    {{"theme": "short label (3-5 words)", "mentions": <int>, "example": "<short representative quote, <100 chars>"}}
  ],
  "notable_quotes": [
    {{"quote": "<powerful 1-line review quote, <140 chars>", "stars": <int>, "topic": "<theme>"}}
  ]
}}

Rules:
- Up to 8 praise_themes, sorted by mentions descending. Be specific ("tour manager Sumit", "Kashmir houseboat", "Pune pickup punctuality") not generic ("good service").
- Up to 5 complaint_themes (can be empty). Be specific.
- Up to 5 notable_quotes — punchy, save-worthy lines that could be used in marketing."""

    try:
        themes = gemini_chat_json(system=system, user=user, max_tokens=8000)
    except RuntimeError as e:
        raise RuntimeError(f"Gemini theme extraction failed: {str(e)[:300]}")

    themes["review_count"] = len(snippet)
    return themes


# ─── Comparison helper ────────────────────────────────────────────────────────

def build_comparison(dwt_profile: dict, competitors: list[dict]) -> dict:
    """Side-by-side metrics table — DWT vs each competitor."""
    rows = []
    rows.append({
        "name": dwt_profile.get("name", "Dream World Tours"),
        "is_dwt": True,
        "rating": dwt_profile.get("rating"),
        "review_count": dwt_profile.get("review_count"),
        "categories": dwt_profile.get("categories", [])[:3],
        "website": dwt_profile.get("website"),
        "image_url": dwt_profile.get("image_url"),
    })
    for c in competitors:
        rows.append({
            "name": c.get("place_name") or c.get("name"),
            "is_dwt": False,
            "rating": c.get("rating"),
            "review_count": c.get("review_count"),
            "categories": c.get("categories", [])[:3],
            "website": c.get("website"),
            "image_url": c.get("image_url"),
            "error": c.get("error") if not c.get("found", True) else None,
        })
    return {"rows": rows}
