"""
Brand pack loader.

Brand identity — name, wordmark, colours, fonts, voice, channels, trip source —
lives in backend/brands/<slug>/brand.json, never in code. Generators receive a
brand dict and read tokens from it.

Adding a brand = adding a folder. No code change.

Public API:
    list_brands()              → [{slug, name, colors, ...}, ...]
    get_brand(slug)            → brand dict (cached)
    resolve_brand(param)       → brand dict, falling back to DEFAULT_BRAND env
    brand_env(brand, channel, key) → namespaced credential lookup
    reference_doc(brand)       → workspace-relative path to the brand's ground-truth doc
"""
import os
import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

BRANDS_DIR = Path(__file__).parent.parent / "brands"

DEFAULT_BRAND = os.environ.get("DEFAULT_BRAND", "dwt")


class UnknownBrand(ValueError):
    """Raised when a brand slug has no brand.json."""


def _brand_path(slug: str) -> Path:
    return BRANDS_DIR / slug / "brand.json"


@lru_cache(maxsize=16)
def get_brand(slug: str) -> dict:
    """Load and cache one brand pack. Raises UnknownBrand if missing."""
    slug = (slug or "").strip().lower()
    path = _brand_path(slug)
    if not path.exists():
        known = ", ".join(b["slug"] for b in list_brands()) or "none"
        raise UnknownBrand(f"Unknown brand '{slug}'. Known brands: {known}")
    return json.loads(path.read_text(encoding="utf-8"))


def list_brands() -> list:
    """Every brand pack on disk, sorted with the default brand first."""
    if not BRANDS_DIR.exists():
        return []
    out = []
    for d in sorted(BRANDS_DIR.iterdir()):
        f = d / "brand.json"
        if not f.is_file():
            continue
        try:
            out.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            continue
    out.sort(key=lambda b: (b.get("slug") != DEFAULT_BRAND, b.get("slug", "")))
    return out


def resolve_brand(param: Optional[str] = None) -> dict:
    """
    Resolve a request's brand. Falls back to DEFAULT_BRAND so every existing
    DWT caller keeps working without passing anything.
    """
    return get_brand(param or DEFAULT_BRAND)


def brand_env(brand: dict, channel: str, key: str) -> Optional[str]:
    """
    Look up a channel credential using the brand's env prefix.

    DWT       → env_prefix ""           → INSTAGRAM_ACCESS_TOKEN
    Wandrcrew → env_prefix "WANDRCREW_" → WANDRCREW_INSTAGRAM_ACCESS_TOKEN
    """
    prefix = (brand.get("channels", {}).get(channel, {}) or {}).get("env_prefix", "")
    return os.environ.get(f"{prefix}{key}")


def channel_enabled(brand: dict, channel: str) -> bool:
    return bool((brand.get("channels", {}).get(channel, {}) or {}).get("enabled"))


def reference_doc(brand: dict) -> str:
    """Workspace-relative path to this brand's ground-truth reference doc."""
    return brand.get("reference_doc", "reference/brand-reference.md")


def allowed_inspirations(brand: dict) -> list:
    """Inspiration ids this brand is permitted to use (empty list = all)."""
    return brand.get("inspirations", [])
