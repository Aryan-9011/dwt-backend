# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## What This Is

This is a **Claude Workspace Template** — a structured environment designed for working with Claude Code as a powerful agent assistant across sessions. The user will spin up fresh Claude Code sessions repeatedly, using `/prime` at the start of each to load essential context without bloat.

**This file (CLAUDE.md) is the foundation.** It is automatically loaded at the start of every session. Keep it current — it is the single source of truth for how Claude should understand and operate within this workspace.

---

## The Claude-User Relationship

Claude operates as an **agent assistant** with access to the workspace folders, context files, commands, and outputs. The relationship is:

- **User**: Defines goals, provides context about their role/function, and directs work through commands
- **Claude**: Reads context, understands the user's objectives, executes commands, produces outputs, and maintains workspace consistency

Claude should always orient itself through `/prime` at session start, then act with full awareness of who the user is, what they're trying to achieve, and how this workspace supports that.

---

## Workspace Structure

```
.
├── CLAUDE.md              # This file — core context, always loaded
├── .claude/
│   ├── commands/          # Slash commands Claude can execute
│   │   ├── prime.md       # /prime — session initialization
│   │   ├── create-plan.md  # /create-plan — create implementation plans
│   │   ├── implement.md   # /implement — execute plans
│   │   └── create-content.md  # /create-content — generate on-brand content
│   └── agents/            # Specialist subagents (manager + team architecture)
│       ├── content-idea-orchestrator.md  # MANAGER — runs full pipeline 4x/week, delegates to subagents
│       ├── itinerary-reader.md           # Reads PDFs → returns real pricing/dates JSON
│       ├── trend-analyst.md              # Web research → returns angles/pain points JSON
│       ├── content-ideas-writer.md       # Writes 7 high-quality ideas (opus model)
│       ├── sheets-publisher.md           # Writes rows to Google Sheets (haiku model)
│       ├── creative-designer.md          # Generates carousel slides + hero visual (nano-banana)
│       ├── campaign-strategist.md        # Full campaign strategy and brief
│       ├── market-researcher.md          # Competitor and market research
│       ├── paid-ads-specialist.md        # Facebook/Instagram ad copy
│       ├── reel-pipeline-manager.md      # MANAGER — orchestrates full reel pipeline (4 subagents) → saves to "Reel Ideas" tab
│       ├── reel-ideator.md               # Generates 5 hook concepts only (no scripts)
│       ├── reel-scripter.md              # Writes complete shot-by-shot scripts for all concepts
│       ├── marketing-post-manager.md     # MANAGER — orchestrates WhatsApp marketing post pipeline → saves to "Marketing Posts" tab
│       ├── marketing-post-ideator.md     # Generates 4 post concepts (Offer Blast, Urgency, Social Proof, etc.)
│       ├── marketing-post-designer.md    # Designs single-image WhatsApp posts (nano-banana), distinct style per post
│       ├── design-analyzer.md            # Reads any poster/design image → auto-generates inspiration-N.md in the inspiration library
│       ├── post-performance-analyzer.md  # Reads past post images + optional metrics → performance insights + recommendations
│       ├── itinerary-image-extractor.md  # Reads scanned/image-based itineraries → returns same JSON as itinerary-reader
│       ├── carousel-auto-pipeline-manager.md  # MANAGER — automated carousel pipeline 3x/week (Mon/Wed/Fri) → research → design → Instagram post
│       ├── travel-article-researcher.md  # Finds trending travel articles → extracts structured carousel content JSON
│       ├── carousel-content-writer.md    # Writes slide-by-slide Inspiration 4 brief + Instagram caption from article JSON
│       └── instagram-publisher.md        # Uploads slides to imgbb → posts carousel via Instagram Graph API
├── context/               # Background context about the user and project
│                          # (User should populate with role, goals, strategies)
├── plans/                 # Implementation plans created by /create-plan
├── outputs/               # Work products and deliverables
├── reference/             # Content strategy system and reusable frameworks
│   ├── brand-reference.md            # GROUND TRUTH — real pricing, itineraries, testimonials, brand colors, design style. Read first before any content creation.
│   ├── content-strategy-master.md    # Brand voice, 6 pillars, seasonal calendar, differentiation angles
│   ├── platform-frameworks.md        # Per-platform formats, frequencies, do/don't rules
│   ├── hook-cta-library.md           # Reusable hooks, headlines, CTAs, urgency triggers, caption formulas
│   ├── content-repurposing-workflow.md  # 1-seed-to-12-pieces repurposing system
│   ├── marathi-script-process.md     # Marathi reel scripts in English letters — phonetics, phrases, templates
│   ├── seo-blog-framework.md         # SEO blog creation process, title formulas, keyword strategy
│   ├── funnel-content-guide.md       # Content types and objectives by funnel stage (Awareness → Referral)
│   ├── itineraries/                  # PDF itineraries for all DWT packages (Vietnam, Dubai, Kashmir, Bali, Thailand, etc.)
│   └── brand-design/                 # Brand assets: logo, brand style guide, inspiration images (Polaroid/scrapbook aesthetic)
├── scripts/
│   ├── sheets_writer.py   # Multi-tab Google Sheets writer — supports --sheet-name flag for 3 tabs:
│   │                      #   "Content Calendar" (content pipeline), "Reel Ideas" (reel pipeline), "Marketing Posts" (marketing pipeline)
│   ├── image_uploader.py  # Uploads local PNG/JPG images to imgbb → returns public URLs (required for Instagram Graph API)
│   └── instagram_poster.py  # Posts carousel or single image to Instagram via Graph API. Requires INSTAGRAM_ACCESS_TOKEN + INSTAGRAM_BUSINESS_ACCOUNT_ID
├── credentials/
│   ├── google-sheets-credentials.json  # Service account key — DO NOT commit to git
│   ├── .env               # API keys: IMGBB_API_KEY, INSTAGRAM_ACCESS_TOKEN, INSTAGRAM_BUSINESS_ACCOUNT_ID — DO NOT commit to git
│   └── .env.template      # Safe template to copy → credentials/.env (no real keys)
├── reference/
│   └── instagram-api-setup.md  # Step-by-step guide: Facebook app setup, token generation, account ID lookup
└── outputs/
    ├── automation/                     # Pipeline logs + all carousel-auto-pipeline runs
    │   ├── pipeline-log.jsonl          # One line per pipeline run (start/complete/failed)
    │   ├── publish-log.jsonl           # One line per Instagram post attempt (post_id + permalink)
    │   └── carousel-pipeline/         # Per-run artifacts: article JSON, brief JSON, caption, slide PNGs
    ├── content/
    │   └── performance-analysis/      # Post performance reports from post-performance-analyzer
    └── data/
        └── itineraries/               # Extracted JSON + summaries from itinerary-image-extractor
```

**Key directories:**

| Directory    | Purpose                                                                             |
| ------------ | ----------------------------------------------------------------------------------- |
| `context/`   | Who the user is, their role, current priorities, strategies. Read by `/prime`.      |
| `plans/`     | Detailed implementation plans. Created by `/create-plan`, executed by `/implement`. |
| `outputs/`   | Deliverables, analyses, reports, and work products.                                 |
| `reference/` | DWT content system — `brand-reference.md` (ground truth for pricing/itineraries/brand style), content strategy, platform frameworks, hook/CTA library, repurposing workflow, Marathi scripts, SEO framework, funnel guide. Also contains `itineraries/` (PDFs) and `brand-design/` (logo, style guide, inspiration images). |
| `scripts/`   | Any automation or tooling scripts.                                                  |

---

## Commands

### /prime

**Purpose:** Initialize a new session with full context awareness.

Run this at the start of every session. Claude will:

1. Read CLAUDE.md and context files
2. Summarize understanding of the user, workspace, and goals
3. Confirm readiness to assist

### /create-plan [request]

**Purpose:** Create a detailed implementation plan before making changes.

Use when adding new functionality, commands, scripts, or making structural changes. Produces a thorough plan document in `plans/` that captures context, rationale, and step-by-step tasks.

Example: `/create-plan add a competitor analysis command`

### /implement [plan-path]

**Purpose:** Execute a plan created by /create-plan.

Reads the plan, executes each step in order, validates the work, and updates the plan status.

Example: `/implement plans/2026-01-28-competitor-analysis-command.md`

### /create-content [platform] [destination] [optional: topic/angle] [optional: funnel-stage]

**Purpose:** Generate premium, on-brand content for Dream World Tours for any platform or format.

Reads all content strategy reference files and produces polished, conversion-focused content. Always outputs minimum 3 variations with CTA options.

**Supported platforms:**
`instagram-reel` · `instagram-carousel` · `facebook-ad` · `facebook-lead-ad` · `whatsapp` · `linkedin` · `blog` · `landing-page` · `email` · `video-script` · `marathi-reel` · `caption` · `hooks-and-ctas` · `repurpose`

**Examples:**
- `/create-content instagram-reel Vietnam awareness`
- `/create-content facebook-ad Dubai "family trip" conversion`
- `/create-content marathi-reel Kashmir "summer group departure"`
- `/create-content blog Vietnam "8 days itinerary"`
- `/create-content repurpose Maldives "May honeymoon departure"`

---

## Critical Instruction: Maintain This File

**Whenever Claude makes changes to the workspace, Claude MUST consider whether CLAUDE.md needs updating.**

After any change — adding commands, scripts, workflows, or modifying structure — ask:

1. Does this change add new functionality users need to know about?
2. Does it modify the workspace structure documented above?
3. Should a new command be listed?
4. Does context/ need new files to capture this?

If yes to any, update the relevant sections. This file must always reflect the current state of the workspace so future sessions have accurate context.

**Examples of changes requiring CLAUDE.md updates:**

- Adding a new slash command → add to Commands section
- Creating a new output type → document in Workspace Structure or create a section
- Adding a script → document its purpose and usage
- Changing workflow patterns → update relevant documentation

---

## For Users Downloading This Template

To customize this workspace to your own needs, fill in your context documents in `context/` and modify as needed. Then use `/create-plan` to plan out and `/implement` to execute any structural changes. This ensures everything stays in sync — especially CLAUDE.md, which must always reflect the current state of the workspace.

---

## Session Workflow

1. **Start**: Run `/prime` to load context
2. **Work**: Use commands or direct Claude with tasks
3. **Plan changes**: Use `/create-plan` before significant additions
4. **Execute**: Use `/implement` to execute plans
5. **Maintain**: Claude updates CLAUDE.md and context/ as the workspace evolves

---

## Notes

- Keep context minimal but sufficient — avoid bloat
- Plans live in `plans/` with dated filenames for history
- Outputs are organized by type/purpose in `outputs/`
- Reference materials go in `reference/` for reuse
