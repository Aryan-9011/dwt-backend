# Design Inspiration 4 — Editorial Carousel (Cinematic Photo + Bottom Gradient)

**Style name:** Cinematic Editorial Carousel
**Best for:** Educational/awareness carousels — "8 best X", "7 top Y", listicle-style Instagram carousels. Not a product/offer post — pure value content.
**Reference output:** `outputs/content/carousels/india-beaches-09may/`
**Format:** Portrait 1080×1350px (Instagram standard)

---

## Design Philosophy

Photo-first, editorial, sophisticated. Feels like a Condé Nast Traveller or National Geographic digital carousel.
- The destination photo IS the slide — full-bleed, vivid, no clutter
- Minimal text overlay — only what's essential, nothing decorative
- Bottom gradient keeps text legible without hiding the photo
- Consistent slide counter (01/08) gives the carousel a premium editorial feel
- Three slide types: Cover → Inner (repeatable template) → CTA — all follow the same visual language
- White and teal only — clean, no badge colors, no amber, no red

---

## Three Slide Templates

---

### TEMPLATE 1 — Cover Slide

**Background:** Full-bleed cinematic aerial/scenic photo of the topic destination. Vivid, rich colors.

**Overlay:** Dark gradient covers the TOP 55% of the image — heavier at very top, fading to transparent toward the bottom half. The scenic photo breathes clearly in the lower half.

**Layout — all text LEFT-ALIGNED:**

```
@dreamworldtours                    [top-left, very small, light white]

[TOPIC LINE 1]                      [very large bold condensed white — e.g. "8 CLEANEST"]
[TOPIC LINE 2]                      [very large bold condensed white — e.g. "BEACHES"]
[TOPIC LINE 3]                      [very large bold condensed white — e.g. "IN INDIA"]

───────────                         [teal #00a8a8 horizontal rule, 3px, 80px wide]

[Subtitle — one line description]   [small regular white, elegant]


[bottom-left: "Swipe to discover all X →"]   [bottom-right: "Dream World Tours"]
[both in small light white]
```

---

### TEMPLATE 2 — Inner Slide (Repeatable for each item)

**Background:** Full-bleed cinematic photo specific to that location/item. Different scene every slide — variety is key.

**Overlay:** Subtle dark gradient on BOTTOM 35% ONLY — transparent at top, semi-dark at bottom. The top 65% of the photo is fully visible with no overlay.

**Layout:**

```
@dreamworldtours        [top-left, very small, light white]       XX / YY [top-right, small clean white]




[LOCATION NAME LINE 1]   [very large bold condensed white, left-aligned — e.g. "RADHANAGAR"]
[LOCATION NAME LINE 2]   [very large bold condensed white — e.g. "BEACH"]
[City, State]            [small teal #00a8a8, light weight]
────────                 [teal rule 3px, 60px wide]
[Descriptor line 1]      [small regular white]
[Descriptor line 2]      [small regular white]
```

**Critical rules for inner slides:**
- Split the location name across 2 lines if it fits better (e.g. "RADHANAGAR" / "BEACH" — NOT "RADHANAGAR BEACH" on one line)
- Slide counter format: "01 / 08", "02 / 08" etc.
- NO boxes, NO panels, NO badges around any text
- Descriptor lines: max 55 characters each — short, punchy, factual

---

### TEMPLATE 3 — CTA / Final Slide

**Background:** Full-bleed cinematic beach/destination photo. Vivid and dreamy.

**Overlay:** Dark gradient covers TOP 60% — heavier at top, fading to lighter at bottom so the scenery shows in the lower half.

**Layout:**

```
@dreamworldtours         [top-left, very small light white]

[ENGAGEMENT HEADLINE]    [large bold white — e.g. "WHICH BEACH"]
[LINE 2]                 [large bold white — e.g. "IS CALLING YOU?"]

────────────             [teal rule 3px, 80px wide]

[Save/share prompt]      [small regular white]

○ Item 1 — Location      ○ Item 5 — Location
○ Item 2 — Location      ○ Item 6 — Location      [2-column list, all items]
○ Item 3 — Location      ○ Item 7 — Location
○ Item 4 — Location      ○ Item 8 — Location

[Solid teal #00a8a8 wide pill CTA button centered — white bold text: "DM us to plan your trip →"]

[dreamworldtours.in  |  Dream World Tours — small white centered]
```

---

## Color System

| Element | Color | Style |
|---------|-------|-------|
| All headlines | White `#ffffff` | Bold condensed sans-serif |
| Location subtitle | Teal `#00a8a8` | Light weight, small |
| Accent rule | Teal `#00a8a8` | 3px horizontal line |
| Descriptor text | White `#ffffff` | Regular weight, small |
| Slide counter | White `#ffffff` | Light weight, small |
| CTA button | Solid teal `#00a8a8` | White bold text inside pill |
| @handle | White `#ffffff` | Very small, light weight |

---

## Typography Rules

- **Headlines (location name, cover title):** Very large bold CONDENSED white sans-serif — fills the space, dominant
- **Location subtitle (City, State):** Small teal, light weight — creates hierarchy below the big name
- **Descriptors:** Small regular white — NOT bold, NOT condensed — just readable
- **Slide counter:** Small regular white — unobtrusive
- **Nothing should be ultra-heavy except the main location name/headline**

---

## Photo Direction Per Slide

Each inner slide needs a DIFFERENT scene for visual variety:
- Mix aerial shots with ground-level shots
- Mix golden hour with bright daylight with blue hour
- Mix wide establishing shots with intimate close scenes
- No two slides should feel visually similar

---

## What NOT to Do

- NO info panel / white box behind text — text sits directly on gradient
- NO badges, NO price boxes, NO amber elements (this is not a product post)
- NO centered text — everything LEFT-ALIGNED
- NO same photo angle/mood repeated across multiple slides
- NO heavy text overlay covering the photo — gradient bottom only
- NO multiple colors — white and teal only throughout
- NO slide counter on cover or CTA slides — only on inner slides
- NO cluttered slide with more than 2 descriptor lines

---

## Nano Banana Prompt Patterns

### Cover Slide
```
Portrait 1080×1350px Instagram carousel cover slide. Premium sophisticated editorial design.

BACKGROUND: Full-bleed cinematic [AERIAL/SCENIC DESCRIPTION of topic]. Vivid, rich colors, magazine-quality.

OVERLAY: Dark gradient covers TOP 55% — heavier at top, fading to transparent toward lower half. Lower half of photo fully visible.

TOP-LEFT: "@dreamworldtours" very small light white

HEADLINE — left-aligned, very large bold condensed white sans-serif, stacked:
"[TOPIC LINE 1]"
"[TOPIC LINE 2]"
"[TOPIC LINE 3]"

Below headline: teal #00a8a8 horizontal rule 3px, 80px wide

Below rule: "[Subtitle — one elegant line]" small regular white, left-aligned

Bottom-left: "Swipe to discover all [N] →" small light white
Bottom-right: "Dream World Tours" small clean white

NO boxes, NO badges, NO borders. Clean editorial. Portrait 1080×1350px. High-fidelity text. Professional quality.
```

### Inner Slide
```
Portrait 1080×1350px Instagram carousel inner slide. Sophisticated editorial travel design.

BACKGROUND: Full-bleed cinematic [SPECIFIC SCENE DESCRIPTION — aerial/ground, time of day, key visual elements]. Vivid rich colors.

OVERLAY: Subtle dark gradient BOTTOM 35% ONLY — transparent at top, semi-dark at bottom.

TOP-LEFT: "@dreamworldtours" very small light white
TOP-RIGHT: "[XX] / [YY]" small clean white light weight

BOTTOM-LEFT text block:
- "[LOCATION NAME LINE 1]" — very large bold condensed white, left-aligned
- "[LOCATION NAME LINE 2]" — same very large bold, second line
- "[City, State/Region]" — small teal #00a8a8, light weight
- Short teal rule 3px, 60px
- "[Descriptor fact 1 — max 55 chars]" — small regular white
- "[Descriptor fact 2 — max 55 chars]" — small regular white

NO boxes, NO panels, NO badges. Text directly on gradient. Editorial clean. Portrait 1080×1350px. High-fidelity text. Professional quality.
```

### CTA Slide
```
Portrait 1080×1350px Instagram carousel final CTA slide. Sophisticated editorial travel design.

BACKGROUND: Full-bleed cinematic [SCENIC DESCRIPTION]. Vivid and dreamy.

OVERLAY: Dark gradient covers TOP 60% — heavier at top, lighter toward bottom. Scenery visible in lower half.

TOP-LEFT: "@dreamworldtours" very small light white

HEADLINE left-aligned, large bold white:
"[ENGAGEMENT QUESTION LINE 1]"
"[ENGAGEMENT QUESTION LINE 2]"

Below: teal #00a8a8 rule 3px, 80px wide

Below rule: "[Save/share prompt]" small regular white

2-COLUMN LIST in small regular white (circle bullets):
Left column: ○ [Item 1] — [Location] / ○ [Item 2] — [Location] / ○ [Item 3] / ○ [Item 4]
Right column: ○ [Item 5] — [Location] / ○ [Item 6] / ○ [Item 7] / ○ [Item 8]

SOLID TEAL #00a8a8 wide pill button centered: "[CTA text →]" bold white

Below button: "[dreamworldtours.in  |  Dream World Tours]" small white centered

NO boxes around text. Editorial clean. Portrait 1080×1350px. High-fidelity text. Professional quality.
```
