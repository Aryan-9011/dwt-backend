"""
GMB Review Auto-Reply — draft + post replies to Google Business Profile reviews.

Three public functions:
  fetch_pending_reviews(token) → list of reviews without an owner reply
  draft_reply(review_text, stars, customer_name) → Claude-drafted reply tuned for DWT voice
  post_reply(review_name, reply_text) → POST to GBP API

Designed for the draft → human approve → post flow (NOT fully autonomous).
"""
import os

import requests

from services.gmb_audit import (
    GMB_V4,
    _full_location_path,
    fetch_reviews,
    get_access_token,
)
from services.llm_chat import gemini_chat

STAR_MAP = {"FIVE": 5, "FOUR": 4, "THREE": 3, "TWO": 2, "ONE": 1}


def fetch_pending_reviews(token: str, limit: int = 50) -> list[dict]:
    """All reviews from GBP, sorted newest first, with a needs_reply flag."""
    raw = fetch_reviews(token)
    out = []
    for r in raw[:limit]:
        out.append({
            "review_name": r.get("name"),  # full resource for replying: accounts/X/locations/Y/reviews/Z
            "review_id": (r.get("name") or "").split("/")[-1],
            "reviewer_name": (r.get("reviewer") or {}).get("displayName") or "Anonymous",
            "reviewer_photo": (r.get("reviewer") or {}).get("profilePhotoUrl"),
            "stars": STAR_MAP.get(r.get("starRating", ""), 0),
            "comment": r.get("comment", ""),
            "created_at": r.get("createTime"),
            "owner_reply": (r.get("reviewReply") or {}).get("comment"),
            "owner_reply_at": (r.get("reviewReply") or {}).get("updateTime"),
            "needs_reply": not (r.get("reviewReply") or {}).get("comment"),
        })
    return out


def _draft_system_prompt() -> str:
    return """You write owner replies to Google reviews for Dream World Tours (DWT) — a premium group tour operator from Pune, India.

About DWT (for context, don't recite these stats verbatim):
- 25,000+ travellers over 10 years, 700+ Google reviews at 4.9★
- Pune-based with dedicated Pune tour managers on every trip
- Destinations: Vietnam, Dubai, Bali, Thailand, Bhutan, Kashmir, Kerala, religious tours (Char Dham, Ashtavinayak)
- WhatsApp +91 93226 08068, dreamworldtours.in

Voice rules — read carefully:
1. SHORT. 2-3 sentences max. 250 chars target, 400 absolute max.
2. PERSONAL. Reference one specific detail from the review (the destination they went to, the tour manager they named, the moment they described). If their review is generic, just thank them by first name.
3. WARM but not gushy. No "We are so blessed to have customers like you 🙏🙏🙏" energy. No emojis unless the reviewer used one first (then match sparingly).
4. NO marketing pitches in 5★ replies. Don't push them to book again. They already love you. Just thank.
5. For 1-3★ (negative) reviews: acknowledge the specific problem in their own words, apologize directly, give them a real contact (WhatsApp +91 93226 08068) to make it right. Never argue, never deflect.
6. NEVER make up details. If you don't know the manager's name or the trip date, don't invent one.
7. Sign off naturally — "— Aryan, DWT team" or just "— DWT team" — no formal "Yours sincerely" garbage.
8. Match the reviewer's language. If they wrote in Hindi/Marathi script, reply in the same. If they wrote in romanized Hindi/Marathi, match.

Output: ONLY the reply text. No preamble, no explanation, no quotes around it."""


def draft_reply(comment: str, stars: int, reviewer_name: str) -> str:
    """Generate a single reply draft via Gemini."""
    if not comment or not comment.strip():
        # No review text — generic short thank-you (no LLM needed)
        if stars >= 4:
            first_name = (reviewer_name or "").split()[0] or "there"
            return f"Thank you so much, {first_name}! Means a lot. — DWT team"
        return "Thank you for the feedback. If there's anything we can do to make this right, please WhatsApp us on +91 93226 08068. — DWT team"

    user_msg = f"""Reviewer: {reviewer_name or 'Anonymous'}
Stars: {stars}★
Review text:
\"\"\"
{comment.strip()[:1200]}
\"\"\"

Write the reply. Output ONLY the reply text — no preamble, no quotes around it."""

    reply = gemini_chat(
        system=_draft_system_prompt(),
        user=user_msg,
        max_tokens=800,        # plenty of headroom even for longer Marathi/Hindi replies
        temperature=0.7,
        thinking_budget=0,     # explicit: short replies don't need thinking
    )
    return reply.strip().strip('"').strip()


def draft_replies_bulk(reviews: list[dict]) -> list[dict]:
    """Add a 'draft_reply' field to each review needing one."""
    out = []
    for r in reviews:
        item = dict(r)
        if r.get("needs_reply"):
            try:
                item["draft_reply"] = draft_reply(
                    r.get("comment", ""),
                    r.get("stars", 0),
                    r.get("reviewer_name", ""),
                )
                item["draft_status"] = "ready"
            except Exception as e:
                item["draft_reply"] = ""
                item["draft_status"] = f"error: {str(e)[:500]}"
        else:
            item["draft_reply"] = r.get("owner_reply", "")
            item["draft_status"] = "already_replied"
        out.append(item)
    return out


def post_reply(token: str, review_name: str, reply_text: str) -> dict:
    """PUT to GBP /reviews/{id}/reply with the approved reply text."""
    if not review_name:
        raise ValueError("review_name (full GBP resource name) required")
    if not reply_text or not reply_text.strip():
        raise ValueError("reply_text required")

    # GBP API needs full path like accounts/X/locations/Y/reviews/Z
    # If review_name starts with 'locations/' or just 'reviews/', prepend the location path
    if review_name.startswith("accounts/"):
        full = review_name
    else:
        full = f"{_full_location_path()}/reviews/{review_name.split('/')[-1]}"

    url = f"{GMB_V4}/{full}/reply"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    body = {"comment": reply_text.strip()[:4000]}

    r = requests.put(url, json=body, headers=headers, timeout=30)
    if r.status_code >= 400:
        raise RuntimeError(f"GBP reply API {r.status_code}: {r.text[:400]}")
    return r.json()
