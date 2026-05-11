import os
from pathlib import Path
from dotenv import load_dotenv

# Load credentials from workspace .env
load_dotenv(Path(__file__).parent.parent / "credentials" / ".env")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from api.carousel import router as carousel_router
from api.runs import router as runs_router

app = FastAPI(
    title="DWT Agent Backend",
    description="API backend for Dream World Tours AI content pipelines",
    version="1.0.0",
)

# Allow Lovable frontend (and local dev) to call this API
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

# Serve generated carousel images as static files
OUTPUTS_DIR = Path(__file__).parent / "outputs" / "carousel"
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/outputs/carousel", StaticFiles(directory=str(OUTPUTS_DIR)), name="carousel_outputs")

# Routes
app.include_router(carousel_router, prefix="/api", tags=["Carousel Pipeline"])
app.include_router(runs_router, prefix="/api", tags=["Runs"])


@app.get("/health")
def health():
    return {
        "status": "ok",
        "anthropic_key": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "gemini_key": bool(os.environ.get("GEMINI_API_KEY")),
    }


@app.get("/")
def root():
    return {
        "name": "DWT Agent Backend",
        "docs": "/docs",
        "endpoints": {
            "POST /api/run/carousel": "Start carousel pipeline",
            "GET  /api/stream/{run_id}": "SSE live status stream",
            "GET  /api/runs": "List all runs",
            "GET  /api/runs/{run_id}": "Get run status + results",
        },
    }
