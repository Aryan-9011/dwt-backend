"""Skills API — exposes Claude skills/agents to the Agent Hub via Gemini.

Endpoints:
- GET  /api/skills/list         → list all skills + agents discoverable in .claude/
- POST /api/skills/run          → execute one skill with user args
"""
import asyncio

from fastapi import APIRouter, Body, HTTPException

from services.skill_runner import list_skills, run_skill

router = APIRouter()


@router.get("/skills/list")
async def list_endpoint():
    """Catalog every skill + agent the hub knows how to run."""
    try:
        return list_skills()
    except Exception as e:
        raise HTTPException(500, f"Skill discovery failed: {str(e)[:300]}")


@router.post("/skills/run")
async def run_endpoint(payload: dict = Body(...)):
    """
    Execute a skill or agent.

    Body:
      name: required, skill or agent id (e.g. 'carousel-copy', 'marketing-post-ideator')
      args: optional free-text input
      expect_json: optional bool (default False)
      smart: optional bool (default True — uses Gemini Pro)
    """
    name = (payload.get("name") or "").strip()
    args = (payload.get("args") or "").strip()
    expect_json = bool(payload.get("expect_json", False))
    smart = bool(payload.get("smart", True))

    if not name:
        raise HTTPException(400, "name is required")
    # Loose validation — skill names are kebab-case
    if not all(c.isalnum() or c in "-_" for c in name):
        raise HTTPException(400, "name must be alphanumeric/kebab-case")

    try:
        # Skill runs are sync-blocking (Gemini call) — offload from event loop
        result = await asyncio.to_thread(
            run_skill, name, args, expect_json, 6000, smart
        )
    except ValueError as e:
        raise HTTPException(404, str(e))
    except RuntimeError as e:
        raise HTTPException(502, f"Skill execution failed: {str(e)[:400]}")
    except Exception as e:
        raise HTTPException(500, f"Unexpected: {str(e)[:300]}")

    return result
