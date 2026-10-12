"""
GMB Audit — comprehensive scorecard for Dream World Tours' Google Business Profile.

Pulls live data from Google Business Profile API (existing OAuth refresh token + scope)
and computes a 0-100 score across 5 dimensions with prioritized fix recommendations.

Dimensions + max points:
  Profile completeness  40  (categories, description, hours, services, attributes, URL, phone)
  Visual assets         15  (photo count, recency, logo+cover presence)
  Post cadence          15  (posts in last 7/30 days)
  Review engagement     20  (rating, reply rate, response gap, review velocity)
  Q&A coverage          10  (answered questions)
"""
import os
from datetime import datetime, timedelta, timezone

import requests

CLIENT_ID = os.environ.get("GBP_CLIENT_ID")
CLIENT_SECRET = os.environ.get("GBP_CLIENT_SECRET")
REFRESH_TOKEN = os.environ.get("GBP_REFRESH_TOKEN")
ACCOUNT_ID = os.environ.get("GBP_ACCOUNT_ID")
LOCATION_ID = os.environ.get("GBP_LOCATION_ID")

OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
GMB_V4 = "https://mybusiness.googleapis.com/v4"
GBP_BI = "https://mybusinessbusinessinformation.googleapis.com/v1"


def _full_location_path() -> str:
    """Normalize LOCATION_ID to full 'accounts/X/locations/Y' resource path."""
    if not LOCATION_ID:
        raise RuntimeError("GBP_LOCATION_ID not set")
    if LOCATION_ID.startswith("accounts/"):
        return LOCATION_ID
    if not ACCOUNT_ID:
        raise RuntimeError("GBP_ACCOUNT_ID required when LOCATION_ID is not full path")
    return f"{ACCOUNT_ID}/{LOCATION_ID}"


def _location_only() -> str:
    """Just 'locations/Y' — for the Business Information v1 API."""
    full = _full_location_path()
    parts = full.split("/")
    if len(parts) >= 4 and parts[2] == "locations":
        return f"locations/{parts[3]}"
    if full.startswith("locations/"):
        return full
    raise RuntimeError(f"Cannot extract location-only path from {full}")


def get_access_token() -> str:
    if not all([CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN]):
        raise RuntimeError("GBP OAuth credentials not configured (CLIENT_ID/SECRET/REFRESH_TOKEN)")
    resp = requests.post(OAUTH_TOKEN_URL, data={
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": REFRESH_TOKEN,
        "grant_type": "refresh_token",
    }, timeout=30)
    data = resp.json()
    if "access_token" not in data:
        raise RuntimeError(f"GBP token refresh failed: {data.get('error_description', data)}")
    return data["access_token"]


def _get(url: str, token: str, params: dict | None = None) -> dict:
    r = requests.get(url, headers={"Authorization": f"Bearer {token}"}, params=params or {}, timeout=30)
    if r.status_code >= 400:
        raise RuntimeError(f"GBP API {r.status_code}: {r.text[:600]}")
    return r.json()


# ─── Fetchers ──────────────────────────────────────────────────────────────────

def fetch_location_info(token: str) -> dict:
    """Pull profile metadata via Business Information v1 (categories, hours, etc.).
    Note: 'attributes' is a separate sub-resource — fetched in fetch_attributes()."""
    loc = _location_only()
    fields = ("name,title,phoneNumbers,categories,websiteUri,regularHours,"
              "profile,storefrontAddress,openInfo,serviceItems,metadata")
    info = _get(f"{GBP_BI}/{loc}?readMask={fields}", token)
    # Attach attributes separately (they live at /attributes sub-resource)
    try:
        attrs = _get(f"{GBP_BI}/{loc}/attributes", token)
        info["attributes"] = attrs.get("attributes", [])
    except Exception:
        info["attributes"] = []
    return info


def fetch_reviews(token: str) -> list:
    full = _full_location_path()
    out: list = []
    page_token = None
    for _ in range(5):  # safety cap, ~250 reviews
        params = {"pageSize": 50}
        if page_token:
            params["pageToken"] = page_token
        data = _get(f"{GMB_V4}/{full}/reviews", token, params)
        out.extend(data.get("reviews", []))
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return out


def fetch_posts(token: str) -> list:
    full = _full_location_path()
    data = _get(f"{GMB_V4}/{full}/localPosts", token, {"pageSize": 100})
    return data.get("localPosts", [])


def fetch_media(token: str) -> list:
    full = _full_location_path()
    data = _get(f"{GMB_V4}/{full}/media", token, {"pageSize": 100})
    return data.get("mediaItems", [])


def fetch_questions(token: str) -> list:
    """GBP Q&A — uses v4 'questions' endpoint."""
    full = _full_location_path()
    try:
        data = _get(f"{GMB_V4}/{full}/questions", token, {"pageSize": 50})
        return data.get("questions", [])
    except Exception:
        return []  # endpoint may 404 if Q&A not enabled


# ─── Scoring ───────────────────────────────────────────────────────────────────

def _score_profile(info: dict) -> tuple[int, list]:
    """0-40 pts. Returns (score, issues)."""
    score, issues = 0, []

    # Categories: primary (8) + at least 2 additional (4)
    cats = info.get("categories", {})
    primary = cats.get("primaryCategory")
    additional = cats.get("additionalCategories", [])
    if primary:
        score += 8
    else:
        issues.append({"severity": "high", "area": "Categories", "fix": "Set a primary category"})
    if len(additional) >= 2:
        score += 4
    else:
        issues.append({"severity": "med", "area": "Categories",
                       "fix": f"Add additional categories (have {len(additional)}, target 3+)"})

    # Description (8 pts: 4 if exists, +4 if ≥500 chars)
    desc = (info.get("profile") or {}).get("description", "") or ""
    if desc:
        score += 4
        if len(desc) >= 500:
            score += 4
        else:
            issues.append({"severity": "med", "area": "Description",
                           "fix": f"Expand business description ({len(desc)}/750 chars). Include destinations + USP."})
    else:
        issues.append({"severity": "high", "area": "Description", "fix": "Write a 500-750 char business description"})

    # Hours (5 pts)
    hours = info.get("regularHours", {}).get("periods", [])
    if hours:
        score += 5
    else:
        issues.append({"severity": "high", "area": "Hours", "fix": "Add regular business hours"})

    # Website + phone (3 pts each)
    if info.get("websiteUri"):
        score += 3
    else:
        issues.append({"severity": "high", "area": "Website", "fix": "Add dreamworldtours.in to profile"})
    if info.get("phoneNumbers", {}).get("primaryPhone"):
        score += 3
    else:
        issues.append({"severity": "high", "area": "Phone", "fix": "Add primary phone number"})

    # Services / serviceItems (5 pts)
    services = info.get("serviceItems", [])
    if len(services) >= 5:
        score += 5
    elif services:
        score += 2
        issues.append({"severity": "med", "area": "Services",
                       "fix": f"List more services ({len(services)} now, add Kashmir/Vietnam/Dubai/Bhutan etc.)"})
    else:
        issues.append({"severity": "high", "area": "Services",
                       "fix": "Add service items for each destination you run"})

    # Attributes (4 pts) — payment, accessibility, amenities
    attrs = info.get("attributes", [])
    if len(attrs) >= 5:
        score += 4
    elif attrs:
        score += 2
        issues.append({"severity": "low", "area": "Attributes",
                       "fix": f"Add more attributes ({len(attrs)} now) — payments accepted, accessibility, etc."})
    else:
        issues.append({"severity": "med", "area": "Attributes", "fix": "Set business attributes"})

    return score, issues


def _score_visual(media: list) -> tuple[int, list]:
    """0-15 pts."""
    score, issues = 0, []
    if not media:
        issues.append({"severity": "high", "area": "Photos", "fix": "Upload at least 20 high-quality photos"})
        return 0, issues

    total = len(media)
    if total >= 50:
        score += 6
    elif total >= 20:
        score += 4
    elif total >= 10:
        score += 2
        issues.append({"severity": "med", "area": "Photos", "fix": f"Add more photos ({total} now, target 50+)"})
    else:
        issues.append({"severity": "high", "area": "Photos", "fix": f"Only {total} photos — target 50+"})

    # Recency: any photo in last 30 days?
    now = datetime.now(timezone.utc)
    recent = 0
    for m in media:
        ct = m.get("createTime")
        if not ct:
            continue
        try:
            dt = datetime.fromisoformat(ct.replace("Z", "+00:00"))
            if (now - dt).days <= 30:
                recent += 1
        except Exception:
            pass
    if recent >= 5:
        score += 5
    elif recent >= 1:
        score += 3
    else:
        issues.append({"severity": "med", "area": "Photos",
                       "fix": "No photos in last 30 days — upload at least 5/month"})

    # Has logo + cover (4 pts)
    has_logo = any(m.get("locationAssociation", {}).get("category") == "LOGO" for m in media)
    has_cover = any(m.get("locationAssociation", {}).get("category") == "COVER" for m in media)
    if has_logo:
        score += 2
    else:
        issues.append({"severity": "med", "area": "Photos", "fix": "Upload logo image"})
    if has_cover:
        score += 2
    else:
        issues.append({"severity": "med", "area": "Photos", "fix": "Upload cover photo"})

    return score, issues


def _score_posts(posts: list) -> tuple[int, list]:
    """0-15 pts. Reward 2-3 posts/week."""
    score, issues = 0, []
    now = datetime.now(timezone.utc)

    def _count_within(days: int) -> int:
        n = 0
        for p in posts:
            ct = p.get("createTime")
            if not ct:
                continue
            try:
                dt = datetime.fromisoformat(ct.replace("Z", "+00:00"))
                if (now - dt).days <= days:
                    n += 1
            except Exception:
                pass
        return n

    last7 = _count_within(7)
    last30 = _count_within(30)

    if last7 >= 2:
        score += 8
    elif last7 >= 1:
        score += 5
        issues.append({"severity": "med", "area": "Posts",
                       "fix": f"Only {last7} post in last 7 days. Target 2-3/week."})
    else:
        issues.append({"severity": "high", "area": "Posts",
                       "fix": "No posts in last 7 days — gmb-autopilot should be running Mon/Wed/Fri"})

    if last30 >= 8:
        score += 7
    elif last30 >= 4:
        score += 4
        issues.append({"severity": "med", "area": "Posts",
                       "fix": f"Only {last30} posts in last 30 days. Target 10-12/month."})
    else:
        issues.append({"severity": "high", "area": "Posts",
                       "fix": f"Only {last30} posts in last 30 days. Check gmb-autopilot cron is firing."})

    return score, issues


def _score_reviews(reviews: list) -> tuple[int, list]:
    """0-20 pts. Reply rate + rating + velocity."""
    score, issues = 0, []
    total = len(reviews)
    if total == 0:
        issues.append({"severity": "high", "area": "Reviews", "fix": "No reviews returned — verify GBP access"})
        return 0, issues

    # Average rating (max 5 pts)
    star_map = {"FIVE": 5, "FOUR": 4, "THREE": 3, "TWO": 2, "ONE": 1}
    rating_sum = sum(star_map.get(r.get("starRating", ""), 0) for r in reviews)
    avg = rating_sum / total if total else 0
    if avg >= 4.8:
        score += 5
    elif avg >= 4.5:
        score += 4
        issues.append({"severity": "low", "area": "Reviews",
                       "fix": f"Avg {avg:.2f}★ — request more 5★ reviews to push above 4.8"})
    elif avg >= 4.0:
        score += 2
        issues.append({"severity": "med", "area": "Reviews",
                       "fix": f"Avg {avg:.2f}★ — focus on service quality + ask 5★ customers to review"})
    else:
        issues.append({"severity": "high", "area": "Reviews", "fix": f"Avg {avg:.2f}★ — quality issue, investigate"})

    # Reply rate (max 10 pts)
    replied = sum(1 for r in reviews if r.get("reviewReply", {}).get("comment"))
    reply_rate = replied / total if total else 0
    if reply_rate >= 0.9:
        score += 10
    elif reply_rate >= 0.7:
        score += 7
        issues.append({"severity": "med", "area": "Reviews",
                       "fix": f"Reply rate {reply_rate:.0%} — aim for 90%+. Use auto-reply tool."})
    elif reply_rate >= 0.5:
        score += 4
        issues.append({"severity": "high", "area": "Reviews",
                       "fix": f"Reply rate only {reply_rate:.0%}. Reply to every review."})
    else:
        issues.append({"severity": "high", "area": "Reviews",
                       "fix": f"Reply rate {reply_rate:.0%} — major gap. Reply to all reviews."})

    # Velocity: reviews in last 30 days (max 5 pts)
    now = datetime.now(timezone.utc)
    recent = 0
    for r in reviews:
        ct = r.get("createTime")
        if not ct:
            continue
        try:
            dt = datetime.fromisoformat(ct.replace("Z", "+00:00"))
            if (now - dt).days <= 30:
                recent += 1
        except Exception:
            pass
    if recent >= 10:
        score += 5
    elif recent >= 5:
        score += 3
        issues.append({"severity": "low", "area": "Reviews",
                       "fix": f"{recent} new reviews in 30 days. Push for 10+/month via post-tour follow-up."})
    elif recent >= 1:
        score += 1
        issues.append({"severity": "med", "area": "Reviews",
                       "fix": f"Only {recent} new reviews in 30 days. Set up post-tour review request."})
    else:
        issues.append({"severity": "high", "area": "Reviews",
                       "fix": "No new reviews in 30 days — review-request flow is broken"})

    return score, issues


def _score_qa(questions: list) -> tuple[int, list]:
    """0-10 pts. Q&A coverage."""
    score, issues = 0, []
    total = len(questions)
    if total == 0:
        issues.append({"severity": "low", "area": "Q&A",
                       "fix": "No Q&A activity. Seed 5-10 owner-asked FAQs (price range, group size, refund policy)"})
        return 0, issues

    answered = sum(1 for q in questions if q.get("topAnswers"))
    rate = answered / total if total else 0
    if rate >= 0.9:
        score += 10
    elif rate >= 0.7:
        score += 7
        issues.append({"severity": "med", "area": "Q&A",
                       "fix": f"{answered}/{total} questions answered. Answer the rest."})
    elif rate >= 0.5:
        score += 4
        issues.append({"severity": "high", "area": "Q&A",
                       "fix": f"Only {answered}/{total} questions answered. Catch up."})
    else:
        issues.append({"severity": "high", "area": "Q&A",
                       "fix": f"Only {answered}/{total} questions answered."})

    return score, issues


# ─── Public entry point ────────────────────────────────────────────────────────

def run_audit() -> dict:
    """Full audit. Returns dict with score, breakdown, issues, raw counts."""
    token = get_access_token()

    info = fetch_location_info(token)
    reviews = fetch_reviews(token)
    posts = fetch_posts(token)
    media = fetch_media(token)
    questions = fetch_questions(token)

    profile_score, profile_issues = _score_profile(info)
    visual_score, visual_issues = _score_visual(media)
    posts_score, posts_issues = _score_posts(posts)
    reviews_score, reviews_issues = _score_reviews(reviews)
    qa_score, qa_issues = _score_qa(questions)

    total_score = profile_score + visual_score + posts_score + reviews_score + qa_score
    all_issues = profile_issues + visual_issues + posts_issues + reviews_issues + qa_issues

    # Sort issues by severity (high → med → low), keep top 8
    sev_order = {"high": 0, "med": 1, "low": 2}
    all_issues.sort(key=lambda x: sev_order.get(x["severity"], 9))
    top_issues = all_issues[:8]

    grade = (
        "A+" if total_score >= 90 else
        "A" if total_score >= 80 else
        "B" if total_score >= 70 else
        "C" if total_score >= 60 else
        "D" if total_score >= 50 else "F"
    )

    return {
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "score": total_score,
        "max_score": 100,
        "grade": grade,
        "breakdown": {
            "profile_completeness": {"score": profile_score, "max": 40},
            "visual_assets":        {"score": visual_score,  "max": 15},
            "post_cadence":         {"score": posts_score,   "max": 15},
            "review_engagement":    {"score": reviews_score, "max": 20},
            "qa_coverage":          {"score": qa_score,      "max": 10},
        },
        "issues": top_issues,
        "totals": {
            "reviews": len(reviews),
            "posts": len(posts),
            "photos": len(media),
            "questions": len(questions),
            "categories": len((info.get("categories", {}) or {}).get("additionalCategories", [])) + (1 if (info.get("categories", {}) or {}).get("primaryCategory") else 0),
            "services": len(info.get("serviceItems", []) or []),
            "attributes": len(info.get("attributes", []) or []),
        },
        "profile_snapshot": {
            "title": info.get("title"),
            "website": info.get("websiteUri"),
            "phone": (info.get("phoneNumbers") or {}).get("primaryPhone"),
            "primary_category": ((info.get("categories", {}) or {}).get("primaryCategory") or {}).get("displayName"),
            "description_preview": ((info.get("profile") or {}).get("description") or "")[:200],
        },
    }
