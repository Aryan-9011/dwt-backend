from pydantic import BaseModel
from typing import Optional, List
from enum import Enum


class RunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


class WorkflowType(str, Enum):
    CAROUSEL = "carousel"
    MARKETING_POST = "marketing_post"
    REEL_SCRIPTS = "reel_scripts"
    CONTENT_IDEAS = "content_ideas"


class CarouselRunRequest(BaseModel):
    inspiration: int = 5          # 4 or 5
    topic_hint: Optional[str] = None   # e.g. "hill stations" — leave blank for auto


class RunResponse(BaseModel):
    run_id: str
    workflow: WorkflowType
    status: RunStatus
    message: str


class SlideResult(BaseModel):
    index: int
    filename: str
    url: str           # public URL served by FastAPI static files


class RunResult(BaseModel):
    run_id: str
    workflow: WorkflowType
    status: RunStatus
    topic: Optional[str] = None
    slides: Optional[List[SlideResult]] = None
    caption: Optional[str] = None
    error: Optional[str] = None
    created_at: str
    completed_at: Optional[str] = None


class StatusEvent(BaseModel):
    run_id: str
    step: str           # "researching" | "writing_brief" | "generating_slides" | "complete" | "error"
    message: str
    progress: int       # 0–100
    data: Optional[dict] = None
