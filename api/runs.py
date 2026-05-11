from pathlib import Path
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from models import RunResult
from services import run_store

OUTPUTS_DIR = Path(__file__).parent.parent / "outputs" / "carousel"

router = APIRouter()


@router.get("/runs", response_model=list[RunResult])
async def list_runs():
    return run_store.get_all_runs()


@router.get("/runs/{run_id}", response_model=RunResult)
async def get_run(run_id: str):
    run = run_store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.get("/slides/{run_id}/{filename}")
async def get_slide(run_id: str, filename: str):
    """Serve a slide image — URL is always relative to the backend, works with any tunnel or domain."""
    path = OUTPUTS_DIR / run_id / filename
    if not path.exists() or not path.suffix in (".png", ".jpg", ".jpeg"):
        raise HTTPException(status_code=404, detail="Slide not found")
    return FileResponse(path, media_type="image/png")
