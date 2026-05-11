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
import asyncio
import shutil
from datetime import date
from pathlib import Path

from services import run_store, researcher, image_generator as ig

OUTPUTS_DIR = Path(__file__).parent.parent / "outputs" / "carousel"
BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000")
WORKSPACE_ROOT = Path(__file__).parent.parent.parent
USE_AGENTS = os.environ.get("USE_AGENTS", "false").lower() == "true"


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

    # Find claude executable
    import shutil as sh
    claude_bin = sh.which("claude")
    if not claude_bin:
        run_store.fail_run(run_id, "claude CLI not found. Install Claude Code: npm install -g @anthropic-ai/claude-code")
        await run_store.push_event(run_id, "error", "claude CLI not found", 0)
        return

    cmd = [claude_bin, "-p", prompt, "--output-format", "stream-json"]

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
        url = f"{BASE_URL}/outputs/carousel/{run_id}/{png.name}"
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


# ── MODE B — Standalone Python Pipeline ───────────────────────────────────────

async def _run_standalone(run_id: str, inspiration: int, topic_hint: str = None):
    run_store.update_run(run_id, status="running")

    try:
        await run_store.push_event(run_id, "researching", "Finding the best topic for today...", 5)

        recent = [r["topic"] for r in run_store.get_all_runs()
                  if r.get("topic") and r["run_id"] != run_id][:5]

        data = await researcher.research_topic(
            date=date.today().isoformat(),
            avoid_topics=recent,
            topic_hint=topic_hint,
        )

        topic = data["theme"]
        run_store.update_run(run_id, topic=topic)
        await run_store.push_event(run_id, "researching", f"Topic: {topic}", 15, {"topic": topic})

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
            url = f"{BASE_URL}/outputs/carousel/{run_id}/{filename}"
            results.append({"index": i, "filename": filename, "url": url})

        await run_store.push_event(run_id, "generating_slides", "Writing Instagram caption...", 93)
        caption = _build_caption(data)
        (out_dir / "caption.txt").write_text(caption)

        run_store.complete_run(run_id, topic=topic, slides=results, caption=caption)
        await run_store.push_event(
            run_id, "complete",
            f"Done! {n} slides generated.",
            100,
            {"slides": results, "caption": caption, "topic": topic},
        )

    except Exception as e:
        run_store.fail_run(run_id, str(e))
        await run_store.push_event(run_id, "error", str(e), 0)
        raise


def _build_slides(data: dict, inspiration: int) -> list[dict]:
    slides = []
    items = data["items"]
    n_inner = len(items)

    if inspiration == 5:
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
