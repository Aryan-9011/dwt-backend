"""
Research a fresh carousel topic using Claude API.
Returns structured JSON matching article-research format.
"""
import os
import json
import anthropic

client = anthropic.AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

RESEARCH_SYSTEM = """You are a travel content researcher for Dream World Tours (DWT), a Pune-based group tour operator for Indian travelers (25–55 age group, aspirational domestic + international travel).

Your job: pick a fresh, trending travel topic and generate a structured carousel brief for it.

Rules:
- Pick a topic that is highly shareable for Indian travelers right now
- Up to 8 locations/destinations — pick the most visual and interesting
- Every photo direction MUST specify a bright sky or light area at the top (dark text needs contrast)
- Descriptors are factual, punchy, max 55 characters
- Avoid repeating any topic passed in the "avoid" list
- Output ONLY valid JSON — no markdown, no explanation"""

RESEARCH_PROMPT = """Pick a great travel listicle topic for an Instagram carousel for Dream World Tours.

Today: {date}
Avoid these recent topics: {avoid_topics}
Topic hint (optional): {topic_hint}

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


async def research_topic(date: str, avoid_topics: list[str], topic_hint: str = None) -> dict:
    prompt = RESEARCH_PROMPT.format(
        date=date,
        avoid_topics=", ".join(avoid_topics) if avoid_topics else "none",
        topic_hint=topic_hint or "any great topic for Indian travelers",
    )

    response = await client.messages.create(
        model="claude-opus-4-5",
        max_tokens=4096,
        system=RESEARCH_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw)
