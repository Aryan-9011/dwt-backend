"""Marketing Posts API — single-image marketing posts for Dream World Tours.

Endpoints:
- GET  /api/marketing-posts/inspirations             → list available inspirations
- POST /api/marketing-posts/generate                 → generate a post (single, user picks inspiration)
- POST /api/marketing-posts/smart-generate           → AI agent picks inspirations + writes details
- GET  /api/marketing-posts/history                  → past generations from Postgres
- GET  /api/marketing-posts/image/{filename}         → serve local fallback image
"""
import asyncio
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Body
from fastapi.responses import FileResponse

from services import db
from services.marketing_post_generator import (
    generate_post,
    get_inspirations,
    OUTPUT_DIR,
)
from services.smart_orchestrator import smart_generate

router = APIRouter()


@router.get("/marketing-posts/inspirations")
async def list_inspirations():
    """Return the list of marketing post inspirations with previews."""
    return {"inspirations": get_inspirations()}


@router.post("/marketing-posts/generate")
async def generate_marketing_post(payload: dict = Body(...)):
    """
    Generate a marketing post. Body:
      destination: required string (e.g., "Bhutan")
      inspiration_id: required string (one of the inspiration ids)
      details: optional dict — title_line_1, price_line, departures, highlights, photo_direction, etc.
    """
    destination = (payload.get("destination") or "").strip()
    inspiration_id = (payload.get("inspiration_id") or "").strip()
    details = payload.get("details") or {}
    model_provider = (payload.get("model_provider") or "gemini").strip().lower()

    if not destination:
        raise HTTPException(400, "destination is required")
    if not inspiration_id:
        raise HTTPException(400, "inspiration_id is required")
    if not isinstance(details, dict):
        raise HTTPException(400, "details must be an object")
    if model_provider not in ("gemini", "openai"):
        raise HTTPException(400, "model_provider must be 'gemini' or 'openai'")

    try:
        # Generation is sync-blocking; offload to thread to avoid blocking event loop
        result = await asyncio.to_thread(generate_post, destination, inspiration_id, details, model_provider)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Generation failed: {str(e)[:300]}")

    # Persist to Postgres history
    try:
        db.save_run(
            run_id=result["run_id"],
            workflow="marketing_post",
            status="complete",
            topic=f"{destination} · {result['inspiration_name']}",
            result=result,
        )
    except Exception as e:
        print(f"[marketing_post] DB save failed: {str(e)[:120]}")

    return result


@router.post("/marketing-posts/smart-generate")
async def smart_generate_endpoint(payload: dict = Body(...)):
    """
    Smart Batch: free-text request → Claude picks inspirations + writes details → generates N posts.

    Body:
      request: required string, e.g. "make 3 Kashmir posts for May families"
      count: optional int (1-5, default 3)
      model_provider: optional, "gemini" (default) or "openai"
    """
    request = (payload.get("request") or "").strip()
    count = int(payload.get("count", 3))
    model_provider = (payload.get("model_provider") or "gemini").strip().lower()

    if not request:
        raise HTTPException(400, "request is required")
    if count < 1 or count > 5:
        raise HTTPException(400, "count must be between 1 and 5")
    if model_provider not in ("gemini", "openai"):
        raise HTTPException(400, "model_provider must be 'gemini' or 'openai'")

    try:
        # Planner + image generation is sync-blocking — offload from event loop
        result = await asyncio.to_thread(smart_generate, request, count, model_provider)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Smart generate failed: {str(e)[:300]}")

    # Persist each generated post to Postgres history
    for post in result.get("posts", []):
        try:
            db.save_run(
                run_id=post["run_id"],
                workflow="marketing_post",
                status="complete",
                topic=f"{post['destination']} · {post['inspiration_name']} · smart",
                result=post,
            )
        except Exception as e:
            print(f"[smart_generate] DB save failed for {post.get('run_id')}: {str(e)[:120]}")

    return result


@router.get("/marketing-posts/history")
async def history(limit: int = 30):
    """Return past marketing post generations from Postgres."""
    runs = db.get_runs(workflow="marketing_post", limit=limit)
    posts = []
    for r in runs:
        result = r.get("result") or {}
        if not isinstance(result, dict):
            continue
        posts.append({
            "run_id": r.get("id"),
            "destination": result.get("destination") or r.get("topic"),
            "inspiration_id": result.get("inspiration_id"),
            "inspiration_name": result.get("inspiration_name"),
            "image_url": result.get("image_url"),
            "permanent_url": result.get("permanent_url"),
            "filename": result.get("filename"),
            "created_at": r.get("created_at"),
        })
    return {"posts": posts, "count": len(posts)}


@router.get("/marketing-posts/image/{filename}")
async def serve_image(filename: str):
    """Serve a locally-saved marketing post image (fallback when imgbb URL missing)."""
    safe = "".join(c for c in filename if c.isalnum() or c in "-_.")
    if not safe.endswith(".png"):
        raise HTTPException(400, "Invalid filename")
    p = OUTPUT_DIR / safe
    if not p.exists():
        raise HTTPException(404, "Image not found")
    return FileResponse(str(p), media_type="image/png")
