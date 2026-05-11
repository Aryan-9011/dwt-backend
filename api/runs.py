from fastapi import APIRouter, HTTPException
from models import RunResult
from services import run_store

router = APIRouter()


@router.get("/runs", response_model=list[RunResult])
async def list_runs():
    """List all pipeline runs, newest first."""
    return run_store.get_all_runs()


@router.get("/runs/{run_id}", response_model=RunResult)
async def get_run(run_id: str):
    """Get status and results for a specific run."""
    run = run_store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run
