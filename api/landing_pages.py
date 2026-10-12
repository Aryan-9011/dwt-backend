"""
Landing Pages API — REST endpoints for the Agent Hub dashboard.

Endpoints:
- GET  /api/landing-pages/list                  → list all generated pages + briefs
- POST /api/landing-pages/build                 → build a single page from posted brief JSON
- POST /api/landing-pages/build-all             → batch-build all briefs in _briefs/
- POST /api/landing-pages/mine-reviews          → fetch real Google reviews via Apify
- GET  /api/landing-pages/preview/{filename}    → serve generated HTML file
- GET  /api/landing-pages/download/{filename}   → download as attachment
"""
import os
from pathlib import Path
from datetime import datetime

from fastapi import APIRouter, HTTPException, Body
from fastapi.responses import FileResponse, JSONResponse

from services.landing_page_builder import build_from_brief, save_html, BUILDERS, _load_brief
from services.review_miner import get_quotes_for, fetch_all_reviews

router = APIRouter()

ROOT = Path(__file__).parent.parent.parent
BRIEFS_DIR = ROOT / "outputs" / "landing-pages" / "_briefs"
PAGES_DIR = ROOT / "outputs" / "landing-pages"


def _safe_filename(name: str) -> str:
    """Allow only alphanumeric + dash + underscore + .html"""
    return "".join(c for c in name if c.isalnum() or c in "-_.") if name else ""


@router.get("/landing-pages/debug")
async def debug_paths():
    """Diagnostic: show what's on disk at the expected paths."""
    import os
    return {
        "cwd": os.getcwd(),
        "ROOT": str(ROOT),
        "BRIEFS_DIR": str(BRIEFS_DIR),
        "BRIEFS_DIR_exists": BRIEFS_DIR.exists(),
        "BRIEFS_listing": [p.name for p in BRIEFS_DIR.glob("*")] if BRIEFS_DIR.exists() else None,
        "PAGES_DIR": str(PAGES_DIR),
        "PAGES_DIR_exists": PAGES_DIR.exists(),
        "PAGES_listing": [p.name for p in PAGES_DIR.glob("*.html")] if PAGES_DIR.exists() else None,
        "ROOT_listing": sorted([p.name for p in ROOT.iterdir()])[:20] if ROOT.exists() else None,
        "outputs_listing": sorted([p.name for p in (ROOT/"outputs").iterdir()]) if (ROOT/"outputs").exists() else None,
    }


@router.get("/landing-pages/list")
async def list_pages():
    """Return all briefs and all generated pages."""
    briefs = []
    if BRIEFS_DIR.exists():
        for p in sorted(BRIEFS_DIR.glob("*.yaml")) + sorted(BRIEFS_DIR.glob("*.json")):
            try:
                brief = _load_brief(str(p))
                briefs.append({
                    "filename": p.name,
                    "slug": brief.get("slug", p.stem),
                    "type": brief.get("type", "unknown"),
                    "modified": datetime.fromtimestamp(p.stat().st_mtime).isoformat(),
                })
            except Exception as e:
                briefs.append({
                    "filename": p.name,
                    "slug": p.stem,
                    "type": "error",
                    "error": str(e)[:120],
                })

    pages = []
    if PAGES_DIR.exists():
        for p in sorted(PAGES_DIR.glob("*.html")):
            stat = p.stat()
            pages.append({
                "filename": p.name,
                "size_kb": stat.st_size // 1024,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "preview_url": f"/api/landing-pages/preview/{p.name}",
                "download_url": f"/api/landing-pages/download/{p.name}",
            })

    return {
        "briefs": briefs,
        "pages": pages,
        "supported_types": list(BUILDERS.keys()),
    }


@router.post("/landing-pages/build")
async def build_page(brief: dict = Body(...)):
    """Build a single page from a brief JSON payload (sent from the dashboard form)."""
    if not isinstance(brief, dict):
        raise HTTPException(400, "Brief must be a JSON object")
    if "type" not in brief or "slug" not in brief:
        raise HTTPException(400, "Brief must include 'type' and 'slug' fields")
    if brief["type"] not in BUILDERS:
        raise HTTPException(400, f"Unsupported type. Use one of: {list(BUILDERS.keys())}")

    # Save the brief as YAML so it's persistent + reusable
    import yaml
    BRIEFS_DIR.mkdir(parents=True, exist_ok=True)
    brief_path = BRIEFS_DIR / f"{brief['slug']}.yaml"
    brief_path.write_text(yaml.safe_dump(brief, sort_keys=False, allow_unicode=True))

    # Build the HTML
    try:
        builder = BUILDERS[brief["type"]]
        html = builder(brief)
        out_path = save_html(brief["slug"], html, brief_type=brief["type"])
    except Exception as e:
        raise HTTPException(500, f"Build failed: {str(e)[:300]}")

    filename = Path(out_path).name
    return {
        "success": True,
        "filename": filename,
        "slug": brief["slug"],
        "type": brief["type"],
        "brief_path": str(brief_path),
        "size_kb": Path(out_path).stat().st_size // 1024,
        "preview_url": f"/api/landing-pages/preview/{filename}",
        "download_url": f"/api/landing-pages/download/{filename}",
    }


@router.post("/landing-pages/build-all")
async def build_all_briefs():
    """Re-build every brief in BRIEFS_DIR. Returns per-brief results."""
    if not BRIEFS_DIR.exists():
        raise HTTPException(404, "No briefs directory")

    results = []
    for p in sorted(BRIEFS_DIR.glob("*.yaml")) + sorted(BRIEFS_DIR.glob("*.json")):
        try:
            r = build_from_brief(str(p))
            out_path = save_html(r["slug"], r["html"], brief_type=r["brief_type"])
            results.append({
                "brief": p.name,
                "success": True,
                "filename": Path(out_path).name,
                "type": r["brief_type"],
            })
        except Exception as e:
            results.append({
                "brief": p.name,
                "success": False,
                "error": str(e)[:300],
            })
    return {
        "total": len(results),
        "succeeded": sum(1 for r in results if r["success"]),
        "failed": sum(1 for r in results if not r["success"]),
        "results": results,
    }


@router.post("/landing-pages/mine-reviews")
async def mine_reviews(payload: dict = Body(...)):
    """Fetch matching Google reviews for a topic. Used to fill in testimonials in briefs.
    Payload: { "topic": "kashmir" | "vietnam" | "family" | etc., "count": 3 }
    """
    topic = (payload.get("topic") or "").strip().lower()
    count = int(payload.get("count", 3))
    force_refresh = bool(payload.get("force_refresh", False))

    if not topic:
        raise HTTPException(400, "Payload must include 'topic'")
    if not os.environ.get("APIFY_TOKEN"):
        raise HTTPException(400, "APIFY_TOKEN not set on this environment")

    try:
        if force_refresh:
            await fetch_all_reviews(force_refresh=True)
        quotes = await get_quotes_for(topic, count=count)
    except Exception as e:
        raise HTTPException(500, f"Review mining failed: {str(e)[:300]}")

    return {
        "topic": topic,
        "count_returned": len(quotes),
        "quotes": quotes,
    }


@router.get("/landing-pages/preview/{filename}")
async def preview_page(filename: str):
    """Serve a generated HTML page in the browser."""
    safe = _safe_filename(filename)
    if not safe or not safe.endswith(".html"):
        raise HTTPException(400, "Invalid filename")
    p = PAGES_DIR / safe
    if not p.exists():
        raise HTTPException(404, "Page not found")
    return FileResponse(str(p), media_type="text/html")


@router.get("/landing-pages/download/{filename}")
async def download_page(filename: str):
    """Download a generated HTML page as an attachment."""
    safe = _safe_filename(filename)
    if not safe or not safe.endswith(".html"):
        raise HTTPException(400, "Invalid filename")
    p = PAGES_DIR / safe
    if not p.exists():
        raise HTTPException(404, "Page not found")
    return FileResponse(
        str(p),
        media_type="text/html",
        filename=safe,
        headers={"Content-Disposition": f'attachment; filename="{safe}"'},
    )


@router.delete("/landing-pages/page/{filename}")
async def delete_page(filename: str):
    """Delete a generated HTML page (does not delete the brief)."""
    safe = _safe_filename(filename)
    if not safe or not safe.endswith(".html"):
        raise HTTPException(400, "Invalid filename")
    p = PAGES_DIR / safe
    if not p.exists():
        raise HTTPException(404, "Page not found")
    p.unlink()
    return {"success": True, "deleted": safe}
