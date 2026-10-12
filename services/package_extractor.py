"""
Dynamic DWT package data extractor.

- Scans reference/itineraries/*.pdf for new/changed files (detected by MD5 hash)
- Extracts structured data (name, price, departures, highlights, scene) via Gemini
- Persists to backend/data/packages.json  ← committed to git, deployed to Railway

Local usage (runs automatically at app startup when PDFs are present):
    python -m services.package_extractor

Railway usage:
    Reads from committed packages.json — no PDFs needed on server.
"""
import os
import json
import hashlib
from pathlib import Path
from typing import Optional

import requests

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "AIzaSyCO0g2c42fl7COFiLASbYKS9EZNzrN2mvM")

_BACKEND = Path(__file__).parent.parent

# Where extracted data is persisted (committed to git)
PACKAGES_JSON = _BACKEND / "data" / "packages.json"

# PDF source — look in project root first (local dev), then backend/ (in case user copies there)
_PDF_ROOTS = [
    _BACKEND.parent / "reference" / "itineraries",
    _BACKEND / "reference" / "itineraries",
]
ITINERARIES_DIR: Optional[Path] = next((p for p in _PDF_ROOTS if p.exists()), None)


EXTRACT_PROMPT = """You are extracting structured data from a Dream World Tours (DWT) travel itinerary PDF.

Return ONLY valid JSON with this exact structure — no markdown, no explanation:
{{
  "slug": "lowercase-hyphenated-name",
  "name": "Tour Display Name",
  "duration": "e.g. 6N/7D",
  "price_display": "e.g. From ₹55,000",
  "flights": true,
  "departures": ["e.g. May 2026", "Jun 2026"],
  "highlights": [
    "Highlight 1 — max 65 chars, activity/experience focused",
    "Highlight 2",
    "Highlight 3",
    "Highlight 4",
    "Highlight 5"
  ],
  "spotlight_fact": "One memorable, emotional sentence about the destination's unique draw",
  "scene": "Detailed cinematic photo description for AI image gen — specific landmark + time of day + lighting + mood + composition"
}}

Rules:
- slug: lowercase, hyphens only, no special chars (e.g. kashmir-ladakh)
- flights: true if text says flights included/incl, false otherwise
- departures: only upcoming/future dates, format as "DD Mon YYYY" or "Mon YYYY"
- highlights: exactly 5, punchy, specific experiences — not generic phrases
- spotlight_fact: unique to this destination, creates FOMO in the reader
- scene: very cinematic and specific (e.g. "Pangong Lake at sunrise — vast deep-blue high-altitude lake, snow-capped Pir Panjal range, lone tent on shore, pale gold sky")

Itinerary text:
{text}"""


def _md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()[:12]


def _extract_pdf_text(pdf_path: Path) -> str:
    try:
        import pdfplumber
        with pdfplumber.open(str(pdf_path)) as pdf:
            pages = [page.extract_text() or "" for page in pdf.pages]
        return "\n".join(pages)[:8000]
    except ImportError:
        raise RuntimeError("pdfplumber not installed — run: pip install pdfplumber")
    except Exception as e:
        raise RuntimeError(f"PDF read error: {e}")


def _gemini_extract(text: str) -> dict:
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    )
    resp = requests.post(url, json={
        "contents": [{"parts": [{"text": EXTRACT_PROMPT.format(text=text)}]}],
        "generationConfig": {"temperature": 0.1},
    }, timeout=60)
    resp.raise_for_status()
    raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())


def load_packages() -> list:
    """Load packages from committed JSON. Returns [] if file missing."""
    if PACKAGES_JSON.exists():
        try:
            return json.loads(PACKAGES_JSON.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def sync_packages(verbose: bool = True) -> list:
    """
    Scan ITINERARIES_DIR for PDFs.
    Extract any that are new or changed (detected by MD5 hash).
    Save/update packages.json.
    Returns the full list of packages.
    """
    if not ITINERARIES_DIR:
        if verbose:
            print("[package_extractor] No itineraries directory found — using packages.json as-is")
        return load_packages()

    # Build existing map: slug → package (with _hash for change detection)
    existing = {p["slug"]: p for p in load_packages()}
    known_hashes = {p["_hash"] for p in existing.values() if p.get("_hash")}
    new_hashes: dict[str, str] = {}  # pdf_name → hash (for all current PDFs)

    pdfs = sorted(ITINERARIES_DIR.glob("*.pdf"))
    if not pdfs:
        if verbose:
            print(f"[package_extractor] No PDFs found in {ITINERARIES_DIR}")
        return load_packages()

    changed = False
    for pdf in pdfs:
        h = _md5(pdf)
        new_hashes[pdf.name] = h

        if h in known_hashes:
            continue  # already extracted, skip

        if verbose:
            print(f"[package_extractor] Extracting: {pdf.name} …")
        try:
            text = _extract_pdf_text(pdf)
            pkg = _gemini_extract(text)
            pkg["_hash"] = h
            pkg["_source"] = pdf.name
            # Resolve slug collision: if slug exists from a *different* PDF, append duration
            slug = pkg["slug"]
            if slug in existing and existing[slug].get("_source") != pdf.name:
                dur = pkg.get("duration", "").lower().replace("/", "-").replace(" ", "")
                slug = f"{slug}-{dur}"
                pkg["slug"] = slug
            existing[slug] = pkg
            changed = True
            if verbose:
                print(f"  → {pkg['name']}  {pkg['duration']}  {pkg['price_display']}")
        except Exception as e:
            if verbose:
                print(f"  ✗ Failed: {e}")

    # Remove packages whose source PDF was deleted
    # BUT preserve manual entries (source starts with "manual-added" — for tours without PDFs)
    current_pdf_names = {p.name for p in pdfs}
    to_remove = [
        slug for slug, pkg in existing.items()
        if pkg.get("_source")
        and pkg["_source"] not in current_pdf_names
        and not pkg["_source"].startswith("manual-added")
    ]
    for slug in to_remove:
        if verbose:
            print(f"[package_extractor] Removed (PDF deleted): {slug}")
        del existing[slug]
        changed = True

    packages = list(existing.values())

    if changed:
        PACKAGES_JSON.parent.mkdir(parents=True, exist_ok=True)
        PACKAGES_JSON.write_text(
            json.dumps(packages, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        if verbose:
            print(f"[package_extractor] Saved {len(packages)} packages → {PACKAGES_JSON}")
    else:
        if verbose:
            print(f"[package_extractor] All {len(packages)} packages up-to-date.")

    return packages


if __name__ == "__main__":
    sync_packages(verbose=True)
