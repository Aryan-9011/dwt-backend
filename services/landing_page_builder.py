"""
Landing Page Builder — Agent that generates production-ready HTML landing pages
for Dream World Tours from structured YAML briefs.

Supported page types (dispatched by brief['type']):
- comparison   → /alternatives/[competitor]   (Veena, Kesari, Miracle, etc.)
- tour-launch  → /tours/[campaign-slug]       (Single departure with urgency: "Vietnam Sep 2026")
- destination  → /destinations/[place]        (Evergreen: all Kashmir packages, all Vietnam packages)
- audience     → /tours-for/[segment]         (Family, Honeymoon, Religious, Senior, First-International)

All pages share:
- Validated design spec from ui-ux-pro-max (Travel/Tourism palette, Lexend + Source Sans 3)
- DWT positioning from product-marketing.md
- FAQ schema.org JSON-LD
- WCAG accessibility (single H1, focus rings, semantic HTML, prefers-reduced-motion)
- Mobile-first responsive design with sticky CTA bar
"""
import json
from datetime import datetime
from pathlib import Path

# ── Design spec (validated via ui-ux-pro-max skill) ───────────────────────────

DESIGN_SPEC = {
    "colors": {
        "dwt_teal": "#0c6980",
        "dwt_teal_dark": "#0a5468",
        "dwt_amber": "#f5c518",
        "dwt_orange": "#EA580C",   # WCAG-safe CTA orange
        "dwt_bg": "#F0F9FF",
        "dwt_card": "#FFFFFF",
        "dwt_text": "#0C4A6E",
        "dwt_muted": "#64748B",
        "dwt_border": "#BAE6FD",
    },
    "fonts": {
        "google_url": "https://fonts.googleapis.com/css2?family=Lexend:wght@400;500;600;700&family=Source+Sans+3:wght@400;500;600;700&display=swap",
    },
}

# Curated high-quality Unsplash photo IDs by destination/theme.
# These photos are free for commercial use under the Unsplash License.
# Format: photo-[ID] → resolved to https://images.unsplash.com/photo-[ID]?w=1600&q=80
DESTINATION_IMAGES = {
    "vietnam":           "photo-1528127269322-539801943592",  # Halong Bay
    "kashmir":           "photo-1566305977571-5666677c6e98",  # Dal Lake Srinagar
    "ladakh":            "photo-1626621341517-bbf3d9990a23",  # Pangong Lake
    "leh-ladakh":        "photo-1626621341517-bbf3d9990a23",  # Pangong Lake
    "bhutan":            "photo-1571401835393-8c5f35328320",  # Tiger's Nest
    "thailand":          "photo-1552465011-b4e21bf6e79a",     # Phi Phi Islands
    "dubai":             "photo-1518684079-3c830dcef090",     # Dubai skyline
    "singapore":         "photo-1565967511849-76a60a516170",  # Marina Bay
    "malaysia":          "photo-1596422846543-75c6fc197f07",  # Petronas Towers
    "kerala":            "photo-1602216056096-3b40cc0c9944",  # Alleppey backwaters
    "sikkim":            "photo-1626621341517-bbf3d9990a23",  # Himalayan view
    "northeast":         "photo-1597211833712-5e41faa202ea",  # Living root bridge
    "bali":              "photo-1537953773345-d172ccf13cf1",  # Bali rice terraces
    "maldives":          "photo-1514282401047-d79a71a590e8",  # Maldives water villa
    "kenya":             "photo-1516026672322-bc52d61a55d5",  # Masai Mara sunset
    "amarnath":          "photo-1567157577867-05ccb1388e66",  # Kashmir mountains
    "europe":            "photo-1499856871958-5b9627545d1a",  # Generic Europe
    "default":           "photo-1488646953014-85cb44e25828",  # World map / travel
    "family":            "photo-1542038784456-1ea8e935640e",  # Family travel scene
    "honeymoon":         "photo-1601000938259-9e92002320b2",  # Romantic couple
    "comparison":        "photo-1488085061387-422e29b40080",  # Decision-making
}


def _img_url(key: str, width: int = 1600) -> str:
    """Return an Unsplash image URL for a destination/theme key. Falls back to default."""
    k = (key or "").lower().strip()
    # Try exact match, then partial match, then default
    if k in DESTINATION_IMAGES:
        photo_id = DESTINATION_IMAGES[k]
    else:
        # Try fuzzy match
        photo_id = next((v for kw, v in DESTINATION_IMAGES.items() if kw in k or k in kw), DESTINATION_IMAGES["default"])
    return f"https://images.unsplash.com/{photo_id}?w={width}&q=80&auto=format&fit=crop"

# DWT facts from product-marketing.md
DWT_FACTS = {
    "name": "Dream World Tours",
    "phone": "+91 73682 60990",
    "whatsapp": "919322608068",
    "whatsapp_display": "+91 93226 08068",
    "address": "Walhekar Properties, 3rd Floor, Office No. 305, Nanded City, Sinhgad Road, Pune 411041",
    "office_short": "Nanded City, Sinhgad Road, Pune",
    "website": "dreamworldtours.in",
    "instagram": "@dreamworldtours_",
    "instagram_url": "https://instagram.com/dreamworldtours_",
    "google_review_link": "https://g.page/dreamworldtours",
    "maps_link": "https://maps.app.goo.gl/dreamworldtours",
    "stats": {
        "travellers": "25,000+",
        "reviews_count": "700+",
        "rating": "4.9",
        "years": "10",
    },
}


# ── Shared helpers ────────────────────────────────────────────────────────────

def _load_brief(path):
    p = Path(path)
    text = p.read_text()
    if p.suffix == ".json":
        return json.loads(text)
    try:
        import yaml
        return yaml.safe_load(text)
    except ImportError:
        raise ImportError("PyYAML not installed. Run: pip3 install pyyaml")


def _faq_schema_json(faqs):
    entities = [{
        "@type": "Question",
        "name": faq["question"],
        "acceptedAnswer": {"@type": "Answer", "text": faq["answer"]},
    } for faq in faqs]
    return json.dumps({"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": entities}, indent=2)


def _faqs_html(faqs):
    return "\n".join(f'''        <details class="bg-white p-6 rounded-lg border border-dwt-border group">
          <summary class="font-semibold text-dwt-text cursor-pointer flex justify-between items-center">{faq["question"]} <span class="text-dwt-orange group-open:rotate-180 transition-transform">▼</span></summary>
          <p class="mt-3 text-dwt-muted">{faq["answer"]}</p>
        </details>''' for faq in faqs)


def _testimonials_html(testimonials):
    return "\n".join(f'''        <blockquote class="bg-dwt-bg p-6 rounded-lg border-l-4 border-dwt-orange">
          <p class="text-dwt-text mb-3">"{t["quote"]}"</p>
          <footer class="text-sm text-dwt-muted">— {t["author"]}</footer>
        </blockquote>''' for t in testimonials)


def _li_check(items, color="dwt-orange"):
    return "\n".join(f'''          <li class="flex gap-3"><span class="text-{color} font-bold">✓</span><span>{i}</span></li>''' for i in items)


def _navbar():
    return f'''  <nav class="bg-white border-b border-dwt-border" aria-label="Main navigation">
    <div class="max-w-6xl mx-auto px-4 py-4 flex items-center justify-between">
      <a href="/" class="flex items-center gap-2" aria-label="{DWT_FACTS['name']} homepage">
        <span class="font-heading font-bold text-xl text-dwt-teal">{DWT_FACTS['name']}</span>
      </a>
      <div class="hidden md:flex items-center gap-6 text-sm">
        <a href="/packages" class="hover:text-dwt-teal">Packages</a>
        <a href="/about" class="hover:text-dwt-teal">About</a>
        <a href="/reviews" class="hover:text-dwt-teal">Reviews</a>
        <a href="https://wa.me/{DWT_FACTS['whatsapp']}" class="bg-dwt-orange text-white px-4 py-2 rounded-md font-semibold hover:bg-orange-700 transition-colors">WhatsApp Us</a>
      </div>
    </div>
  </nav>'''


def _sticky_mobile_cta(label="WhatsApp Us to Plan Your Trip"):
    return f'''  <div class="sticky top-0 z-50 bg-dwt-teal text-white shadow-md md:hidden">
    <a href="https://wa.me/{DWT_FACTS['whatsapp']}" class="block py-3 text-center font-semibold" aria-label="{label}">
      💬 {label} →
    </a>
  </div>'''


def _footer():
    return f'''  <footer class="bg-dwt-text text-blue-100 py-8 text-sm">
    <div class="max-w-6xl mx-auto px-4 text-center">
      <p class="mb-2">{DWT_FACTS['name']} Private Limited</p>
      <p class="text-xs">{DWT_FACTS['address']}</p>
      <p class="text-xs mt-1">📞 {DWT_FACTS['phone']} · 💬 WhatsApp {DWT_FACTS['whatsapp_display']} · 🌐 {DWT_FACTS['website']}</p>
      <p class="text-xs mt-4 text-blue-200">© {datetime.now().year} {DWT_FACTS['name']}. All rights reserved.</p>
    </div>
  </footer>'''


def _trust_bar(on_dark=False):
    s = DWT_FACTS["stats"]
    color = "text-white drop-shadow" if on_dark else "text-dwt-muted"
    return f'''      <div class="mt-8 flex flex-wrap justify-center gap-4 text-sm {color}">
        <span>✓ {s['travellers']} travellers</span>
        <span>✓ {s['reviews_count']} reviews at {s['rating']} ★</span>
        <span>✓ {s['years']} years from Pune</span>
        <span>✓ Sinhgad Road office</span>
      </div>'''


def _head(title, description, canonical, faq_schema=None):
    schema_block = f'''
  <script type="application/ld+json">
{faq_schema}
  </script>''' if faq_schema else ""

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">

  <title>{title}</title>
  <meta name="description" content="{description}">
  <link rel="canonical" href="{canonical}">

  <meta property="og:title" content="{title}">
  <meta property="og:description" content="{description[:200]}">
  <meta property="og:type" content="website">
  <meta property="og:url" content="{canonical}">

  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="{DESIGN_SPEC['fonts']['google_url']}" rel="stylesheet">

  <script src="https://cdn.tailwindcss.com"></script>
  <script>
    tailwind.config = {{
      theme: {{ extend: {{
        fontFamily: {{ heading: ['Lexend', 'sans-serif'], body: ['"Source Sans 3"', 'sans-serif'] }},
        colors: {{
          'dwt-teal': '{DESIGN_SPEC["colors"]["dwt_teal"]}',
          'dwt-teal-dark': '{DESIGN_SPEC["colors"]["dwt_teal_dark"]}',
          'dwt-amber': '{DESIGN_SPEC["colors"]["dwt_amber"]}',
          'dwt-orange': '{DESIGN_SPEC["colors"]["dwt_orange"]}',
          'dwt-bg': '{DESIGN_SPEC["colors"]["dwt_bg"]}',
          'dwt-card': '{DESIGN_SPEC["colors"]["dwt_card"]}',
          'dwt-text': '{DESIGN_SPEC["colors"]["dwt_text"]}',
          'dwt-muted': '{DESIGN_SPEC["colors"]["dwt_muted"]}',
          'dwt-border': '{DESIGN_SPEC["colors"]["dwt_border"]}',
        }}
      }} }}
    }}
  </script>{schema_block}

  <style>
    @media (prefers-reduced-motion: reduce) {{
      *, *::before, *::after {{ animation-duration: 0.01ms !important; transition-duration: 0.01ms !important; }}
    }}
    *:focus-visible {{ outline: 3px solid {DESIGN_SPEC["colors"]["dwt_orange"]}; outline-offset: 2px; border-radius: 4px; }}
    body {{
      font-family: 'Source Sans 3', sans-serif;
      font-size: 1.0625rem;   /* 17px base — larger for readability */
      line-height: 1.65;
      color: {DESIGN_SPEC["colors"]["dwt_text"]};
    }}
    h1, h2, h3, h4 {{ font-family: 'Lexend', sans-serif; }}
    p {{ font-size: 1.0625rem; line-height: 1.7; }}
    .hero-overlay {{
      background: linear-gradient(180deg, rgba(12,73,110,0.35) 0%, rgba(12,73,110,0.55) 50%, rgba(240,249,255,1) 100%);
    }}
    .hero-img {{
      object-fit: cover;
      object-position: center;
      filter: brightness(0.85);
    }}
    .package-card-img {{
      object-fit: cover;
      object-position: center;
      width: 100%;
      height: 200px;
      border-radius: 0.5rem 0.5rem 0 0;
    }}
  </style>
</head>'''


def _final_cta_section(heading, body):
    s = DWT_FACTS["stats"]
    return f'''  <section class="py-16 md:py-24 bg-dwt-teal text-white">
    <div class="max-w-3xl mx-auto px-4 text-center">
      <h2 class="font-heading text-3xl md:text-4xl font-bold mb-6">{heading}</h2>
      <p class="text-lg text-blue-100 mb-8 max-w-xl mx-auto">{body}</p>
      <div class="flex flex-col sm:flex-row gap-3 justify-center mb-8">
        <a href="https://wa.me/{DWT_FACTS['whatsapp']}" class="inline-block bg-dwt-orange text-white px-8 py-4 rounded-md font-bold text-lg hover:bg-orange-700 transition-colors min-h-[48px]">
          💬 WhatsApp {DWT_FACTS['whatsapp_display']}
        </a>
        <a href="{DWT_FACTS['maps_link']}" class="inline-block bg-white text-dwt-teal px-8 py-4 rounded-md font-bold text-lg hover:bg-dwt-bg transition-colors min-h-[48px]">
          📍 Visit Our Pune Office
        </a>
      </div>
      <p class="text-sm text-blue-100">{s['travellers']} travellers · {s['reviews_count']} reviews at {s['rating']} ★ · {s['years']} years of fixed departures from Pune</p>
    </div>
  </section>'''


# ── PAGE TYPE 1: COMPARISON (/alternatives/[competitor]) ──────────────────────

def build_comparison_page(brief: dict) -> str:
    c = brief["competitor"]
    comp_name = c["name"]
    canonical = f"https://{DWT_FACTS['website']}/alternatives/{brief['slug']}"
    title = f"{comp_name} Alternative from Pune — {DWT_FACTS['name']} | {DWT_FACTS['stats']['rating']}★ on Google"
    desc = brief.get("meta_description") or f"Looking for a {comp_name} alternative from Pune? {DWT_FACTS['name']} — {DWT_FACTS['stats']['travellers']} travellers, {DWT_FACTS['stats']['rating']}★ on {DWT_FACTS['stats']['reviews_count']} Google reviews."
    faq_schema = _faq_schema_json(brief["faqs"])

    comparison_rows = "\n".join(
        f'''            <tr class="border-b border-dwt-border {"bg-white" if i % 2 else ""}">
              <td class="px-6 py-4 font-semibold">{r["dimension"]}</td>
              <td class="px-6 py-4 bg-yellow-50 font-medium">{r["dwt"]}</td>
              <td class="px-6 py-4 text-dwt-muted">{r["competitor"]}</td>
            </tr>''' for i, r in enumerate(brief["comparison_table"]))

    pricing_rows = "\n".join(
        f'''            <tr class="border-t border-dwt-border {"bg-dwt-bg" if i % 2 else ""}"><td class="px-6 py-3 font-semibold">{r["package"]}</td><td class="px-6 py-3">{r["dwt"]}</td><td class="px-6 py-3 text-dwt-muted">{r["competitor"]}</td></tr>''' for i, r in enumerate(brief["pricing_comparison"]))

    pain_points = "\n".join(f'''        <div class="bg-dwt-bg p-6 rounded-lg border border-dwt-border">
          <p class="font-semibold text-dwt-text mb-2">"{p["headline"]}"</p>
          <p class="text-dwt-muted text-sm">{p["description"]}</p>
        </div>''' for p in brief["pain_points"])

    hero_img = brief.get("hero_image") or _img_url("comparison")

    return f'''{_head(title, desc, canonical, faq_schema)}
<body class="bg-dwt-bg text-dwt-text antialiased">
{_sticky_mobile_cta("WhatsApp Us to Compare Packages")}
{_navbar()}

  <!-- Hero with image -->
  <section class="relative">
    <div class="absolute inset-0 z-0">
      <img src="{hero_img}" alt="Pune travellers comparing tour packages" class="w-full h-full hero-img" loading="eager">
      <div class="absolute inset-0 hero-overlay"></div>
    </div>
    <div class="relative z-10 max-w-4xl mx-auto px-4 text-center pt-20 pb-24 md:pt-32 md:pb-40">
      <p class="text-sm text-white/90 uppercase tracking-wider mb-4 font-semibold drop-shadow">{comp_name} Alternative · Pune</p>
      <h1 class="font-heading text-4xl md:text-5xl lg:text-6xl font-bold text-white leading-tight mb-6 drop-shadow-lg">
        Comparing {DWT_FACTS['name']} and {comp_name}
      </h1>
      <p class="text-lg md:text-2xl text-white max-w-2xl mx-auto mb-10 leading-relaxed drop-shadow">{brief['hero_subline']}</p>
      <div class="flex flex-col sm:flex-row gap-3 justify-center">
        <a href="https://wa.me/{DWT_FACTS['whatsapp']}" class="inline-block bg-dwt-orange text-white px-6 py-3 rounded-md font-semibold text-base hover:bg-orange-700 transition-colors min-h-[44px]">💬 WhatsApp to Compare Packages</a>
        <a href="#comparison" class="inline-block bg-white text-dwt-teal border-2 border-dwt-teal px-6 py-3 rounded-md font-semibold text-base hover:bg-dwt-teal hover:text-white transition-colors min-h-[44px]">See the Comparison</a>
      </div>
{_trust_bar(on_dark=True)}
    </div>
  </section>

  <section class="py-16 bg-white">
    <div class="max-w-4xl mx-auto px-4">
      <h2 class="font-heading text-3xl md:text-4xl font-bold text-dwt-text mb-8 text-center">Why Pune travellers explore {comp_name} alternatives</h2>
      <p class="text-dwt-muted text-center mb-12 max-w-2xl mx-auto">{brief['pain_section_intro']}</p>
      <div class="grid md:grid-cols-2 gap-6">
{pain_points}
      </div>
    </div>
  </section>

  <section id="comparison" class="py-16 bg-dwt-bg">
    <div class="max-w-6xl mx-auto px-4">
      <h2 class="font-heading text-3xl md:text-4xl font-bold text-dwt-text mb-3 text-center">{DWT_FACTS['name']} vs {comp_name}</h2>
      <p class="text-dwt-muted text-center mb-10">Honest comparison.</p>
      <div class="overflow-x-auto rounded-lg shadow-lg bg-white">
        <table class="w-full text-left min-w-[640px]" role="table">
          <thead class="bg-dwt-teal text-white">
            <tr>
              <th scope="col" class="px-6 py-4 font-semibold text-sm uppercase tracking-wider">Dimension</th>
              <th scope="col" class="px-6 py-4 font-semibold text-sm uppercase tracking-wider bg-dwt-teal-dark relative">{DWT_FACTS['name']}<span class="absolute top-1 right-2 text-xs bg-dwt-amber text-dwt-text px-2 py-0.5 rounded font-bold">YOU ARE HERE</span></th>
              <th scope="col" class="px-6 py-4 font-semibold text-sm uppercase tracking-wider">{comp_name}</th>
            </tr>
          </thead>
          <tbody class="text-sm">
{comparison_rows}
          </tbody>
        </table>
      </div>
    </div>
  </section>

  <section class="py-16 bg-white">
    <div class="max-w-5xl mx-auto px-4">
      <h2 class="font-heading text-3xl md:text-4xl font-bold text-dwt-text mb-3 text-center">Same destinations. Real prices.</h2>
      <p class="text-dwt-muted text-center mb-10">{brief.get('pricing_intro', '')}</p>
      <div class="overflow-x-auto rounded-lg shadow bg-white border border-dwt-border">
        <table class="w-full text-left min-w-[600px]">
          <thead class="bg-dwt-bg">
            <tr>
              <th scope="col" class="px-6 py-3 text-sm font-semibold uppercase">Package</th>
              <th scope="col" class="px-6 py-3 text-sm font-semibold uppercase text-dwt-teal">{DWT_FACTS['name']} (from)</th>
              <th scope="col" class="px-6 py-3 text-sm font-semibold uppercase text-dwt-muted">{comp_name} (typical from)</th>
            </tr>
          </thead>
          <tbody class="text-sm">
{pricing_rows}
          </tbody>
        </table>
      </div>
    </div>
  </section>

  <section class="py-16 bg-dwt-bg">
    <div class="max-w-5xl mx-auto px-4 grid md:grid-cols-2 gap-8">
      <article class="bg-white p-8 rounded-lg shadow border border-dwt-teal">
        <h2 class="font-heading text-2xl font-bold text-dwt-teal mb-4">Choose {DWT_FACTS['name']} if:</h2>
        <ul class="space-y-3 text-dwt-text">
{_li_check(brief["dwt_best_for"])}
        </ul>
      </article>
      <article class="bg-white p-8 rounded-lg shadow border border-dwt-border">
        <h2 class="font-heading text-2xl font-bold text-dwt-muted mb-4">Choose {comp_name} if:</h2>
        <ul class="space-y-3 text-dwt-text">
{_li_check(c["best_for"], color="dwt-muted")}
        </ul>
      </article>
    </div>
  </section>

  <section class="py-16 bg-white">
    <div class="max-w-5xl mx-auto px-4">
      <h2 class="font-heading text-3xl md:text-4xl font-bold text-dwt-text mb-10 text-center">What travellers who chose us say</h2>
      <div class="grid md:grid-cols-3 gap-6">
{_testimonials_html(brief["testimonials"])}
      </div>
    </div>
  </section>

  <section class="py-16 bg-dwt-bg">
    <div class="max-w-3xl mx-auto px-4">
      <h2 class="font-heading text-3xl md:text-4xl font-bold text-dwt-text mb-10 text-center">Common questions</h2>
      <div class="space-y-4">
{_faqs_html(brief["faqs"])}
      </div>
    </div>
  </section>

{_final_cta_section("Ready to compare a specific package?", f"WhatsApp with the destination + dates you're considering. We send a full quote within an hour, with an honest comparison vs {comp_name}.")}
{_footer()}
</body>
</html>
'''


# ── PAGE TYPE 2: TOUR LAUNCH (/tours/[campaign-slug]) ─────────────────────────

def build_tour_launch_page(brief: dict) -> str:
    """Time-sensitive single-departure page — designed to convert with urgency.
    Used for: 'Vietnam September 2026 Departure', 'Amarnath Yatra July 2026', etc.
    """
    pkg = brief["package"]
    hero = brief["hero"]
    canonical = f"https://{DWT_FACTS['website']}/tours/{brief['slug']}"
    title = brief.get("meta_title") or f"{pkg['name']} from Pune — {pkg['duration']} Group Tour | {DWT_FACTS['name']}"
    desc = brief.get("meta_description") or f"{pkg['name']} group tour from Pune. {pkg['duration']}. Departure {pkg.get('departure_date','')}. ₹{pkg.get('price','')}. Pune-based tour manager. {DWT_FACTS['stats']['rating']}★ on {DWT_FACTS['stats']['reviews_count']} reviews."
    faq_schema = _faq_schema_json(brief.get("faqs", []))

    seats_badge = ""
    if pkg.get("seats_remaining"):
        seats_badge = f'''<span class="inline-block bg-dwt-orange text-white text-xs font-bold px-3 py-1 rounded-full uppercase tracking-wider mb-4">⚡ Only {pkg["seats_remaining"]} seats left</span>'''

    included = "\n".join(
        f'''        <li class="flex gap-3 text-dwt-text"><span class="text-dwt-teal font-bold text-lg">✓</span><span>{item}</span></li>'''
        for item in brief["included"]
    )

    itinerary_html = ""
    if brief.get("itinerary"):
        itinerary_html = f'''
  <section class="py-16 bg-white">
    <div class="max-w-4xl mx-auto px-4">
      <h2 class="font-heading text-3xl md:text-4xl font-bold text-dwt-text mb-10 text-center">Day-by-day itinerary</h2>
      <div class="space-y-3">
''' + "\n".join(f'''        <details class="bg-dwt-bg p-5 rounded-lg border border-dwt-border group">
          <summary class="cursor-pointer flex justify-between items-center">
            <span class="font-heading font-bold text-dwt-text"><span class="text-dwt-orange">Day {d["day"]}</span> · {d["title"]}</span>
            <span class="text-dwt-orange group-open:rotate-180 transition-transform">▼</span>
          </summary>
          <p class="mt-3 text-dwt-muted text-sm leading-relaxed">{d["description"]}</p>
        </details>''' for d in brief["itinerary"]) + '''
      </div>
    </div>
  </section>'''

    other_departures_html = ""
    if brief.get("other_departures"):
        rows = "\n".join(f'''            <tr class="border-t border-dwt-border"><td class="px-6 py-3 font-semibold">{d["date"]}</td><td class="px-6 py-3 text-dwt-muted">{d.get("seats","Available")}</td><td class="px-6 py-3"><a href="https://wa.me/{DWT_FACTS['whatsapp']}" class="text-dwt-orange font-semibold hover:underline">Book Now →</a></td></tr>''' for d in brief["other_departures"])
        other_departures_html = f'''
  <section class="py-16 bg-dwt-bg">
    <div class="max-w-3xl mx-auto px-4">
      <h2 class="font-heading text-3xl font-bold text-dwt-text mb-8 text-center">Other upcoming departures</h2>
      <div class="overflow-x-auto rounded-lg shadow bg-white border border-dwt-border">
        <table class="w-full text-left">
          <thead class="bg-dwt-teal text-white">
            <tr>
              <th scope="col" class="px-6 py-3 text-sm font-semibold uppercase">Departure Date</th>
              <th scope="col" class="px-6 py-3 text-sm font-semibold uppercase">Status</th>
              <th scope="col" class="px-6 py-3 text-sm font-semibold uppercase">Action</th>
            </tr>
          </thead>
          <tbody class="text-sm">
{rows}
          </tbody>
        </table>
      </div>
    </div>
  </section>'''

    # Pick hero image from brief, or fall back to destination keyword in package name
    hero_img = brief.get("hero_image") or _img_url(pkg["name"])

    return f'''{_head(title, desc, canonical, faq_schema)}
<body class="bg-dwt-bg text-dwt-text antialiased">
{_sticky_mobile_cta(f"Book {pkg['name']} Now")}
{_navbar()}

  <!-- Hero with image -->
  <section class="relative">
    <div class="absolute inset-0 z-0">
      <img src="{hero_img}" alt="{pkg['name']} destination" class="w-full h-full hero-img" loading="eager">
      <div class="absolute inset-0 hero-overlay"></div>
    </div>
    <div class="relative z-10 max-w-4xl mx-auto px-4 text-center pt-16 pb-20 md:pt-24 md:pb-28">
      <p class="text-sm text-white/90 uppercase tracking-wider mb-3 font-bold drop-shadow">{brief.get('eyebrow', f"{pkg['duration']} Group Tour from Pune")}</p>
      {seats_badge}
      <h1 class="font-heading text-4xl md:text-5xl lg:text-6xl font-bold text-white leading-tight mb-6 drop-shadow-lg">{hero['headline']}</h1>
      <p class="text-lg md:text-2xl text-white max-w-2xl mx-auto mb-10 leading-relaxed drop-shadow">{hero['subline']}</p>

      <div class="bg-white border-2 border-dwt-teal rounded-lg p-6 max-w-md mx-auto mb-8 shadow-lg">
        <div class="grid grid-cols-2 gap-4 text-left">
          <div>
            <p class="text-xs text-dwt-muted uppercase tracking-wider">Departure</p>
            <p class="font-heading font-bold text-dwt-teal text-lg">{pkg.get('departure_date', 'On request')}</p>
          </div>
          <div>
            <p class="text-xs text-dwt-muted uppercase tracking-wider">Duration</p>
            <p class="font-heading font-bold text-dwt-teal text-lg">{pkg['duration']}</p>
          </div>
          <div>
            <p class="text-xs text-dwt-muted uppercase tracking-wider">Price (per person)</p>
            <p class="font-heading font-bold text-dwt-orange text-2xl">₹{pkg['price']}</p>
          </div>
          <div>
            <p class="text-xs text-dwt-muted uppercase tracking-wider">From</p>
            <p class="font-heading font-bold text-dwt-teal text-lg">Pune</p>
          </div>
        </div>
      </div>

      <a href="https://wa.me/{DWT_FACTS['whatsapp']}" class="inline-block bg-dwt-orange text-white px-8 py-4 rounded-md font-bold text-lg hover:bg-orange-700 transition-colors min-h-[48px]">💬 WhatsApp to Reserve Your Seat →</a>
{_trust_bar(on_dark=True)}
    </div>
  </section>

  <section class="py-16 bg-white">
    <div class="max-w-3xl mx-auto px-4">
      <h2 class="font-heading text-3xl md:text-4xl font-bold text-dwt-text mb-8 text-center">What's included</h2>
      <ul class="space-y-3 max-w-xl mx-auto">
{included}
      </ul>
    </div>
  </section>
{itinerary_html}
{other_departures_html}

  <section class="py-16 bg-white">
    <div class="max-w-5xl mx-auto px-4">
      <h2 class="font-heading text-3xl md:text-4xl font-bold text-dwt-text mb-10 text-center">What past travellers say</h2>
      <div class="grid md:grid-cols-3 gap-6">
{_testimonials_html(brief.get("testimonials", []))}
      </div>
    </div>
  </section>

  <section class="py-16 bg-dwt-bg">
    <div class="max-w-3xl mx-auto px-4">
      <h2 class="font-heading text-3xl md:text-4xl font-bold text-dwt-text mb-10 text-center">Common questions</h2>
      <div class="space-y-4">
{_faqs_html(brief.get("faqs", []))}
      </div>
    </div>
  </section>

{_final_cta_section(f"Lock your seat for {pkg.get('departure_date','this departure')}", f"WhatsApp us to confirm availability and reserve. Bookings close once {pkg.get('seats_remaining', 25)} seats fill.")}
{_footer()}
</body>
</html>
'''


# ── PAGE TYPE 3: DESTINATION (/destinations/[place]) ──────────────────────────

def build_destination_page(brief: dict) -> str:
    """Evergreen destination page — all packages for one destination.
    Used for: 'Vietnam Tours from Pune', 'Kashmir Tours from Pune', etc.
    """
    dest = brief["destination"]
    canonical = f"https://{DWT_FACTS['website']}/{brief['slug']}"
    title = brief.get("meta_title") or f"{dest['name']} Tour Packages from Pune — {DWT_FACTS['name']} | {DWT_FACTS['stats']['rating']}★ Rated"
    desc = brief.get("meta_description") or f"{dest['name']} tour packages from Pune. Multiple departures. Indian meals + Pune-based tour manager included. {DWT_FACTS['stats']['travellers']} travellers, {DWT_FACTS['stats']['rating']}★."
    faq_schema = _faq_schema_json(brief.get("faqs", []))

    packages_html = "\n".join(f'''        <article class="bg-white rounded-lg shadow-md border border-dwt-border overflow-hidden hover:shadow-lg transition-shadow flex flex-col">
          <img src="{p.get("image") or _img_url(p.get("image_key") or dest["name"])}" alt="{p['name']}" class="package-card-img" loading="lazy">
          <div class="p-6 flex flex-col flex-grow">
            <p class="text-xs text-dwt-teal uppercase tracking-wider font-bold mb-2">{p['duration']}</p>
            <h3 class="font-heading text-xl font-bold text-dwt-text mb-2">{p['name']}</h3>
            <p class="text-dwt-muted text-sm mb-4">{p.get('tagline','')}</p>
            <p class="text-2xl font-heading font-bold text-dwt-orange mb-1">₹{p['price']}</p>
            <p class="text-xs text-dwt-muted mb-3">per person · {p.get('airfare','airfare incl' if p.get('airfare_included') else 'airfare excl')}</p>
            <p class="text-xs text-dwt-muted mb-4">Next: <span class="font-semibold text-dwt-text">{p.get('next_departure','On request')}</span></p>
            <ul class="text-sm text-dwt-text space-y-1 mb-5 flex-grow">
{chr(10).join(f"              <li>✓ {h}</li>" for h in p.get("highlights", [])[:4])}
            </ul>
            <a href="https://wa.me/{DWT_FACTS['whatsapp']}" class="block w-full text-center bg-dwt-orange text-white py-2.5 rounded-md font-semibold hover:bg-orange-700 transition-colors">WhatsApp to Book →</a>
          </div>
        </article>''' for p in brief["packages"])

    why_dwt_html = _li_check(dest.get("why_dwt", []))

    best_time_html = ""
    if dest.get("best_time_to_visit"):
        best_time_html = f'''
  <section class="py-16 bg-white">
    <div class="max-w-3xl mx-auto px-4">
      <h2 class="font-heading text-3xl font-bold text-dwt-text mb-6 text-center">Best time to visit {dest['name']}</h2>
      <p class="text-dwt-muted text-center leading-relaxed">{dest['best_time_to_visit']}</p>
    </div>
  </section>'''

    hero_img = brief.get("hero_image") or _img_url(dest["name"])

    return f'''{_head(title, desc, canonical, faq_schema)}
<body class="bg-dwt-bg text-dwt-text antialiased">
{_sticky_mobile_cta(f"WhatsApp Us About {dest['name']}")}
{_navbar()}

  <!-- Hero with image -->
  <section class="relative">
    <div class="absolute inset-0 z-0">
      <img src="{hero_img}" alt="{dest['name']} destination view" class="w-full h-full hero-img" loading="eager">
      <div class="absolute inset-0 hero-overlay"></div>
    </div>
    <div class="relative z-10 max-w-4xl mx-auto px-4 text-center pt-20 pb-24 md:pt-32 md:pb-40">
      <p class="text-sm text-white/90 uppercase tracking-wider mb-4 font-semibold drop-shadow">Group Tour Packages · From Pune</p>
      <h1 class="font-heading text-4xl md:text-5xl lg:text-6xl font-bold text-white leading-tight mb-6 drop-shadow-lg">{dest['name']} Tour Packages from Pune</h1>
      <p class="text-lg md:text-2xl text-white max-w-2xl mx-auto mb-10 leading-relaxed drop-shadow">{dest.get('hero_subline','')}</p>
      <div class="flex flex-col sm:flex-row gap-3 justify-center">
        <a href="#packages" class="inline-block bg-dwt-orange text-white px-6 py-3 rounded-md font-semibold text-base hover:bg-orange-700 transition-colors min-h-[44px]">See All {dest['name']} Packages</a>
        <a href="https://wa.me/{DWT_FACTS['whatsapp']}" class="inline-block bg-white text-dwt-teal border-2 border-dwt-teal px-6 py-3 rounded-md font-semibold text-base hover:bg-dwt-teal hover:text-white transition-colors min-h-[44px]">WhatsApp Us</a>
      </div>
{_trust_bar(on_dark=True)}
    </div>
  </section>

  <section id="packages" class="py-16 bg-dwt-bg">
    <div class="max-w-6xl mx-auto px-4">
      <h2 class="font-heading text-3xl md:text-4xl font-bold text-dwt-text mb-3 text-center">All our {dest['name']} packages</h2>
      <p class="text-dwt-muted text-center mb-10">{len(brief["packages"])} options. All from Pune. All with Pune-based tour manager and Indian meals.</p>
      <div class="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
{packages_html}
      </div>
    </div>
  </section>

  <section class="py-16 bg-white">
    <div class="max-w-3xl mx-auto px-4">
      <h2 class="font-heading text-3xl md:text-4xl font-bold text-dwt-text mb-8 text-center">Why book {dest['name']} with {DWT_FACTS['name']}</h2>
      <ul class="space-y-3 max-w-xl mx-auto">
{why_dwt_html}
      </ul>
    </div>
  </section>
{best_time_html}

  <section class="py-16 bg-white">
    <div class="max-w-5xl mx-auto px-4">
      <h2 class="font-heading text-3xl md:text-4xl font-bold text-dwt-text mb-10 text-center">Travellers' experiences</h2>
      <div class="grid md:grid-cols-3 gap-6">
{_testimonials_html(brief.get("testimonials", []))}
      </div>
    </div>
  </section>

  <section class="py-16 bg-dwt-bg">
    <div class="max-w-3xl mx-auto px-4">
      <h2 class="font-heading text-3xl md:text-4xl font-bold text-dwt-text mb-10 text-center">Common questions about {dest['name']}</h2>
      <div class="space-y-4">
{_faqs_html(brief.get("faqs", []))}
      </div>
    </div>
  </section>

{_final_cta_section(f"Ready to plan your {dest['name']} trip?", f"WhatsApp us with your preferred dates and we'll send the right {dest['name']} package within an hour.")}
{_footer()}
</body>
</html>
'''


# ── PAGE TYPE 4: AUDIENCE (/tours-for/[segment]) ──────────────────────────────

def build_audience_page(brief: dict) -> str:
    """Audience-segment page — packages curated for one customer segment.
    Used for: 'Family Tours from Pune', 'Honeymoon Tours from Pune', 'Religious Tours', etc.
    """
    aud = brief["audience"]
    canonical = f"https://{DWT_FACTS['website']}/{brief['slug']}"
    title = brief.get("meta_title") or f"{aud['name']} from Pune — {DWT_FACTS['name']} | {DWT_FACTS['stats']['rating']}★ Rated"
    desc = brief.get("meta_description") or f"{aud['name']} group tours from Pune. Curated by 25,000+ travellers' experience. {DWT_FACTS['stats']['rating']}★ on {DWT_FACTS['stats']['reviews_count']} reviews."
    faq_schema = _faq_schema_json(brief.get("faqs", []))

    why_dwt = _li_check(aud.get("why_dwt_for_this_audience", []))
    needs_html = "\n".join(f'''        <div class="bg-dwt-bg p-6 rounded-lg border border-dwt-border">
          <h3 class="font-heading font-bold text-dwt-text mb-2">{n["headline"]}</h3>
          <p class="text-dwt-muted text-sm">{n["description"]}</p>
        </div>''' for n in brief.get("audience_needs", []))

    packages_html = "\n".join(f'''        <article class="bg-white rounded-lg shadow-md border border-dwt-border overflow-hidden hover:shadow-lg transition-shadow flex flex-col">
          <img src="{p.get("image") or _img_url(p.get("image_key") or p.get("destination", aud["name"]))}" alt="{p['name']}" class="package-card-img" loading="lazy">
          <div class="p-6 flex flex-col flex-grow">
            <p class="text-xs text-dwt-teal uppercase tracking-wider font-bold mb-2">{p['duration']} · {p.get('destination','')}</p>
            <h3 class="font-heading text-xl font-bold text-dwt-text mb-2">{p['name']}</h3>
            <p class="text-dwt-muted text-sm mb-4 flex-grow">{p.get('why_for_this_audience','')}</p>
            <p class="text-2xl font-heading font-bold text-dwt-orange mb-1">₹{p['price']}</p>
            <p class="text-xs text-dwt-muted mb-4">per person · Next: {p.get('next_departure','On request')}</p>
            <a href="https://wa.me/{DWT_FACTS['whatsapp']}" class="block w-full text-center bg-dwt-orange text-white py-2.5 rounded-md font-semibold hover:bg-orange-700 transition-colors">WhatsApp Us →</a>
          </div>
        </article>''' for p in brief.get("recommended_packages", []))

    hero_img = brief.get("hero_image") or _img_url(aud.get("image_key") or aud["name"])

    return f'''{_head(title, desc, canonical, faq_schema)}
<body class="bg-dwt-bg text-dwt-text antialiased">
{_sticky_mobile_cta(f"WhatsApp Us About {aud['name']}")}
{_navbar()}

  <!-- Hero with image -->
  <section class="relative">
    <div class="absolute inset-0 z-0">
      <img src="{hero_img}" alt="{aud['name']} from Pune" class="w-full h-full hero-img" loading="eager">
      <div class="absolute inset-0 hero-overlay"></div>
    </div>
    <div class="relative z-10 max-w-4xl mx-auto px-4 text-center pt-20 pb-24 md:pt-32 md:pb-40">
      <p class="text-sm text-white/90 uppercase tracking-wider mb-4 font-semibold drop-shadow">{aud.get('eyebrow','Curated Group Tours · From Pune')}</p>
      <h1 class="font-heading text-4xl md:text-5xl lg:text-6xl font-bold text-white leading-tight mb-6 drop-shadow-lg">{aud['name']} from Pune</h1>
      <p class="text-lg md:text-2xl text-white max-w-2xl mx-auto mb-10 leading-relaxed drop-shadow">{aud.get('hero_subline','')}</p>
      <div class="flex flex-col sm:flex-row gap-3 justify-center">
        <a href="#packages" class="inline-block bg-dwt-orange text-white px-6 py-3 rounded-md font-semibold text-base hover:bg-orange-700 transition-colors min-h-[44px]">See Curated Packages</a>
        <a href="https://wa.me/{DWT_FACTS['whatsapp']}" class="inline-block bg-white text-dwt-teal border-2 border-dwt-teal px-6 py-3 rounded-md font-semibold text-base hover:bg-dwt-teal hover:text-white transition-colors min-h-[44px]">WhatsApp Us</a>
      </div>
{_trust_bar(on_dark=True)}
    </div>
  </section>

  <section class="py-16 bg-white">
    <div class="max-w-4xl mx-auto px-4">
      <h2 class="font-heading text-3xl md:text-4xl font-bold text-dwt-text mb-8 text-center">What {aud['name'].lower()} need from a tour operator</h2>
      <p class="text-dwt-muted text-center mb-12 max-w-2xl mx-auto">{aud.get('needs_intro','')}</p>
      <div class="grid md:grid-cols-2 gap-6">
{needs_html}
      </div>
    </div>
  </section>

  <section id="packages" class="py-16 bg-dwt-bg">
    <div class="max-w-6xl mx-auto px-4">
      <h2 class="font-heading text-3xl md:text-4xl font-bold text-dwt-text mb-3 text-center">Curated for {aud['name'].lower()}</h2>
      <p class="text-dwt-muted text-center mb-10">Hand-picked from our 17 active packages.</p>
      <div class="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
{packages_html}
      </div>
    </div>
  </section>

  <section class="py-16 bg-white">
    <div class="max-w-3xl mx-auto px-4">
      <h2 class="font-heading text-3xl md:text-4xl font-bold text-dwt-text mb-8 text-center">Why {aud['name'].lower()} pick {DWT_FACTS['name']}</h2>
      <ul class="space-y-3 max-w-xl mx-auto">
{why_dwt}
      </ul>
    </div>
  </section>

  <section class="py-16 bg-dwt-bg">
    <div class="max-w-5xl mx-auto px-4">
      <h2 class="font-heading text-3xl md:text-4xl font-bold text-dwt-text mb-10 text-center">What {aud['name'].lower()} say</h2>
      <div class="grid md:grid-cols-3 gap-6">
{_testimonials_html(brief.get("testimonials", []))}
      </div>
    </div>
  </section>

  <section class="py-16 bg-white">
    <div class="max-w-3xl mx-auto px-4">
      <h2 class="font-heading text-3xl md:text-4xl font-bold text-dwt-text mb-10 text-center">Common questions</h2>
      <div class="space-y-4">
{_faqs_html(brief.get("faqs", []))}
      </div>
    </div>
  </section>

{_final_cta_section(f"Plan your {aud['name'].lower()} trip", f"WhatsApp us with your group size and preferred destination. We'll send 2-3 curated options within an hour.")}
{_footer()}
</body>
</html>
'''


# ── Dispatcher ────────────────────────────────────────────────────────────────

BUILDERS = {
    "comparison":  build_comparison_page,
    "tour-launch": build_tour_launch_page,
    "destination": build_destination_page,
    "audience":    build_audience_page,
}


def build_from_brief(brief_path: str) -> dict:
    """Load brief and dispatch to the right builder by type."""
    brief = _load_brief(brief_path)
    brief_type = brief.get("type", "comparison")
    if brief_type not in BUILDERS:
        raise ValueError(f"Unknown brief type '{brief_type}'. Supported: {list(BUILDERS.keys())}")
    html = BUILDERS[brief_type](brief)
    return {"slug": brief["slug"], "html": html, "brief_type": brief_type, "brief": brief}


def save_html(slug: str, html: str, brief_type: str = "comparison", out_dir: str = "outputs/landing-pages") -> str:
    """Save HTML with type-aware filename prefix."""
    prefix = {
        "comparison": "alternatives",
        "tour-launch": "tour",
        "destination": "destination",
        "audience": "audience",
    }.get(brief_type, "page")
    out_path = Path(out_dir) / f"{prefix}-{slug}.html"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html)
    return str(out_path)
