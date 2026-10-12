import asyncio
from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import StreamingResponse
from models import WorkflowType, RunStatus
from services import run_store, db

router = APIRouter()


async def _growth_pipeline(run_id: str):
    """Background task: gather live IG intel, research web trends, generate calendar, persist to DB."""
    from scripts.growth_autopilot import generate_growth_calendar
    from services.instagram_intel import gather_intel
    from services.web_research import research_travel_trends

    try:
        await run_store.push_event(
            run_id, "fetching_ig",
            "Fetching Instagram data — DWT + 4 competitors via Apify (parallel)…",
            10,
        )

        recent_runs = db.get_runs(workflow="growth_strategy", limit=5)
        recent_topics: list[str] = []
        for r in recent_runs:
            result = r.get("result") or {}
            for item in result.get("calendar", [])[:3]:
                recent_topics.append(item.get("topic", ""))

        # Step 1: Apify scrape DWT + competitors in parallel
        intel = await gather_intel()

        # Step 2: Web research for trending travel articles (DWT-aware)
        await run_store.push_event(
            run_id, "researching_web",
            "Researching trending travel articles via Gemini + Google Search…",
            35,
        )
        from scripts.growth_autopilot import _dwt_destination_keywords
        dwt_destinations = _dwt_destination_keywords()
        web_research = await asyncio.to_thread(research_travel_trends, dwt_destinations)

        # Step 3: Analyze + report summary
        if intel.get("available"):
            d = intel.get("dwt", {})
            comp_count = len([c for c in intel.get("competitors", []) if c.get("posts_last_7d",0)>0])
            await run_store.push_event(
                run_id, "analyzing",
                f"Analyzing — engagement {d.get('engagement_rate_pct',0)}%, {d.get('posts_last_7d',0)} DWT posts, {comp_count}/4 competitors, {len(web_research.get('articles',[])) if web_research.get('available') else 0} web articles",
                60, data={"intel_summary": {
                    "engagement_rate_pct": d.get("engagement_rate_pct", 0),
                    "posts_last_7d": d.get("posts_last_7d", 0),
                    "followers": d.get("followers", 0),
                    "competitors_analyzed": comp_count,
                    "web_articles_found": len(web_research.get("articles", [])) if web_research.get("available") else 0,
                }}
            )
        else:
            await run_store.push_event(
                run_id, "analyzing",
                f"Apify unavailable — using {len(web_research.get('articles',[])) if web_research.get('available') else 0} web articles + package data",
                60,
            )

        # Step 4: Generate calendar with all context
        await run_store.push_event(run_id, "generating", "Generating data-driven 7-day calendar with Gemini…", 80)

        result = await asyncio.to_thread(generate_growth_calendar, recent_topics[:10], intel, web_research)

        db.save_run(
            run_id=run_id,
            workflow="growth_strategy",
            status="complete",
            topic=result["week_of"],
            result=result,
        )
        run_store.update_run(run_id, status=RunStatus.COMPLETE)
        await run_store.push_event(
            run_id, "complete",
            f"7-day calendar ready for {result['week_of']}",
            100,
            data=result,
        )

    except Exception as e:
        err = str(e)
        db.save_run(
            run_id=run_id, workflow="growth_strategy",
            status="failed", topic="error", result={"error": err},
        )
        run_store.update_run(run_id, status=RunStatus.FAILED)
        await run_store.push_event(run_id, "error", f"Failed: {err}", 0)


@router.post("/growth/run")
async def run_growth_strategy(background_tasks: BackgroundTasks):
    """Trigger a new 7-day content calendar generation."""
    run_id = run_store.new_run(WorkflowType.GROWTH_STRATEGY)
    background_tasks.add_task(_growth_pipeline, run_id)
    return {"run_id": run_id, "status": "running", "stream_url": f"/api/stream/{run_id}"}


@router.get("/growth/calendar")
async def get_latest_calendar():
    """Return the most recent completed growth strategy calendar."""
    runs = db.get_runs(workflow="growth_strategy", limit=1)
    if not runs or runs[0].get("status") != "complete":
        return {"calendar": None, "week_of": None, "run_id": None}
    r = runs[0]
    result = r.get("result") or {}
    return {
        "run_id": r["id"],
        "week_of": result.get("week_of"),
        "calendar": result.get("calendar", []),
        "intel": result.get("intel"),
        "web_research": result.get("web_research"),
        "created_at": r.get("created_at"),
    }


@router.get("/growth/history")
async def get_growth_history(limit: int = 12):
    """Return past growth strategy runs (metadata only)."""
    runs = db.get_runs(workflow="growth_strategy", limit=limit)
    out = []
    for r in runs:
        result = r.get("result") or {}
        out.append({
            "run_id": r["id"],
            "week_of": result.get("week_of") or r.get("topic"),
            "status": r.get("status"),
            "created_at": r.get("created_at"),
            "calendar": result.get("calendar", []),
            "intel": result.get("intel"),
        "web_research": result.get("web_research"),
        })
    return {"runs": out}
