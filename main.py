import os
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from dotenv import load_dotenv

# Load credentials from workspace .env
load_dotenv(Path(__file__).parent.parent / "credentials" / ".env")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from api.carousel import router as carousel_router
from api.runs import router as runs_router
from api.gmb import router as gmb_router, run_gmb_pipeline
from api.growth import router as growth_router
from api.instagram import router as instagram_router
from api.landing_pages import router as landing_pages_router
from api.marketing_posts import router as marketing_posts_router
from api.skills import router as skills_router
from api.instagram_pipeline import router as ig_pipeline_router
from services import run_store, db
from services import package_extractor
from models import WorkflowType

STATIC_DIR = Path(__file__).parent / "static"
OUTPUTS_DIR = Path(__file__).parent / "outputs" / "carousel"
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

scheduler = AsyncIOScheduler(timezone="UTC")


async def _scheduled_gmb():
    """Mon/Wed/Fri 03:33 UTC = 09:03 IST — automated GMB post."""
    run_id = run_store.new_run(WorkflowType.GMB)
    await run_gmb_pipeline(run_id=run_id, force=False)


async def _scheduled_growth():
    """Every Monday 03:00 UTC = 08:30 IST — automated weekly content calendar."""
    from api.growth import _growth_pipeline
    run_id = run_store.new_run(WorkflowType.GROWTH_STRATEGY)
    await _growth_pipeline(run_id)


async def _scheduled_ig_gate():
    """Mon-Fri 03:30 UTC (09:00 IST) — re-run the gate on everything pending so
    the dashboard always shows current lint + detection results."""
    from services import ig_pipeline as igp
    igp.PENDING.mkdir(parents=True, exist_ok=True)
    for d in igp.PENDING.iterdir():
        if d.is_dir():
            try:
                await asyncio.to_thread(igp.gate, d.name)
            except Exception as e:
                print(f"[ig-gate] {d.name}: {str(e)[:120]}")


async def _bg_package_sync():
    """Auto-sync new PDFs on local dev. Railway reads from committed packages.json."""
    if package_extractor.ITINERARIES_DIR:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: package_extractor.sync_packages(verbose=False))


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    # On local dev: auto-extract any new PDFs in background (non-blocking)
    asyncio.create_task(_bg_package_sync())
    # Schedule GMB autopilot: Mon/Wed/Fri 03:33 UTC (09:03 IST)
    scheduler.add_job(
        _scheduled_gmb,
        "cron",
        day_of_week="mon,wed,fri",
        hour=3,
        minute=33,
        misfire_grace_time=3600,
    )
    # Schedule weekly growth calendar: every Monday 03:00 UTC (08:30 IST)
    scheduler.add_job(
        _scheduled_growth,
        "cron",
        day_of_week="mon",
        hour=3,
        minute=0,
        misfire_grace_time=3600,
    )
    # Instagram gate refresh — Mon-Fri 03:30 UTC (09:00 IST)
    scheduler.add_job(
        _scheduled_ig_gate,
        "cron",
        day_of_week="mon-fri",
        hour=3,
        minute=30,
        id="ig_gate",
        misfire_grace_time=3600,
    )
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(
    title="DWT Agent Hub",
    description="Dashboard for Dream World Tours AI automation agents",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS — allow all origins (internal tool)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Bypass ngrok browser warning for API calls
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

class NgrokHeaderMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["ngrok-skip-browser-warning"] = "true"
        return response

app.add_middleware(NgrokHeaderMiddleware)

# Static mounts
app.mount("/outputs/carousel", StaticFiles(directory=str(OUTPUTS_DIR)), name="carousel_outputs")

# Routes
app.include_router(carousel_router, prefix="/api", tags=["Carousel"])
app.include_router(runs_router, prefix="/api", tags=["Runs"])
app.include_router(gmb_router, prefix="/api", tags=["GMB"])
app.include_router(growth_router, prefix="/api", tags=["Growth"])
app.include_router(instagram_router, prefix="/api", tags=["Instagram"])
app.include_router(landing_pages_router, prefix="/api", tags=["Landing Pages"])
app.include_router(marketing_posts_router, prefix="/api", tags=["Marketing Posts"])
app.include_router(skills_router, prefix="/api", tags=["Skills"])
app.include_router(ig_pipeline_router, prefix="/api", tags=["Instagram Pipeline"])


@app.get("/api/packages")
def get_packages():
    pkgs = package_extractor.load_packages()
    return {"count": len(pkgs), "packages": [{"slug": p["slug"], "name": p["name"], "duration": p["duration"], "source": p.get("_source", "")} for p in pkgs]}


@app.get("/api/history")
def get_history(workflow: str = None, limit: int = 100):
    return {"runs": db.get_runs(workflow=workflow, limit=limit)}


@app.get("/health")
def health():
    return {
        "status": "ok",
        "anthropic_key": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "gemini_key": bool(os.environ.get("GEMINI_API_KEY")),
        "gbp_configured": bool(os.environ.get("GBP_REFRESH_TOKEN")),
        "scheduler": scheduler.running,
        "jobs": [j.id or j.name for j in scheduler.get_jobs()],
        "ig_pipeline": True,
    }


@app.get("/")
def dashboard():
    """Serve the Agent Hub dashboard."""
    index = STATIC_DIR / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return {"name": "DWT Agent Hub", "docs": "/docs"}
