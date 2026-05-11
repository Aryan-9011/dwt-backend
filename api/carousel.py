from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import StreamingResponse
from models import CarouselRunRequest, RunResponse, WorkflowType, RunStatus
from services import run_store, pipeline_runner

router = APIRouter()


@router.post("/run/carousel", response_model=RunResponse)
async def start_carousel(req: CarouselRunRequest, background_tasks: BackgroundTasks):
    """Kick off a carousel pipeline run. Returns run_id immediately."""
    run_id = run_store.new_run(WorkflowType.CAROUSEL)
    background_tasks.add_task(
        pipeline_runner.run_carousel,
        run_id=run_id,
        inspiration=req.inspiration,
        topic_hint=req.topic_hint,
    )
    return RunResponse(
        run_id=run_id,
        workflow=WorkflowType.CAROUSEL,
        status=RunStatus.QUEUED,
        message="Pipeline started. Connect to /api/stream/{run_id} for live updates.",
    )


@router.get("/stream/{run_id}")
async def stream_run(run_id: str):
    """SSE endpoint — stream real-time status events for a run."""
    return StreamingResponse(
        run_store.event_stream(run_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
