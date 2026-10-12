import io
import zipfile
from pathlib import Path

import requests as req_lib
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
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


# IMPORTANT: specific route must come BEFORE the {filename} wildcard route
@router.get("/slides/{run_id}/download-all.zip")
async def download_all_slides_zip(run_id: str):
    """Bundle all slides for a carousel run into a ZIP for download."""
    from services import db as _db

    zip_buf = io.BytesIO()

    # Try local filesystem first (works if container hasn't restarted)
    out_dir = OUTPUTS_DIR / run_id
    local_pngs = sorted(out_dir.glob("*.png")) if out_dir.exists() else []

    if local_pngs:
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for png in local_pngs:
                zf.write(png, png.name)
    else:
        # Fetch slide URLs from Postgres
        runs = _db.get_runs(limit=500)
        run = next((r for r in runs if r["id"] == run_id), None)
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")
        slides = (run.get("result") or {}).get("slides", [])
        if not slides:
            raise HTTPException(status_code=404, detail="No slides found for this run")
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for s in slides:
                url = s.get("url", "")
                fname = s.get("filename", f"slide-{s.get('index', 0)}.png")
                if url.startswith("http"):
                    try:
                        r = req_lib.get(url, timeout=30)
                        r.raise_for_status()
                        zf.writestr(fname, r.content)
                    except Exception:
                        pass

    zip_buf.seek(0)
    return StreamingResponse(
        zip_buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="carousel-{run_id}.zip"'},
    )


@router.get("/slides/{run_id}/{filename}")
async def get_slide(run_id: str, filename: str, download: bool = False):
    """Serve a slide image. Pass ?download=true to force browser download."""
    path = OUTPUTS_DIR / run_id / filename
    if not path.exists() or path.suffix not in (".png", ".jpg", ".jpeg"):
        raise HTTPException(status_code=404, detail="Slide not found")
    headers = {}
    if download:
        headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return FileResponse(path, media_type="image/png", headers=headers)
