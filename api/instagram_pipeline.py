"""
Instagram Pipeline API — the draft gate, exposed to the dashboard.

Self-contained: calls services/ig_pipeline.py in-process. No dependency on the
workspace root, because Railway only deploys this repo.
"""
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse

from services import ig_pipeline as igp

router = APIRouter()
PENDING = igp.PENDING
SPECS = igp.SPECS


def _state(d: Path) -> str:
    if (d / "APPROVED").exists():
        return "APPROVED"
    g = d / "gate.json"
    if g.exists():
        try:
            j = json.loads(g.read_text())
            return "PASS" if j.get("caption_ok") and j.get("human_ok") else "FAIL"
        except Exception:
            return "UNCHECKED"
    return "UNCHECKED"


def _summary(d: Path) -> dict:
    def _j(name):
        f = d / name
        if f.exists():
            try:
                return json.loads(f.read_text())
            except Exception:
                return {}
        return {}
    cap = (d / "caption.txt").read_text(encoding="utf-8") if (d / "caption.txt").exists() else ""
    spec = _j("spec.json")
    return {
        "slug": d.name,
        "state": _state(d),
        "slides": sorted(p.name for p in d.glob("[0-9]*.png")),
        "slide_count": len(sorted(d.glob("[0-9]*.png"))),
        "gate": _j("gate.json"),
        "caption": cap,
        "caption_preview": cap.split("\n")[0][:140],
        "brand": spec.get("brand", "dwt"),
        "post_date": spec.get("post_date"),
        "language": spec.get("language"),
        "modified": datetime.fromtimestamp(d.stat().st_mtime, timezone.utc).isoformat(),
    }


@router.get("/ig/pending")
async def pending():
    PENDING.mkdir(parents=True, exist_ok=True)
    items = [_summary(d) for d in sorted(PENDING.iterdir()) if d.is_dir()]
    return {"count": len(items), "items": items}


@router.get("/ig/specs")
async def specs():
    SPECS.mkdir(parents=True, exist_ok=True)
    out = []
    for f in sorted(SPECS.glob("*.json")):
        try:
            s = json.loads(f.read_text(encoding="utf-8"))
            out.append({"file": f.name, "slug": s.get("slug"), "brand": s.get("brand"),
                        "slides": len(s.get("slides", [])),
                        "title": (s.get("slides") or [{}])[0].get("title", ""),
                        "rendered": (PENDING / (s.get("slug") or "")).exists()})
        except Exception:
            continue
    return {"count": len(out), "items": out}


@router.get("/ig/slides/{slug}/{filename}")
async def slide(slug: str, filename: str):
    if any(x in slug + filename for x in ("/", "..", "\\")):
        raise HTTPException(400, "bad path")
    f = PENDING / slug / filename
    if not f.exists():
        raise HTTPException(404, "slide not found")
    return FileResponse(str(f))


@router.post("/ig/render")
async def render(payload: dict = Body(...)):
    """Render a spec by filename from data/ig-specs/, or an inline spec."""
    spec = payload.get("spec")
    if not spec:
        name = payload.get("file")
        if not name:
            raise HTTPException(400, "pass {file: '<name>.json'} or {spec: {...}}")
        f = SPECS / Path(name).name
        if not f.exists():
            raise HTTPException(404, f"no spec {name}")
        spec = json.loads(f.read_text(encoding="utf-8"))
    try:
        res = await asyncio.to_thread(igp.render, spec)
        await asyncio.to_thread(igp.gate, spec["slug"])
    except Exception as e:
        raise HTTPException(500, f"render failed: {str(e)[:400]}")
    return res


@router.post("/ig/check/{slug}")
async def check(slug: str):
    if not (PENDING / slug).exists():
        raise HTTPException(404, slug)
    g = await asyncio.to_thread(igp.gate, slug)
    return {"slug": slug, "gate": g, **_summary(PENDING / slug)}


@router.post("/ig/approve/{slug}")
async def approve(slug: str, force: bool = False):
    if not (PENDING / slug).exists():
        raise HTTPException(404, slug)
    try:
        return await asyncio.to_thread(igp.approve, slug, force)
    except Exception as e:
        raise HTTPException(400, str(e)[:400])


@router.post("/ig/reject/{slug}")
async def reject(slug: str):
    if not (PENDING / slug).exists():
        raise HTTPException(404, slug)
    return await asyncio.to_thread(igp.reject, slug)


@router.post("/ig/publish/{slug}")
async def publish(slug: str, dry_run: bool = True):
    """dry_run defaults TRUE — publishing for real is an explicit choice."""
    if not (PENDING / slug).exists():
        raise HTTPException(404, slug)
    try:
        res = await asyncio.to_thread(igp.publish, slug, dry_run)
        return {"slug": slug, "dry_run": dry_run, "ok": True, "result": res}
    except Exception as e:
        return {"slug": slug, "dry_run": dry_run, "ok": False, "error": str(e)[:600]}
