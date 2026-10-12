"""
Research a fresh carousel topic.
Uses Claude API when ANTHROPIC_API_KEY is set, falls back to Gemini.
Returns structured JSON matching article-research format.
"""
import os
import json
import asyncio
import anthropic

RESEARCH_SYSTEM = """You are a travel content researcher for Dream World Tours (DWT), a Pune-based group tour operator for Indian travelers (25–55 age group, aspirational domestic + international travel).

Your job: pick a fresh, trending travel topic and generate a structured carousel brief for it.

CRITICAL ANTI-REPETITION RULES (most important):
- You MUST NOT pick a topic that is similar, related, or overlapping with anything in the "avoid" list.
- "Similar" means: same destination, same theme category (spiritual/luxury/budget/honeymoon/hill-stations etc.), same season focus, OR same geographic region.
- If recent topics covered SPIRITUAL/RELIGIOUS themes — pick something secular (food, adventure, beaches, shopping, culture).
- If recent covered HILL STATIONS — pick beaches, deserts, cities, or international.
- If recent covered DOMESTIC INDIA — pick international destinations.
- If recent covered INTERNATIONAL — pick domestic India.
- Be deliberately contrarian to the avoid list. Variety drives engagement.

OTHER RULES:
- Pick a topic that is highly shareable for Indian travelers right now
- Up to 8 locations/destinations — pick the most visual and interesting
- Every photo direction MUST specify a bright sky or light area at the top (dark text needs contrast)
- Descriptors are factual, punchy, max 55 characters
- Output ONLY valid JSON — no markdown, no explanation"""

RESEARCH_PROMPT = """Pick a great travel listicle topic for an Instagram carousel for Dream World Tours.

Today: {date}

═══ AVOID LIST (DO NOT REPEAT OR OVERLAP) ═══
The following topics, themes, destinations, or destination keywords have been covered in recent DWT carousels.
You MUST pick something completely different in theme, region, and angle:

{avoid_topics}

If the avoid list mentions:
- "spiritual" or "religious" or any sacred destinations → pick FOOD, ADVENTURE, BEACHES, NIGHTLIFE, or SHOPPING themes instead
- "hill stations" or specific mountains → pick BEACHES, DESERTS, CITIES, or INTERNATIONAL themes
- "kashmir"/"ladakh"/"himachal" → pick NORTHEAST, SOUTH INDIA, or INTERNATIONAL
- "honeymoon" or "romantic" → pick FAMILY, ADVENTURE, or SOLO travel themes
- Any international destination → pick DOMESTIC INDIA (or vice versa)

Topic hint (optional, only follow if it doesn't conflict with avoid list): {topic_hint}

═══ THEME VARIETY REQUIREMENT ═══
Your chosen topic must fall into a DIFFERENT category than anything in the avoid list.
Categories to rotate through: Beaches · Hills · Cities · Food · Adventure · Wildlife · Cultural · Spiritual · Honeymoon · Family · Budget · Luxury · Off-beat · International · Domestic.

Generate structured data for exactly 8 destinations/locations.

Return this exact JSON:
{{
  "theme": "short theme description",
  "season_label": "e.g. MONSOON EDITION or SUMMER 2026",
  "cover_headline_1": "e.g. 8 HILL STATIONS",
  "cover_headline_2": "e.g. UNDER 5 HOURS",
  "cover_headline_3": "e.g. FROM PUNE",
  "cover_subhead": "e.g. JUNE · JULY · AUGUST 2026",
  "cover_collage_photos": ["5 specific destination photo descriptions for the collage"],
  "items": [
    {{
      "index": 1,
      "name_line_1": "DESTINATION NAME",
      "name_line_2": "",
      "city_state": "City, State",
      "descriptor": "One factual line max 55 chars",
      "photo_direction": "Specific cinematic shot with bright sky at top"
    }}
  ],
  "cta": {{
    "name_line_1": "WHICH ONE",
    "name_line_2": "IS YOUR PICK?",
    "descriptor": "DM us '[KEYWORD]' to plan your escape",
    "photo_direction": "Scenic panorama with bright pale sky at top"
  }}
}}"""


def _clean_json(raw: str) -> dict:
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())


async def _research_via_gemini(prompt: str) -> dict:
    """Gemini-based topic research — primary path."""
    import google.generativeai as genai
    genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
    model = genai.GenerativeModel("gemini-2.5-pro")
    full_prompt = f"{RESEARCH_SYSTEM}\n\n{prompt}\n\nIMPORTANT: Return ONLY valid JSON. No markdown fences, no explanation."
    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(None, lambda: model.generate_content(full_prompt))
    return _clean_json(response.text)


async def research_topic(date: str, avoid_topics: list, topic_hint: str = None, web_research: dict = None) -> dict:
    # Inject live web article inspiration if available
    web_block = ""
    if web_research and web_research.get("available"):
        from services.web_research import trends_to_prompt_block
        web_block = "\n\n" + trends_to_prompt_block(web_research) + "\n"
        web_block += "\nGIVE PREFERENCE to topics derived from the ACTIONABLE articles above when they don't conflict with the avoid list.\n"

    prompt = RESEARCH_PROMPT.format(
        date=date,
        avoid_topics=", ".join(avoid_topics) if avoid_topics else "none",
        topic_hint=topic_hint or "any great topic for Indian travelers",
    ) + web_block

    # Try Claude first ONLY if key is set AND we haven't blacklisted it this session
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            client = anthropic.AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
            response = await client.messages.create(
                model="claude-opus-4-5",
                max_tokens=4096,
                system=RESEARCH_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
            )
            return _clean_json(response.content[0].text)
        except Exception as e:
            err = str(e)
            # Fall back to Gemini on credit/auth/quota errors — don't crash the pipeline
            print(f"[researcher] Claude failed ({err[:120]}) — falling back to Gemini")

    # Gemini path (primary fallback, also used when no Claude key)
    return await _research_via_gemini(prompt)
