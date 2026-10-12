"""
Instagram publisher service for DWT Agent Hub.
Posts carousel slides to Instagram via Graph API.
Ported from scripts/instagram_poster.py.

Required env vars on Railway:
- INSTAGRAM_ACCESS_TOKEN: long-lived (60-day) page access token
- INSTAGRAM_BUSINESS_ACCOUNT_ID: numeric IG Business Account ID
"""
import os
import time
import asyncio
import requests

GRAPH_BASE = "https://graph.facebook.com/v19.0"


def _access_token() -> str:
    tok = os.environ.get("INSTAGRAM_ACCESS_TOKEN")
    if not tok:
        raise RuntimeError("INSTAGRAM_ACCESS_TOKEN not set on Railway")
    return tok


def _ig_account_id() -> str:
    acct = os.environ.get("INSTAGRAM_BUSINESS_ACCOUNT_ID")
    if not acct:
        raise RuntimeError("INSTAGRAM_BUSINESS_ACCOUNT_ID not set on Railway")
    return acct


def _post(endpoint: str, payload: dict) -> dict:
    url = f"{GRAPH_BASE}/{endpoint}"
    resp = requests.post(url, json={**payload, "access_token": _access_token()}, timeout=60)
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"Graph API error on {endpoint}: {data['error'].get('message', data['error'])}")
    return data


def _get(endpoint: str, params: dict = None) -> dict:
    url = f"{GRAPH_BASE}/{endpoint}"
    resp = requests.get(url, params={**(params or {}), "access_token": _access_token()}, timeout=60)
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"Graph API error on {endpoint}: {data['error'].get('message', data['error'])}")
    return data


def _create_carousel_item(image_url: str) -> str:
    data = _post(f"{_ig_account_id()}/media", {
        "image_url": image_url,
        "is_carousel_item": True,
    })
    return data["id"]


def _create_carousel_container(item_ids: list, caption: str) -> str:
    data = _post(f"{_ig_account_id()}/media", {
        "media_type": "CAROUSEL",
        "children": ",".join(item_ids),
        "caption": caption,
    })
    return data["id"]


def _create_single_image_container(image_url: str, caption: str) -> str:
    data = _post(f"{_ig_account_id()}/media", {
        "image_url": image_url,
        "caption": caption,
    })
    return data["id"]


def _wait_for_container(container_id: str, max_wait: int = 180) -> None:
    """Poll until container status is FINISHED."""
    polls = max_wait // 5
    for _ in range(polls):
        data = _get(f"{container_id}", {"fields": "status_code"})
        status = data.get("status_code", "")
        if status == "FINISHED":
            return
        if status == "ERROR":
            raise RuntimeError(f"Container {container_id} errored during Instagram processing")
        time.sleep(5)
    raise TimeoutError(f"Container {container_id} not ready after {max_wait}s")


def _publish(container_id: str) -> dict:
    return _post(f"{_ig_account_id()}/media_publish", {"creation_id": container_id})


def _permalink(post_id: str) -> str:
    try:
        data = _get(post_id, {"fields": "permalink"})
        return data.get("permalink", "")
    except Exception:
        return ""


def post_carousel_sync(image_urls: list, caption: str) -> dict:
    """Post a carousel of images to Instagram. Returns {success, post_id, permalink} or {success: False, error}."""
    if not image_urls:
        return {"success": False, "error": "No image URLs provided"}
    if len(image_urls) < 2:
        return {"success": False, "error": "Carousel requires at least 2 images"}
    if len(image_urls) > 10:
        return {"success": False, "error": "Instagram allows max 10 images per carousel"}

    # Validate all URLs are publicly fetchable HTTP URLs (imgbb, not local /api paths)
    for url in image_urls:
        if not url.startswith("http"):
            return {"success": False, "error": f"Image URL must be public HTTP(S): {url[:80]}"}

    try:
        # Step 1: create child item containers (parallel-ish via fast sequential)
        item_ids = []
        for url in image_urls:
            item_ids.append(_create_carousel_item(url))

        # Step 2: create the parent carousel container
        carousel_id = _create_carousel_container(item_ids, caption)

        # Step 3: wait for processing
        _wait_for_container(carousel_id)

        # Step 4: publish
        result = _publish(carousel_id)
        post_id = result["id"]
        permalink = _permalink(post_id)

        return {"success": True, "post_id": post_id, "permalink": permalink}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def post_carousel_async(image_urls: list, caption: str) -> dict:
    """Async wrapper — runs the sync Graph API calls in a thread."""
    return await asyncio.to_thread(post_carousel_sync, image_urls, caption)
