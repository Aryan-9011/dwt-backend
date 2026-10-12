"""
Smart Marketing Post Orchestrator — agent layer on top of marketing_post_generator.

Takes a free-text request like "make 3 Kashmir posts for May families" and:
1. Asks Gemini to pick the best inspirations + write tight per-post details
2. Executes each plan by calling generate_post() N times
3. Returns finished posts (each persisted to Postgres by the API layer)

This is what makes the hub an actual agent for marketing posts — an LLM is reasoning about
the request and picking, not the user clicking inspiration cards.
"""
import os

from services.llm_chat import gemini_chat_json
from services.marketing_post_generator import (
    INSPIRATIONS,
    generate_post,
)

# Feature flag: route planning through marketing-post-ideator agent (brand-aware,
# reads brand-reference.md) vs. the hardcoded planner. Default ON.
USE_IDEATOR_AGENT = os.environ.get("USE_IDEATOR_AGENT", "true").lower() == "true"


def _system_prompt() -> str:
    insp_summary = "\n".join(
        f'- "{i["id"]}": {i["name"]} — {i["tagline"]}. Best for: {i["best_for"]}.'
        for i in INSPIRATIONS
    )
    return f"""You are the marketing director for Dream World Tours (DWT) — a premium group tour operator from Pune, India. 25,000+ travellers over 10 years. 700+ Google reviews at 4.9★. Real packages, real Pune-based tour managers. Audience is Indian families and couples from Pune/Mumbai.

The team gives you a free-text request. You return a JSON plan to generate 1–5 marketing post images.

AVAILABLE INSPIRATIONS (image design styles):
{insp_summary}

For each post, you pick:
- inspiration_id: one of the IDs above. Match the style to destination/audience/season.
- destination: clean destination name
- details: dict the image prompt builder uses. Provide all of:
    - title_line_1: 2–4 word evocative headline, all caps (e.g. "KASHMIR IN BLOOM", "VIETNAM UNFOLDS")
    - price_line: real-feel price + duration (e.g. "₹65,000 per person · 6N/7D"). Use ₹ symbol.
    - departures: month + dates if the request implies them (e.g. "May 15 · 22 · 29, 2026")
    - highlights: list of 3–5 specific concrete inclusions (no generic phrases)
    - photo_direction: one sentence describing the cinematic photo — be specific (location, time of day, mood, no people in foreground)
    - highlight_word: ONE word from title_line_1 that should be marker-highlighted (used by yellow-accent styles)
    - eyebrow: small label (e.g. "PREMIUM GROUP TOUR", "LIMITED MAY DEPARTURE")
- rationale: one short line on why you picked this inspiration

Output ONLY a JSON object, no markdown fences, no preamble. Schema:

{{
  "intent_summary": "1-line restatement of what the user wants",
  "posts": [
    {{
      "inspiration_id": "...",
      "destination": "...",
      "details": {{
        "title_line_1": "...",
        "price_line": "...",
        "departures": "...",
        "highlights": ["...", "..."],
        "photo_direction": "...",
        "highlight_word": "...",
        "eyebrow": "..."
      }},
      "rationale": "..."
    }}
  ]
}}

Rules:
- Vary inspirations if generating multiple posts. Don't repeat the same style.
- Never invent prices outside DWT's range (₹35,000–₹150,000 per person typical).
- If the user gives a real price, use it exactly. If not, pick a believable one for that destination.
- title_line_1 must be 2–4 words. NEVER use clichés ("Paradise Awaits", "Discover the Magic").
- photo_direction must include a specific landmark or scene, time of day, and mood.
- highlights must be CONCRETE: "5★ Houseboat in Srinagar" beats "Premium accommodation".
"""


def smart_generate(request: str, count: int = 3, model_provider: str = "gemini") -> dict:
    """
    Plan and generate marketing posts from a free-text request.

    Args:
        request: e.g. "make 3 Kashmir posts for May families"
        count: 1–5 (clamped). How many posts to generate.
        model_provider: "gemini" or "openai" for image generation

    Returns:
        {
          "intent_summary": str,
          "plan": {full plan dict from Claude},
          "posts": [list of finished generate_post results],
          "errors": [list of {destination, inspiration_id, error} for failures]
        }
    """
    count = max(1, min(5, int(count)))

    # Prefer brand-aware planning via marketing-post-ideator agent (auto-loads
    # brand-reference.md). Falls back to the hardcoded planner if it fails.
    plan = None
    plan_source = "hardcoded"
    if USE_IDEATOR_AGENT:
        try:
            from services.skill_runner import run_skill
            insp_ids = [i["id"] for i in INSPIRATIONS]
            ideator_args = f"""USER REQUEST: {request}

Generate exactly {count} marketing post concepts.

OVERRIDE YOUR DEFAULT JSON SCHEMA. Return JSON in EXACTLY this shape (no other keys):

{{
  "intent_summary": "<1-line restatement>",
  "posts": [
    {{
      "inspiration_id": "<one of: {', '.join(insp_ids)}>",
      "destination": "<destination name>",
      "details": {{
        "title_line_1": "<2-4 word evocative all-caps headline>",
        "price_line": "<₹X,XXX per person · NN/ND>",
        "departures": "<dates if relevant, else empty string>",
        "highlights": ["<concrete inclusion>", "<another>", "<another>", "<another>"],
        "photo_direction": "<1-sentence cinematic photo brief, no people in foreground>",
        "highlight_word": "<one word from title to marker-highlight>",
        "eyebrow": "<small label like 'PREMIUM GROUP TOUR'>"
      }},
      "rationale": "<one short line on why this inspiration fits>"
    }}
  ]
}}

Use the brand context from brand-reference.md. Use real DWT prices and real package inclusions where you know them. Vary inspirations across posts. No clichés ("Paradise Awaits", "Discover the Magic")."""
            result = run_skill(
                name="marketing-post-ideator",
                args=ideator_args,
                expect_json=True,
                smart=True,
                max_tokens=6000,
            )
            plan = result.get("output")
            if not isinstance(plan, dict) or "posts" not in plan:
                raise RuntimeError("Ideator returned malformed plan (missing 'posts' key)")
            plan_source = "skill:marketing-post-ideator"
        except Exception as e:
            print(f"[smart_generate] Ideator failed, falling back to hardcoded planner: {str(e)[:200]}")
            plan = None

    if plan is None:
        try:
            plan = gemini_chat_json(
                system=_system_prompt(),
                user=f"Request: {request}\n\nGenerate exactly {count} post(s).",
                max_tokens=4000,
                smart=True,
            )
            plan_source = "hardcoded"
        except RuntimeError as e:
            raise RuntimeError(f"Planner call failed: {str(e)[:300]}")

    posts_plan = plan.get("posts", [])[:count]
    if not posts_plan:
        raise RuntimeError("Planner returned no posts in plan")

    posts: list = []
    errors: list = []

    for post_plan in posts_plan:
        try:
            result = generate_post(
                destination=post_plan.get("destination", ""),
                inspiration_id=post_plan.get("inspiration_id", ""),
                details=post_plan.get("details", {}),
                model_provider=model_provider,
            )
            result["rationale"] = post_plan.get("rationale", "")
            result["planned_details"] = post_plan.get("details", {})
            posts.append(result)
        except Exception as e:
            errors.append({
                "destination": post_plan.get("destination", "?"),
                "inspiration_id": post_plan.get("inspiration_id", "?"),
                "error": str(e)[:300],
            })

    return {
        "intent_summary": plan.get("intent_summary", ""),
        "plan": plan,
        "plan_source": plan_source,
        "posts": posts,
        "errors": errors,
    }
