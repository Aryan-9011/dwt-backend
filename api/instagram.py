"""Instagram posting endpoints — manual button per carousel."""
import os
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException

from services import db
from services.instagram_publisher import post_carousel_async

router = APIRouter()

PUBLISH_LOG = Path(__file__).parent.parent / "outputs" / "automation" / "publish-log.jsonl"
PUBLISH_LOG.parent.mkdir(parents=True, exist_ok=True)


def _append_publish_log(entry: dict):
    try:
        with open(PUBLISH_LOG, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass


@router.get("/instagram/status")
async def status():
    """Whether Instagram posting is configured."""
    return {
        "configured": bool(os.environ.get("INSTAGRAM_ACCESS_TOKEN") and os.environ.get("INSTAGRAM_BUSINESS_ACCOUNT_ID")),
        "ig_account_id": os.environ.get("INSTAGRAM_BUSINESS_ACCOUNT_ID", "")[-4:] if os.environ.get("INSTAGRAM_BUSINESS_ACCOUNT_ID") else None,
    }


@router.post("/instagram/post/{run_id}")
async def post_run_to_instagram(run_id: str):
    """Post the given carousel run to Instagram. Manual trigger — one button per run."""
    # 1. Check configuration
    if not (os.environ.get("INSTAGRAM_ACCESS_TOKEN") and os.environ.get("INSTAGRAM_BUSINESS_ACCOUNT_ID")):
        raise HTTPException(
            status_code=400,
            detail="Instagram posting not configured. Set INSTAGRAM_ACCESS_TOKEN and INSTAGRAM_BUSINESS_ACCOUNT_ID env vars on Railway.",
        )

    # 2. Find the run
    runs = db.get_runs(workflow="carousel", limit=200)
    run = next((r for r in runs if r["id"] == run_id), None)
    if not run:
        raise HTTPException(status_code=404, detail=f"Carousel run {run_id} not found")
    if run.get("status") != "complete":
        raise HTTPException(status_code=400, detail=f"Run is {run.get('status')}, must be complete to post")

    result = run.get("result") or {}
    if not isinstance(result, dict):
        raise HTTPException(status_code=400, detail="Run has no usable result data")

    slides = result.get("slides") or []
    caption = result.get("caption") or f"{run.get('topic', 'Travel inspiration')} ✈️\n\nDream World Tours · 25,000+ travellers · 4.9★ on Google\nWhatsApp us to book your next trip 👇"

    # 3. Filter for publicly-accessible imgbb URLs
    image_urls = []
    for s in slides:
        if not isinstance(s, dict):
            continue
        url = s.get("url", "")
        if url.startswith("http"):
            image_urls.append(url)

    if not image_urls:
        raise HTTPException(
            status_code=400,
            detail="No public image URLs found. Slides need imgbb upload to work for Instagram.",
        )
    if len(image_urls) < 2:
        raise HTTPException(
            status_code=400,
            detail=f"Only {len(image_urls)} public URL(s); Instagram carousel needs at least 2.",
        )

    # 4. Post to Instagram
    started_at = datetime.now(timezone.utc).isoformat()
    publish_result = await post_carousel_async(image_urls, caption)
    finished_at = datetime.now(timezone.utc).isoformat()

    # 5. Persist to DB + log
    new_result = dict(result)
    new_result["instagram"] = {
        "posted_at": finished_at,
        **publish_result,
    }
    try:
        db.save_run(
            run_id=run_id,
            workflow="carousel",
            status="complete",
            topic=run.get("topic"),
            result=new_result,
        )
    except Exception as e:
        print(f"[instagram] DB update failed: {e}")

    _append_publish_log({
        "event": "instagram_post",
        "run_id": run_id,
        "topic": run.get("topic"),
        "started_at": started_at,
        "finished_at": finished_at,
        "image_count": len(image_urls),
        **publish_result,
    })

    if not publish_result.get("success"):
        raise HTTPException(status_code=502, detail=publish_result.get("error", "Instagram post failed"))

    return publish_result
