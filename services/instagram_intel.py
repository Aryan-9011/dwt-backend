"""
Instagram intelligence service for DWT Agent Hub.
Pulls DWT + competitor data via Apify, computes engagement metrics,
and returns a structured intel dict for the growth strategist.
"""
import os
import asyncio
from datetime import datetime, timezone, timedelta
import httpx

APIFY_TOKEN = os.environ.get("APIFY_TOKEN")

DWT_HANDLE = "dreamworldtours_"
COMPETITORS = ["thrillophilia", "veena_world", "holidayscrowd", "capture.a.trip"]

SCRAPER_ACTOR = "apify~instagram-scraper"
PROFILE_ACTOR = "apify~instagram-profile-scraper"

_BASE = "https://api.apify.com/v2/acts"


async def _fetch_posts(handle: str, limit: int = 20, timeout: int = 75) -> list:
    """Fetch recent posts for a handle. Returns list of post dicts (possibly empty)."""
    if not APIFY_TOKEN:
        return []
    url = f"{_BASE}/{SCRAPER_ACTOR}/run-sync-get-dataset-items?token={APIFY_TOKEN}&timeout={timeout}"
    body = {
        "directUrls": [f"https://www.instagram.com/{handle}/"],
        "resultsType": "posts",
        "resultsLimit": limit,
    }
    try:
        async with httpx.AsyncClient(timeout=timeout + 15) as client:
            r = await client.post(url, json=body)
            r.raise_for_status()
            return r.json() if isinstance(r.json(), list) else []
    except Exception as e:
        print(f"[intel] {handle} posts fetch failed: {str(e)[:120]}")
        return []


async def _fetch_profile(handle: str, timeout: int = 45) -> dict:
    """Fetch profile data (follower count etc) for a handle."""
    if not APIFY_TOKEN:
        return {}
    url = f"{_BASE}/{PROFILE_ACTOR}/run-sync-get-dataset-items?token={APIFY_TOKEN}&timeout={timeout}"
    body = {"usernames": [handle], "resultsLimit": 1}
    try:
        async with httpx.AsyncClient(timeout=timeout + 15) as client:
            r = await client.post(url, json=body)
            r.raise_for_status()
            data = r.json()
            return data[0] if isinstance(data, list) and data else {}
    except Exception as e:
        print(f"[intel] {handle} profile fetch failed: {str(e)[:120]}")
        return {}


def _post_type(p: dict) -> str:
    t = (p.get("type") or "").lower()
    if t in ("video", "reel"): return "Reel"
    if t == "sidecar":         return "Carousel"
    return "Static"


def _is_recent(ts: str, days: int = 7) -> bool:
    if not ts: return False
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - dt) <= timedelta(days=days)
    except Exception:
        return False


def _analyze_dwt(posts: list, followers: int) -> dict:
    """Compute engagement metrics from DWT's recent posts."""
    recent = [p for p in posts if _is_recent(p.get("timestamp"))]
    if not recent:
        return {
            "posts_last_7d": 0, "engagement_rate_pct": 0.0,
            "content_mix": {"Reel": 0, "Carousel": 0, "Static": 0},
            "best_post": None, "worst_post": None, "posting_gaps": [],
        }

    mix = {"Reel": 0, "Carousel": 0, "Static": 0}
    for p in recent:
        mix[_post_type(p)] += 1

    def engagement(p):
        return (p.get("likesCount") or 0) + (p.get("commentsCount") or 0)

    recent_sorted = sorted(recent, key=engagement, reverse=True)
    best  = recent_sorted[0]
    worst = recent_sorted[-1]

    avg_likes    = sum(p.get("likesCount") or 0 for p in recent) / len(recent)
    avg_comments = sum(p.get("commentsCount") or 0 for p in recent) / len(recent)
    er = ((avg_likes + avg_comments) / followers * 100) if followers else 0

    # Posting gaps: which weekday names have no posts
    weekdays_posted = set()
    for p in recent:
        try:
            dt = datetime.fromisoformat(p.get("timestamp","").replace("Z","+00:00"))
            weekdays_posted.add(dt.strftime("%A"))
        except Exception: pass
    all_days = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
    posting_gaps = [d for d in all_days if d not in weekdays_posted]

    def _summarize(p):
        return {
            "type": _post_type(p),
            "likes": p.get("likesCount") or 0,
            "comments": p.get("commentsCount") or 0,
            "views": p.get("videoViewCount") or 0,
            "caption_snippet": (p.get("caption") or "")[:140],
        }

    return {
        "posts_last_7d": len(recent),
        "engagement_rate_pct": round(er, 2),
        "avg_likes": round(avg_likes),
        "avg_comments": round(avg_comments),
        "content_mix": mix,
        "best_post": _summarize(best),
        "worst_post": _summarize(worst),
        "posting_gaps": posting_gaps,
    }


def _analyze_competitor(handle: str, posts: list) -> dict:
    recent = [p for p in posts if _is_recent(p.get("timestamp"))]
    if not recent:
        return {"handle": handle, "posts_last_7d": 0, "best_hook": "", "best_format": "", "best_engagement": 0, "top_format_mix": ""}

    def engagement(p):
        return (p.get("likesCount") or 0) + (p.get("commentsCount") or 0)

    best = max(recent, key=engagement)
    mix = {"Reel": 0, "Carousel": 0, "Static": 0}
    for p in recent: mix[_post_type(p)] += 1
    top_format = max(mix.items(), key=lambda kv: kv[1])[0]

    return {
        "handle": handle,
        "posts_last_7d": len(recent),
        "best_hook": (best.get("caption") or "")[:240],   # bumped from 160
        "best_engagement": engagement(best),
        "best_format": _post_type(best),                  # format of the BEST post specifically
        "top_format_mix": top_format,                     # most-used format overall
    }


async def gather_intel() -> dict:
    """Pull DWT + all competitors in parallel and analyze."""
    if not APIFY_TOKEN:
        return {"available": False, "reason": "APIFY_TOKEN not set"}

    dwt_posts_task    = _fetch_posts(DWT_HANDLE, limit=25)
    dwt_profile_task  = _fetch_profile(DWT_HANDLE)
    comp_tasks        = [_fetch_posts(h, limit=15) for h in COMPETITORS]

    dwt_posts, dwt_profile, *comp_posts = await asyncio.gather(
        dwt_posts_task, dwt_profile_task, *comp_tasks, return_exceptions=False
    )

    followers = dwt_profile.get("followersCount") or dwt_profile.get("followers") or 0
    dwt_metrics  = _analyze_dwt(dwt_posts or [], followers)
    competitors  = [_analyze_competitor(COMPETITORS[i], comp_posts[i] or []) for i in range(len(COMPETITORS))]

    # Engagement gap: DWT best post vs the strongest competitor post
    dwt_best     = dwt_metrics.get("best_post") or {}
    dwt_best_eng = (dwt_best.get("likes") or 0) + (dwt_best.get("comments") or 0)
    comp_best    = max((c.get("best_engagement", 0) for c in competitors), default=0)
    multiplier   = round(comp_best / dwt_best_eng, 1) if dwt_best_eng > 0 else None
    top_comp     = max(competitors, key=lambda c: c.get("best_engagement", 0), default={})

    return {
        "available": True,
        "dwt": {**dwt_metrics, "followers": followers, "handle": DWT_HANDLE},
        "competitors": competitors,
        "engagement_gap": {
            "dwt_best": dwt_best_eng,
            "competitor_best": comp_best,
            "multiplier": multiplier,            # competitor outperforms DWT by this much
            "top_competitor_handle": top_comp.get("handle", ""),
            "top_competitor_format": top_comp.get("best_format", ""),
        },
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def intel_to_prompt_block(intel: dict) -> str:
    """Format the intel dict into a directive prompt block Gemini can use."""
    if not intel or not intel.get("available"):
        return "LIVE INSTAGRAM INTEL: (not available — proceed using DWT package data only)"

    d = intel["dwt"]
    mix = d.get("content_mix", {})
    best = d.get("best_post") or {}
    worst = d.get("worst_post") or {}
    gaps = d.get("posting_gaps") or []
    gap = intel.get("engagement_gap") or {}

    lines = [
        "═══════ LIVE INSTAGRAM INTEL (last 7 days) ═══════",
        f"DWT @{d.get('handle')} | {d.get('followers'):,} followers | {d.get('posts_last_7d')} posts | engagement rate: {d.get('engagement_rate_pct')}%",
        f"  avg likes: {d.get('avg_likes')} | avg comments: {d.get('avg_comments')}",
        f"  content mix this week: {mix.get('Reel',0)} Reels / {mix.get('Carousel',0)} Carousels / {mix.get('Static',0)} Static",
        f"  DWT BEST post ({best.get('type','')}): {best.get('likes',0)} likes, {best.get('comments',0)} comments",
        f"    snippet: \"{best.get('caption_snippet','')[:140]}\"",
        f"  DWT WORST post ({worst.get('type','')}): {worst.get('likes',0)} likes",
    ]

    # POSTING GAPS — make this directive
    if gaps:
        lines.append("")
        lines.append(f"⚠️  POSTING GAPS — DWT did NOT post on these days last week: {', '.join(gaps)}")
        lines.append(f"    → REQUIRED: prioritize your HIGHEST virality_score items on these days to break the silence.")

    # ENGAGEMENT GAP — directly call it out
    if gap.get("multiplier"):
        lines.append("")
        lines.append(f"📉 ENGAGEMENT GAP: top competitor @{gap.get('top_competitor_handle')} got {gap.get('competitor_best'):,} engagement on a {gap.get('top_competitor_format')} — that's {gap.get('multiplier')}× DWT's best post ({gap.get('dwt_best')}).")
        lines.append(f"    → REQUIRED: at least 2 calendar items must use the {gap.get('top_competitor_format')} format with hooks modeled after winning competitor patterns.")

    lines.append("")
    lines.append("COMPETITOR ACTIVITY (last 7 days) — study these winning hooks:")
    for c in intel.get("competitors", []):
        if c.get("posts_last_7d", 0) == 0:
            lines.append(f"  @{c['handle']}: no recent data")
            continue
        lines.append(
            f"  @{c['handle']} — {c['posts_last_7d']} posts | best post: {c['best_format']} with {c['best_engagement']:,} engagement"
        )
        lines.append(f"     winning hook: \"{c['best_hook'][:240]}\"")

    lines.append("")
    lines.append("HOW TO USE THIS INTEL (mandatory):")
    lines.append("1. Place the strongest planned items on the posting-gap days listed above.")
    lines.append("2. Model at least 2 hooks after the WINNING competitor hooks above (same emotional pattern, different DWT destination).")
    lines.append("3. If competitors are crushing Reels, weight DWT toward Reels even if DWT's mix has been carousel-heavy.")
    lines.append("4. Beat DWT's last best-post engagement number — assume your top item needs to outperform it.")
    return "\n".join(lines)
