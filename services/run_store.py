"""
In-memory run store with JSON file persistence.
Tracks status and results for all pipeline runs.
"""
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any
import asyncio

STORE_PATH = Path(__file__).parent.parent / "run_history.json"

# In-memory store: run_id → run dict
_runs: Dict[str, dict] = {}

# SSE queues: run_id → asyncio.Queue of status event dicts
_queues: Dict[str, asyncio.Queue] = {}


def new_run(workflow: str) -> str:
    run_id = str(uuid.uuid4())[:8]
    _runs[run_id] = {
        "run_id": run_id,
        "workflow": workflow,
        "status": "queued",
        "topic": None,
        "slides": [],
        "caption": None,
        "error": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": None,
    }
    _queues[run_id] = asyncio.Queue()
    _persist()
    return run_id


def get_run(run_id: str) -> Optional[dict]:
    return _runs.get(run_id)


def get_all_runs() -> list:
    return sorted(_runs.values(), key=lambda r: r["created_at"], reverse=True)


def update_run(run_id: str, **kwargs):
    if run_id in _runs:
        _runs[run_id].update(kwargs)
        _persist()


def complete_run(run_id: str, topic: str, slides: list, caption: str):
    update_run(
        run_id,
        status="complete",
        topic=topic,
        slides=slides,
        caption=caption,
        completed_at=datetime.now(timezone.utc).isoformat(),
    )


def fail_run(run_id: str, error: str):
    update_run(
        run_id,
        status="failed",
        error=error,
        completed_at=datetime.now(timezone.utc).isoformat(),
    )


async def push_event(run_id: str, step: str, message: str, progress: int, data: dict = None):
    event = {"run_id": run_id, "step": step, "message": message, "progress": progress, "data": data or {}}
    if run_id in _queues:
        await _queues[run_id].put(event)


async def event_stream(run_id: str):
    """AsyncGenerator that yields SSE-formatted strings for a run."""
    if run_id not in _queues:
        yield f"data: {json.dumps({'error': 'run not found'})}\n\n"
        return

    queue = _queues[run_id]
    while True:
        try:
            event = await asyncio.wait_for(queue.get(), timeout=60)
            yield f"data: {json.dumps(event)}\n\n"
            if event["step"] in ("complete", "error"):
                break
        except asyncio.TimeoutError:
            yield "data: {\"step\": \"ping\"}\n\n"  # keep-alive


def _persist():
    try:
        STORE_PATH.write_text(json.dumps(list(_runs.values()), indent=2))
    except Exception:
        pass


def _load():
    if STORE_PATH.exists():
        try:
            for run in json.loads(STORE_PATH.read_text()):
                _runs[run["run_id"]] = run
        except Exception:
            pass


_load()
