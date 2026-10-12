"""
Content calendar generator.

Builds N weeks of Instagram plans from the real departure board in
data/packages.json, applying the rules the Apify data actually produced for
@dreamworldtours_ rather than generic best practice:

  * carousels outperform reels ON THIS ACCOUNT (266x/247x/120x vs 1.00/0.47/0.42)
    so the week is 3 carousels + 1 reel until a Marathi reel proves otherwise
  * relational framing beats transactional 78 vs 23 at the median, so at least
    one relational slot per week is mandatory
  * carousels English, reels Marathi, Hinglish only where the post is advice or
    emotion rather than a reference document
  * the account was dormant 417 days, so the honest expectation is 50-150
"""
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
PACKAGES = BACKEND / "data" / "packages.json"
CAL_DIR = BACKEND / "data" / "ig-calendars"
MON = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}

RULES = {
    "language": "Carousels ENGLISH · Reels MARATHI (Devanagari) · Hinglish only where the post is advice or emotion, never for a reference document.",
    "framing": "Relational beats transactional 78 vs 23 at the median. Every week needs at least one genuinely relational post.",
    "format": "This account's carousels win (266x/247x/120x) and its reels lose (1.00x/0.47x/0.42x). 3 carousels + 1 reel until a Marathi reel proves otherwise.",
    "reality": "Dormant 417 days (7 Aug 2025 → 29 Sep 2026); median fell 13,099 → 36. Cold-start, not a penalty. Expect 50–150 on a good post. Consistency is the cure.",
}


def _parse_departures():
    """Every upcoming departure, newest first, from the real package file."""
    if not PACKAGES.exists():
        return []
    today = date.today()
    out = []
    for p in json.loads(PACKAGES.read_text(encoding="utf-8")):
        for raw in p.get("departures") or []:
            m = re.match(r"(?:(\d{1,2})\s+)?([A-Za-z]{3})[a-z]*\s*(\d{4})?", str(raw).strip())
            if not m:
                continue
            day, mon, yr = m.groups()
            if mon[:3] not in MON:
                continue
            try:
                d = date(int(yr) if yr else today.year, MON[mon[:3]], int(day) if day else 15)
            except ValueError:
                continue
            if d >= today:
                out.append({"date": d, "exact": bool(day), "name": p["name"],
                            "price": p.get("price_display", ""), "duration": p.get("duration", ""),
                            "flights": p.get("flights"), "slug": p.get("slug"),
                            "highlights": (p.get("highlights") or [])[:3],
                            "spotlight": p.get("spotlight_fact", "")})
    return sorted(out, key=lambda x: x["date"])


def _slots(week_start, deps):
    """Four posts: Tue/Thu/Fri/Sun. Urgency drives Tuesday, the rest rotate type."""
    wk_end = week_start + timedelta(days=13)          # look two weeks ahead to sell
    soon = [d for d in deps if week_start <= d["date"] <= wk_end]
    later = [d for d in deps if d["date"] > wk_end][:4]
    pick = lambda i, pool: pool[i % len(pool)] if pool else None

    pool = soon + later
    seen, uniq = set(), []
    for d in pool:                       # one slot per package, no repeats in a week
        if d["name"] not in seen:
            seen.add(d["name"]); uniq.append(d)
    urgent = uniq[0] if uniq else None
    second = uniq[1] if len(uniq) > 1 else None
    opening = uniq[2] if len(uniq) > 2 else (second or urgent)

    def fmt(d):
        if not d:
            return "—", ""
        days = (d["date"] - week_start).days
        return d["name"], f"{d['date'].strftime('%d %b')} · {days}d out · {d['price']}"

    un, ud = fmt(urgent)
    on, od = fmt(opening)
    sn, sd = fmt(second)

    return [
        {"day": "MON", "offset": 0, "time": "—", "format": "engage only", "lang": "—", "type": "—",
         "angle": "20-minute engagement round. No post.",
         "detail": "Stories x3. Comment on the reach and peer list before posting anything this week."},
        {"day": "TUE", "offset": 1, "time": "7:30pm", "format": "CAROUSEL", "lang": "English", "type": "TEACH",
         "angle": f"Itinerary carousel — {un}",
         "detail": f"{ud}. Day-by-day listicle, the shape that produced this account's best posts. "
                   f"Include one honest slide about who the trip is NOT for. CTA: comment a keyword."},
        {"day": "WED", "offset": 2, "time": "—", "format": "stories + engage", "lang": "—", "type": "—",
         "angle": f"Last call — {un}",
         "detail": "5 frames, countdown sticker, DM keyword. ⚠️ keyword auto-replies still do not exist."},
        {"day": "THU", "offset": 3, "time": "7:30pm", "format": "REEL", "lang": "Marathi", "type": "PROOF",
         "angle": "Proof — film something that actually happened",
         "detail": "~35s. Open on the @md_tours register (747x): नमस्कार मायबाप पर्यटक मंडळी. "
                   "A departure, an airport send-off, a group on the bus. Real faces. "
                   "⚠️ Only works if someone is briefed to film it."},
        {"day": "FRI", "offset": 4, "time": "8:00pm", "format": "CAROUSEL", "lang": "English", "type": "OFFER",
         "angle": f"What {sn.split('—')[0].strip()} actually includes" if sn != "—" else "What the price actually includes",
         "detail": f"{sd}. Line-item breakdown, not an offer post — 'DM for details' scored 0.47x here. "
                   f"State plainly what is NOT included."},
        {"day": "SAT", "offset": 5, "time": "—", "format": "rest", "lang": "—", "type": "—",
         "angle": "Stories only, 2–3 frames",
         "detail": "Lowest-engagement window of the week. Do not burn a carousel on it."},
        {"day": "SUN", "offset": 6, "time": "7:30pm", "format": "CAROUSEL", "lang": "Hinglish", "type": "RELATIONAL",
         "angle": "The relational slot — who are you taking?",
         "detail": "Advice or emotion, never a reference document — this is where Hinglish belongs and where "
                   f"this account's best numbers come from. Tie it to {on} if it fits. {od}"},
    ]


def generate(weeks=3, start=None):
    """Generate N consecutive weekly calendars. Returns the list, and writes each."""
    deps = _parse_departures()
    base = start or date.today()
    base = base - timedelta(days=base.weekday())        # snap to Monday
    CAL_DIR.mkdir(parents=True, exist_ok=True)
    made = []
    for w in range(weeks):
        ws = base + timedelta(weeks=w)
        days = []
        for s in _slots(ws, deps):
            d = ws + timedelta(days=s.pop("offset"))
            days.append({**s, "date": d.strftime("%d %b")})
        window = [x for x in deps if ws <= x["date"] <= ws + timedelta(days=60)]
        cal = {
            "week_of": ws.isoformat(),
            "week_label": f"{ws.strftime('%d %b')} – {(ws + timedelta(days=6)).strftime('%d %b %Y')}",
            "handle": "@dreamworldtours_",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "rules": RULES,
            "days": days,
            "departures": [{"date": x["date"].strftime("%a %d %b"),
                            "days": (x["date"] - ws).days,
                            "name": x["name"],
                            "note": " · ".join(filter(None, [x["duration"], x["price"],
                                                            "" if x["exact"] else "month only, confirm the date"]))}
                           for x in window[:8]],
            "engagement": {
                "note": "20 min/day BEFORE posting, never after. Do NOT comment on direct competitors.",
                "reach": ["@capture.a.trip (median 236)", "@wander.on (median 1388)"],
                "peers": ["@holidayscrowd (median 53 — our size)", "@md_tours (median 43, 747x outlier)"],
                "watch": ["@veena_world", "@kesaritoursofficial", "@luxuryvacations_abroad", "@aviratparikrama"],
                "missing": "5 Pune/Maharashtra lifestyle creators — not competitors. Not yet sourced.",
            },
            "fix_outside_calendar": [
                "Bio says '25,000+ travellers'. The real number is 50,000+.",
                "Bio has no Pune, no Maharashtra. You are a Pune operator reading as generic-national.",
                "Apply for verification — 14,548 followers, 797 posts, 16 years, live website.",
                "Keyword auto-replies do not exist. Every comment CTA is currently a dead end.",
            ],
        }
        (CAL_DIR / f"{ws.isoformat()}.json").write_text(
            json.dumps(cal, indent=2, ensure_ascii=False), encoding="utf-8")
        made.append(cal)
    return made


def listing():
    CAL_DIR.mkdir(parents=True, exist_ok=True)
    out = []
    for f in sorted(CAL_DIR.glob("*.json")):
        try:
            c = json.loads(f.read_text(encoding="utf-8"))
            out.append({"week_of": c["week_of"], "week_label": c.get("week_label"),
                        "posts": len([d for d in c["days"] if d["format"] not in ("—", "rest", "engage only", "stories + engage")]),
                        "generated_at": c.get("generated_at")})
        except Exception:
            continue
    return out


def load(week_of):
    f = CAL_DIR / f"{week_of}.json"
    if not f.exists():
        return None
    return json.loads(f.read_text(encoding="utf-8"))
