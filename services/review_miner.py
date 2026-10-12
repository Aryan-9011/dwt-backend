"""
Review Miner — Scrapes Google Maps reviews via Apify and returns testimonial-ready quotes.

Used by:
- Landing Page Agent (to replace placeholder testimonials with real review excerpts)
- Future content production (caption ideas, ad creative, brand voice studies)

How it works:
1. Call Apify's `compass/google-maps-reviews-scraper` for DWT's Google Business Profile
2. Filter reviews by minimum star rating + optional keyword (e.g. "Kashmir", "Vietnam")
3. Truncate to testimonial length (1-2 sentences)
4. Return as a list of {quote, author, rating, package_match}

Cache responses for 7 days to avoid hammering Apify.
"""
import os
import json
import asyncio
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
import httpx

APIFY_TOKEN = os.environ.get("APIFY_TOKEN")
DWT_SEARCH_QUERY = "Dream World Tours Pvt Ltd Nanded City Sinhgad Road Pune"

REVIEWS_ACTOR = "compass~google-maps-reviews-scraper"
CACHE_DIR = Path(__file__).parent.parent / "outputs" / "review-cache"
CACHE_TTL_DAYS = 7


def _cache_path() -> Path:
    return CACHE_DIR / "dwt-reviews.json"


def _read_cache() -> dict | None:
    p = _cache_path()
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text())
        fetched = datetime.fromisoformat(data["fetched_at"])
        # Compare timezone-aware datetimes
        if fetched.tzinfo is None:
            fetched = fetched.replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - fetched
        if age.days < CACHE_TTL_DAYS:
            return data
    except Exception:
        pass
    return None


def _write_cache(data: dict):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _cache_path().write_text(json.dumps(data, indent=2, default=str))


async def _fetch_reviews_from_apify(limit: int = 200) -> list:
    """Fetch raw reviews from Apify's Google Maps Reviews Scraper."""
    if not APIFY_TOKEN:
        raise RuntimeError("APIFY_TOKEN not set on this environment")

    url = f"https://api.apify.com/v2/acts/{REVIEWS_ACTOR}/run-sync-get-dataset-items?token={APIFY_TOKEN}&timeout=180"
    body = {
        "searchStringsArray": [DWT_SEARCH_QUERY],
        "maxReviews": limit,
        "language": "en",
        "reviewsSort": "newest",
        "maxCrawledPlacesPerSearch": 1,
        "deeperCityScrape": False,
    }
    try:
        async with httpx.AsyncClient(timeout=200) as client:
            r = await client.post(url, json=body)
            r.raise_for_status()
            data = r.json()
            print(f"[review_miner] Apify returned {len(data) if isinstance(data, list) else 'non-list'} items. First item keys: {list(data[0].keys())[:10] if (isinstance(data, list) and data and isinstance(data[0], dict)) else 'n/a'}")
            return data if isinstance(data, list) else []
    except Exception as e:
        print(f"[review_miner] Apify fetch failed: {str(e)[:200]}")
        return []


def _clean_review_text(text: str) -> str:
    """Strip and trim review text into a 1-2 sentence testimonial."""
    if not text:
        return ""
    text = text.strip().replace("\n", " ").replace("\r", " ")
    # Take first 2 sentences or first 280 chars
    sentences = []
    for delim in [". ", "! ", "? "]:
        if delim in text:
            parts = text.split(delim)
            sentences.append((parts[0] + delim.strip()).strip())
            if len(parts) > 1:
                sentences.append((parts[1] + delim.strip()).strip())
            break
    quote = " ".join(sentences) if sentences else text
    if len(quote) > 280:
        quote = quote[:277].rsplit(" ", 1)[0] + "..."
    return quote


def _shape_review(raw: dict) -> dict | None:
    """Convert raw Apify review into our normalized format."""
    text = raw.get("text") or raw.get("reviewText") or ""
    name = raw.get("name") or raw.get("reviewerName") or "DWT Traveller"
    rating = raw.get("stars") or raw.get("rating") or 0
    if not text or not rating:
        return None
    if rating < 4:  # Skip below 4-star
        return None
    return {
        "quote": _clean_review_text(text),
        "author": name.strip(),
        "rating": int(rating),
        "raw_text": text,
        "review_id": raw.get("reviewId") or raw.get("reviewerId"),
        "published_at": raw.get("publishedAtDate") or raw.get("publishedAt"),
    }


# ── Keyword matching for package-relevant quotes ──────────────────────────────

PACKAGE_KEYWORDS = {
    "vietnam":   ["vietnam", "hanoi", "halong", "ha long", "ho chi minh", "saigon", "ninh binh", "mekong"],
    "kashmir":   ["kashmir", "srinagar", "dal lake", "gulmarg", "pahalgam", "shikara", "houseboat", "tulip"],
    "leh-ladakh":["ladakh", "leh", "pangong", "nubra", "zoji"],
    "thailand":  ["thailand", "bangkok", "pattaya", "phuket", "krabi", "phi phi"],
    "dubai":     ["dubai", "abu dhabi", "burj", "desert safari"],
    "bhutan":    ["bhutan", "paro", "thimphu", "tiger's nest", "punakha"],
    "singapore": ["singapore", "marina bay", "universal studios", "gardens by the bay"],
    "malaysia":  ["malaysia", "kuala lumpur", "kl", "genting", "batu caves"],
    "kerala":    ["kerala", "alleppey", "munnar", "kovalam", "backwater"],
    "bali":      ["bali", "ubud", "seminyak", "nusa penida"],
    "northeast": ["arunachal", "meghalaya", "assam", "tawang", "kaziranga", "shillong"],
    "sikkim":    ["sikkim", "darjeeling", "gangtok", "tsomgo"],
    "kenya":     ["kenya", "masai mara", "safari"],
    "amarnath":  ["amarnath", "yatra", "cave"],
    "family":    ["family", "kids", "children", "parents", "daughter", "son", "wife", "husband", "mother", "father"],
    "honeymoon": ["honeymoon", "couple", "anniversary", "romantic"],
    "religious": ["yatra", "amarnath", "char dham", "darshan", "pilgrimage", "temple"],
}


def _match_keywords(review_text: str, keywords: list) -> bool:
    t = review_text.lower()
    return any(kw in t for kw in keywords)


# ── Public API ────────────────────────────────────────────────────────────────

def _extract_reviews_from_apify_response(raw: list) -> list:
    """Apify's compass/google-maps-reviews-scraper can return either:
    1. Flat list of review objects (when using startUrls with direct place URL)
    2. List of place objects, each with a 'reviews' nested array (when using searchStringsArray)
    Detect and normalize.
    """
    if not raw:
        return []
    first = raw[0] if isinstance(raw[0], dict) else {}
    # If items look like reviews (have text + stars), use directly
    if "text" in first or "reviewText" in first or "stars" in first:
        return raw
    # Otherwise, items are places — pull reviews from each
    flattened = []
    for place in raw:
        if isinstance(place, dict):
            place_reviews = place.get("reviews") or place.get("reviewsResult") or []
            if isinstance(place_reviews, list):
                flattened.extend(place_reviews)
    return flattened


async def fetch_all_reviews(force_refresh: bool = False) -> list:
    """Get all DWT reviews. Cached for 7 days."""
    if not force_refresh:
        cached = _read_cache()
        if cached:
            return cached.get("reviews", [])

    raw = await _fetch_reviews_from_apify(limit=300)
    print(f"[review_miner] Raw items: {len(raw)}")
    review_items = _extract_reviews_from_apify_response(raw)
    print(f"[review_miner] Extracted review items: {len(review_items)}")
    cleaned = [_shape_review(r) for r in review_items]
    reviews = [r for r in cleaned if r]
    print(f"[review_miner] After shaping + 4★ filter: {len(reviews)}")
    _write_cache({
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "count": len(reviews),
        "reviews": reviews,
    })
    return reviews


async def get_quotes_for(topic: str, count: int = 3, min_rating: int = 5) -> list:
    """Return `count` testimonial-ready quotes matching the given topic keyword.
    Topic can be a destination ('vietnam'), audience ('family'), or arbitrary keyword.
    """
    all_reviews = await fetch_all_reviews()
    if not all_reviews:
        return []

    topic_key = topic.lower().strip()
    keywords = PACKAGE_KEYWORDS.get(topic_key, [topic_key])

    matches = []
    fallback = []
    for r in all_reviews:
        if r["rating"] < min_rating:
            continue
        if _match_keywords(r["raw_text"], keywords):
            matches.append(r)
        else:
            fallback.append(r)

    # Prefer matches; if not enough, top up with high-rated general reviews
    result = matches[:count]
    if len(result) < count:
        result.extend(fallback[:count - len(result)])
    return [{"quote": r["quote"], "author": r["author"], "rating": r["rating"]} for r in result[:count]]


async def get_general_top_quotes(count: int = 3) -> list:
    """Return the top general-purpose 5-star quotes (for non-themed pages)."""
    return await get_quotes_for("dwt", count=count, min_rating=5)
