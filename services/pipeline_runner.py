"""
Orchestrates the full carousel pipeline.

MODE A  USE_AGENTS=true   → spawns claude CLI in workspace root — full agent pipeline
        (travel-article-researcher → carousel-content-writer → creative-designer)
        Uses real web research, Inspiration 4 briefs, nano-banana image generation.

MODE B  USE_AGENTS=false  → standalone Python pipeline (Claude API + Gemini direct)
        Fallback for Railway / environments without Claude Code installed.
"""
import os
import json
import base64
import asyncio
import shutil
import requests
from datetime import date
from pathlib import Path

from services import run_store, researcher, image_generator as ig, db

OUTPUTS_DIR = Path(__file__).parent.parent / "outputs" / "carousel"
BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000")
IMGBB_API_KEY = os.environ.get("IMGBB_API_KEY")


def _upload_imgbb(image_path: str, name: str) -> str:
    """Upload image to imgbb and return permanent URL."""
    if not IMGBB_API_KEY:
        raise RuntimeError("IMGBB_API_KEY not set")
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    resp = requests.post(
        "https://api.imgbb.com/1/upload",
        data={"key": IMGBB_API_KEY, "image": b64, "name": Path(name).stem},
        timeout=60,
    )
    result = resp.json()
    if not result.get("success"):
        raise RuntimeError(f"imgbb upload failed: {result}")
    return result["data"]["url"]
USE_AGENTS = os.environ.get("USE_AGENTS", "false").lower() == "true"

# Auto-detect workspace root:
# Railway/Docker  → RAILWAY_ENVIRONMENT is set → use bundled backend/workspace/
# Local dev       → use the real workspace 3 levels up (full agents + MCP + reference files)
_backend_dir = Path(__file__).parent.parent
if os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("RAILWAY_SERVICE_NAME"):
    WORKSPACE_ROOT = _backend_dir / "workspace"
else:
    WORKSPACE_ROOT = _backend_dir.parent


async def run_carousel(run_id: str, inspiration: int, topic_hint: str = None):
    if USE_AGENTS:
        await _run_via_agents(run_id, topic_hint)
    else:
        await _run_standalone(run_id, inspiration, topic_hint)


# ── MODE A — Full Agent Pipeline ───────────────────────────────────────────────

async def _run_via_agents(run_id: str, topic_hint: str = None):
    run_store.update_run(run_id, status="running")

    prompt = "Run the carousel auto pipeline for today"
    if topic_hint:
        prompt += f". Topic hint: {topic_hint}"

    await run_store.push_event(run_id, "researching", "Starting agent pipeline...", 5)

    # Find claude — try direct binary first, fall back to npx
    import shutil as sh
    claude_bin = sh.which("claude")
    base_flags = ["-p", prompt, "--output-format", "stream-json", "--verbose",
                  "--dangerously-skip-permissions"]
    if claude_bin:
        cmd = [claude_bin] + base_flags
    else:
        npx_bin = sh.which("npx")
        if not npx_bin:
            run_store.fail_run(run_id, "claude CLI not found. Install Node.js + Claude Code.")
            await run_store.push_event(run_id, "error", "claude CLI not found", 0)
            return
        cmd = [npx_bin, "-y", "@anthropic-ai/claude-code"] + base_flags

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(WORKSPACE_ROOT),
            env={**os.environ},
        )

        progress = 10
        last_msg = ""

        async for raw_line in process.stdout:
            line = raw_line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
                etype = event.get("type")

                if etype == "assistant":
                    for block in event.get("message", {}).get("content", []):
                        if block.get("type") == "text":
                            text = block["text"].strip()
                            if not text or text == last_msg:
                                continue
                            last_msg = text
                            tl = text.lower()
                            if any(w in tl for w in ["research", "article", "search", "fetch"]):
                                stage, progress = "researching", max(progress, 15)
                            elif any(w in tl for w in ["brief", "writ", "caption", "slide copy"]):
                                stage, progress = "writing_brief", max(progress, 40)
                            elif any(w in tl for w in ["generat", "image", "design", "nano"]):
                                stage, progress = "generating_slides", max(progress, 60)
                            else:
                                stage = "generating_slides"
                            progress = min(progress + 2, 90)
                            await run_store.push_event(run_id, stage, text[:140], progress)

                elif etype == "result":
                    if event.get("is_error") or event.get("subtype") == "error":
                        raise RuntimeError(event.get("result", "Agent pipeline failed"))

            except json.JSONDecodeError:
                pass

        await process.wait()

        if process.returncode != 0:
            stderr_out = await process.stderr.read()
            raise RuntimeError(
                f"claude exited {process.returncode}: {stderr_out.decode()[:400]}"
            )

    except Exception as e:
        run_store.fail_run(run_id, str(e))
        await run_store.push_event(run_id, "error", str(e), 0)
        raise

    # ── Collect slides from workspace outputs ──────────────────────────────
    await run_store.push_event(run_id, "generating_slides", "Collecting generated slides...", 93)

    today_str = date.today().strftime("%Y-%m-%d")
    pipeline_dir = WORKSPACE_ROOT / "outputs" / "automation" / "carousel-pipeline"

    slides_dir = pipeline_dir / f"slides-{today_str}"
    if not slides_dir.exists():
        candidates = sorted(pipeline_dir.glob("slides-*"), reverse=True)
        if not candidates:
            run_store.fail_run(run_id, "No slides folder found after pipeline run")
            await run_store.push_event(run_id, "error", "No slides generated", 0)
            return
        slides_dir = candidates[0]

    out_dir = OUTPUTS_DIR / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for i, png in enumerate(sorted(slides_dir.glob("slide-*.png"))):
        dest = out_dir / png.name
        shutil.copy2(png, dest)
        url = f"/api/slides/{run_id}/{png.name}"
        results.append({"index": i, "filename": png.name, "url": url})

    # Get caption
    caption = ""
    caption_file = pipeline_dir / f"caption-{today_str}.txt"
    if not caption_file.exists():
        candidates = sorted(pipeline_dir.glob("caption-*.txt"), reverse=True)
        caption_file = candidates[0] if candidates else None
    if caption_file and caption_file.exists():
        caption = caption_file.read_text()

    topic = topic_hint or f"Carousel {today_str}"

    run_store.complete_run(run_id, topic=topic, slides=results, caption=caption)
    await run_store.push_event(
        run_id, "complete",
        f"Done! {len(results)} slides generated via agent pipeline.",
        100,
        {"slides": results, "caption": caption, "topic": topic},
    )
    db.save_run(run_id, "carousel", "complete", topic=topic,
                result={"topic": topic, "slides": results, "caption": caption})


# ── MODE B — Standalone Python Pipeline ───────────────────────────────────────

async def _run_standalone(run_id: str, inspiration: int, topic_hint: str = None):
    run_store.update_run(run_id, status="running")

    try:
        await run_store.push_event(run_id, "researching", "Finding the best topic for today...", 5)

        # Pull recent topics from POSTGRES (persistent across redeploys)
        # not from in-memory run_store which gets wiped on every container restart
        recent_db_runs = db.get_runs(workflow="carousel", limit=20)
        recent: list[str] = []
        for r in recent_db_runs:
            if r.get("status") != "complete":
                continue
            if r.get("id") == run_id:
                continue
            topic = r.get("topic")
            if topic and topic.lower() not in [t.lower() for t in recent]:
                recent.append(topic)
            # Also pull destination names from prior slide filenames for richer avoidance
            FILENAME_NOISE = {"slide", "cover", "cta", "intro", "outro", "01", "02", "03", "04", "05", "06", "07", "08", "09", "10"}
            result = r.get("result") or {}
            if isinstance(result, dict):
                for s in (result.get("slides") or [])[:5]:
                    if isinstance(s, dict):
                        fname = (s.get("filename") or "").lower()
                        snippet = fname.replace(".png", "").replace(".jpg", "")
                        for chunk in snippet.split("-"):
                            chunk = chunk.strip()
                            if (len(chunk) > 4
                                and not chunk.isdigit()
                                and chunk not in FILENAME_NOISE
                                and chunk not in [t.lower() for t in recent]):
                                recent.append(chunk)
        recent = recent[:15]
        print(f"[researcher] avoiding {len(recent)} recent topics/destinations: {recent[:8]}")

        # NEW: Pull current trending travel articles via Gemini Google Search grounding
        # This grounds topic selection in real articles being published THIS WEEK,
        # not just Gemini's training-data guesses.
        await run_store.push_event(run_id, "researching", "Searching the web for trending travel articles...", 8)
        try:
            from services.web_research import research_travel_trends
            web_research = await asyncio.to_thread(research_travel_trends)
            n_articles = len(web_research.get("articles", [])) if web_research.get("available") else 0
            n_actionable = sum(1 for a in (web_research.get("articles") or []) if a.get("actionable"))
            if web_research.get("available"):
                await run_store.push_event(
                    run_id, "researching",
                    f"Found {n_articles} live travel articles ({n_actionable} matching DWT destinations)",
                    12,
                )
        except Exception as e:
            print(f"[researcher] web research skipped: {str(e)[:120]}")
            web_research = None

        data = await researcher.research_topic(
            date=date.today().isoformat(),
            avoid_topics=recent,
            topic_hint=topic_hint,
            web_research=web_research,
        )

        topic = data["theme"]
        run_store.update_run(run_id, topic=topic)
        await run_store.push_event(run_id, "researching", f"Topic: {topic}", 15, {"topic": topic, "web_research": web_research})

        await run_store.push_event(run_id, "writing_brief", "Writing slide briefs...", 20)
        slides_data = _build_slides(data, inspiration)
        n = len(slides_data)

        out_dir = OUTPUTS_DIR / run_id
        out_dir.mkdir(parents=True, exist_ok=True)

        results = []
        for i, slide in enumerate(slides_data):
            pct = 25 + int((i / n) * 65)
            await run_store.push_event(
                run_id, "generating_slides",
                f"Generating slide {i + 1} of {n}: {slide['label']}...",
                pct,
            )
            filename = slide["filename"]
            path = str(out_dir / filename)
            await asyncio.to_thread(ig.generate_slide, slide["prompt"], path)
            # Upload to imgbb for permanent URL (survives container restarts)
            try:
                permanent_url = await asyncio.to_thread(_upload_imgbb, path, filename)
            except Exception:
                permanent_url = None
            url = permanent_url or f"/api/slides/{run_id}/{filename}"
            results.append({"index": i, "filename": filename, "url": url, "permanent": bool(permanent_url)})

        await run_store.push_event(run_id, "generating_slides", "Writing Instagram caption...", 93)
        caption_original = _build_caption(data)

        # Apply stop-slop pass to remove AI writing patterns
        await run_store.push_event(run_id, "generating_slides", "Polishing caption (stop-slop)...", 95)
        from services.stop_slop import clean as stop_slop_clean
        slop_result = await stop_slop_clean(caption_original)
        caption = slop_result["cleaned"]
        if slop_result["changed"]:
            print(f"[stop-slop] caption revised — original {len(caption_original)} chars, cleaned {len(caption)} chars")

        (out_dir / "caption.txt").write_text(caption)
        (out_dir / "caption-original.txt").write_text(caption_original)  # keep for comparison

        run_store.complete_run(run_id, topic=topic, slides=results, caption=caption)
        await run_store.push_event(
            run_id, "complete",
            f"Done! {n} slides generated.",
            100,
            {"slides": results, "caption": caption, "topic": topic},
        )
        db.save_run(run_id, "carousel", "complete", topic=topic,
                    result={
                        "topic": topic,
                        "slides": results,
                        "caption": caption,
                        "caption_original": caption_original,  # pre-stop-slop version
                        "stop_slop_applied": slop_result["changed"],
                        "stop_slop_error": slop_result.get("error"),
                        "web_research": web_research,
                        "avoid_list": recent,
                    })

    except Exception as e:
        run_store.fail_run(run_id, str(e))
        await run_store.push_event(run_id, "error", str(e), 0)
        db.save_run(run_id, "carousel", "failed", error=str(e))
        raise


def _build_slides(data: dict, inspiration: int) -> list[dict]:
    slides = []
    items = data["items"]
    n_inner = len(items)

    if inspiration == 7:
        # Cinematic single-destination with yellow accent + bottom-anchored text
        n_inner = len(items)
        # Build headline from cover headlines (extract a key word for yellow highlight)
        headline_1 = data.get("cover_headline_1", "TOP DESTINATIONS")
        headline_2 = data.get("cover_headline_2", "TO VISIT IN 2026")
        # Default highlight word = first non-trivial word from headline_2 OR a chunk of theme
        highlight_word = (data.get("cover_headline_3") or
                          (data.get("theme", "INDIA").split()[0] if data.get("theme") else "INDIA")).upper()
        slides.append({
            "label": "Cover",
            "filename": "slide-00-cover.png",
            "prompt": ig.insp7_cover_prompt({
                "headline_line_1": headline_1,
                "headline_line_2": headline_2,
                "highlight_word": highlight_word,
                "photo_direction": items[0].get("photo_direction", "iconic cinematic travel destination at dusk"),
            }),
        })
        for item in items:
            idx = item["index"]
            name = item["name_line_1"].lower().replace(" ", "-")
            slides.append({
                "label": item["name_line_1"],
                "filename": f"slide-{idx:02d}-{name}.png",
                "prompt": ig.insp7_inner_prompt({
                    "destination_name": item["name_line_1"],
                    "descriptor": item.get("descriptor") or item.get("descriptor_1") or "",
                    "photo_direction": item.get("photo_direction", ""),
                    "slide_counter": f"{idx + 1}/{n_inner + 2}",
                }),
            })
        slides.append({
            "label": "CTA",
            "filename": f"slide-{n_inner + 1:02d}-cta.png",
            "prompt": ig.insp7_cta_prompt({
                "hook_line_1": "BOOK YOUR DREAM",
                "hook_line_2": "TRIP TODAY",
                "highlight_word": "TODAY",
                "save_prompt": data["cta"].get("descriptor", "DM us to plan your trip"),
                "contact_phone": os.environ.get("DWT_WHATSAPP", "+91 93226 08068"),
                "photo_direction": data["cta"]["photo_direction"],
            }),
        })

    elif inspiration == 6:
        # Split-screen paired format — 2 destinations per slide
        slides.append({
            "label": "Cover",
            "filename": "slide-00-cover.png",
            "prompt": ig.insp6_cover_prompt({
                "headline_line_1": data.get("cover_headline_1", "2026 IS CALLING"),
                "headline_line_2": data.get("cover_headline_2", "WHERE WILL YOU GO?"),
                "headline_line_3": data.get("cover_headline_3", ""),
                "subtitle": data.get("cover_subhead", "Save this for later"),
                "photo_direction": items[0].get("photo_direction", "iconic global travel destination at golden hour"),
            }),
        })
        # Pair items 2-by-2
        pairs = [(items[i], items[i+1]) for i in range(0, len(items)-1, 2)]
        n_paired = len(pairs)
        for pair_idx, (top, bot) in enumerate(pairs, 1):
            counter_str = f"{pair_idx + 1}/{n_paired + 2}"  # +2 for cover & CTA
            slug = f"{top['name_line_1']}-{bot['name_line_1']}".lower().replace(" ", "-")[:40]
            slides.append({
                "label": f"{top['name_line_1']} + {bot['name_line_1']}",
                "filename": f"slide-{pair_idx:02d}-{slug}.png",
                "prompt": ig.insp6_paired_inner_prompt({
                    "top_country": top["name_line_1"],
                    "top_place": top.get("city_state") or top.get("descriptor", "Iconic Sight"),
                    "top_photo": top.get("photo_direction", ""),
                    "bottom_country": bot["name_line_1"],
                    "bottom_place": bot.get("city_state") or bot.get("descriptor", "Iconic Sight"),
                    "bottom_photo": bot.get("photo_direction", ""),
                    "slide_counter": counter_str,
                }),
            })
        # CTA slide
        slides.append({
            "label": "CTA",
            "filename": f"slide-{n_paired + 1:02d}-cta.png",
            "prompt": ig.insp6_cta_prompt({
                "hook_line_1": "DON'T WAIT",
                "hook_line_2": "AND BOOK YOUR",
                "hook_line_3": "HOLIDAY PACKAGE TODAY",
                "contact_phone": os.environ.get("DWT_WHATSAPP", "+91 93226 08068"),
                "photo_direction": data["cta"]["photo_direction"],
            }),
        })

    elif inspiration == 5:
        slides.append({
            "label": "Cover",
            "filename": "slide-00-cover.png",
            "prompt": ig.insp5_cover_prompt(data),
        })
        for item in items:
            idx = item["index"]
            name = item["name_line_1"].lower().replace(" ", "-")
            slides.append({
                "label": item["name_line_1"],
                "filename": f"slide-{idx:02d}-{name}.png",
                "prompt": ig.insp5_inner_prompt({
                    **item,
                    "slide_counter": f"{idx:02d} / {n_inner:02d}",
                }),
            })
        slides.append({
            "label": "CTA",
            "filename": f"slide-{n_inner + 1:02d}-cta.png",
            "prompt": ig.insp5_cta_prompt(data["cta"]),
        })

    else:
        cover_photo = f"aerial/scenic view representing {data['theme']}"
        slides.append({
            "label": "Cover",
            "filename": "slide-00-cover.png",
            "prompt": ig.insp4_cover_prompt({
                "headline_line_1": data["cover_headline_1"],
                "headline_line_2": data["cover_headline_2"],
                "headline_line_3": data.get("cover_headline_3", ""),
                "subtitle": data.get("cover_subhead", ""),
                "bottom_left": f"Swipe to discover all {n_inner} →",
                "photo_direction": cover_photo,
            }),
        })
        for item in items:
            idx = item["index"]
            name = item["name_line_1"].lower().replace(" ", "-")
            slides.append({
                "label": item["name_line_1"],
                "filename": f"slide-{idx:02d}-{name}.png",
                "prompt": ig.insp4_inner_prompt({
                    **item,
                    "location_line_1": item["name_line_1"],
                    "location_line_2": item.get("name_line_2", ""),
                    "descriptor_1": item.get("descriptor", item.get("descriptor_1", "")),
                    "descriptor_2": item.get("descriptor_2", ""),
                    "slide_counter": f"{idx:02d} / {n_inner:02d}",
                }),
            })
        col1 = [f"○ {it['name_line_1']}" for it in items[:4]]
        col2 = [f"○ {it['name_line_1']}" for it in items[4:]]
        slides.append({
            "label": "CTA",
            "filename": f"slide-{n_inner + 1:02d}-cta.png",
            "prompt": ig.insp4_cta_prompt({
                "question_line_1": data["cta"]["name_line_1"],
                "question_line_2": data["cta"]["name_line_2"],
                "save_prompt": data["cta"]["descriptor"],
                "items_col_1": col1,
                "items_col_2": col2,
                "cta_button": "DM us to plan your trip →",
                "photo_direction": data["cta"]["photo_direction"],
            }),
        })

    return slides


def _build_caption(data: dict) -> str:
    destinations = ", ".join(
        it["name_line_1"] + (" " + it["name_line_2"] if it.get("name_line_2") else "")
        for it in data["items"][:4]
    )
    keyword = data["cta"].get("descriptor", "").split("'")[1] if "'" in data["cta"].get("descriptor", "") else "TRIP"
    return f"""{data['items'][0]['name_line_1'].title()}, {data['items'][1]['name_line_1'].title()}, {data['items'][2]['name_line_1'].title()} and more — {data['season_label'].lower()} travel sorted.

{len(data['items'])} destinations your group will actually love. From {destinations} — all handpicked by @dreamworldtours so you don't have to figure a thing out.

Save this + DM us '{keyword}' to start planning.

#DreamWorldTours #IndianTravellers #TravelIndia #GroupTravel #{data['season_label'].replace(' ', '').replace('·', '').title()} #TravelPackages #HolidayPlanning #TravelInspiration #Wanderlust #TravelGoals #InstaTravel #ExploreIndia #TravelLife #BucketList #WeekendGetaway #TravelBlogger #HolidayMode #TravelWithFriends #FamilyVacation #TravelPhotography #IndiaTravel #TravelDiaries #IncredibleIndia #TravelAddict #TourPackages #TravelAgency #VisitIndia #TravelMore"""
