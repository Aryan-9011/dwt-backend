"""
Instagram pipeline — self-contained inside the backend.

Ported from the workspace scripts so it deploys with dwt-backend. Railway only
ships this repo, so nothing here may reach outside backend/.

    render(spec_dict)   → slide PNGs in outputs/instagram/pending/<slug>/
    gate(slug)          → caption lint + AI detection → gate.json
    approve/reject(slug)
    publish(slug, dry)  → imgbb → Graph API → publish-log.jsonl
"""
import base64, html, json, os, re, shutil, subprocess, sys, tempfile
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
VENDOR = BACKEND / "vendor" / "ig"
PENDING = BACKEND / "outputs" / "instagram" / "pending"
PUBLISHED = BACKEND / "outputs" / "instagram" / "published"
REJECTED = BACKEND / "outputs" / "instagram" / "rejected"
SPECS = BACKEND / "data" / "ig-specs"
LOG = BACKEND / "outputs" / "automation" / "publish-log.jsonl"
W, H, SAFE = 1080, 1350, 120


def chrome():
    if os.environ.get("CHROME_BIN"):
        return os.environ["CHROME_BIN"]
    for c in ("/usr/bin/chromium", "/usr/bin/chromium-browser",
              "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
              "chromium", "google-chrome"):
        p = c if c.startswith("/") else shutil.which(c)
        if p and Path(p).exists():
            return p
    raise RuntimeError("no chromium — set CHROME_BIN or install it in the image")


def brand(slug="dwt"):
    f = BACKEND / "brands" / slug / "brand.json"
    if not f.exists():
        raise RuntimeError(f"unknown brand {slug}")
    return json.loads(f.read_text(encoding="utf-8"))


def _logo(b):
    p = (b.get("logo") or {}).get("knockout")
    f = BACKEND / p if p else None
    if not f or not f.exists():
        return None
    return "data:image/png;base64," + base64.b64encode(f.read_bytes()).decode()


def _e(s):
    return html.escape(str(s))


def _slide_html(s, i, n, b, logo, handle):
    c = b["colors"]
    ink = c.get("ink", "#0E2E2C"); teal = c.get("primary_dark") or c.get("primary")
    gold = c.get("accent"); paper = c.get("paper", "#fff")
    k = s.get("kind", "body")
    if k == "cover":
        inner = (f'<div class="kicker gold">{_e(s.get("kicker",""))}</div><h1>{_e(s["title"])}</h1>'
                 f'<div class="rule"></div><p class="sub">{_e(s.get("sub",""))}</p>')
    elif k == "stake":
        inner = f'<h2 class="stake">{_e(s["title"])}</h2>' + (f'<p class="body">{_e(s["body"])}</p>' if s.get("body") else "")
    elif k in ("list", "recap"):
        items = "".join(f"<li>{_e(x)}</li>" for x in s.get("items", []))
        inner = (f'<div class="kicker gold">{_e(s.get("kicker",""))}</div>'
                 + (f'<h2>{_e(s["title"])}</h2>' if s.get("title") else "")
                 + f'<ul class="{k}">{items}</ul>'
                 + (f'<div class="cta">{_e(s["cta"])}</div>' if s.get("cta") else ""))
    else:
        inner = (f'<div class="kicker gold">{_e(s.get("kicker",""))}</div><h2>{_e(s["title"])}</h2>'
                 + (f'<p class="body">{_e(s.get("body",""))}</p>' if s.get("body") else ""))
    mark = f'<img class="logo" src="{logo}">' if logo else ""
    return f"""<!doctype html><meta charset="utf-8"><style>
*{{margin:0;padding:0;box-sizing:border-box;-webkit-print-color-adjust:exact}}
html,body{{width:{W}px;height:{H}px;overflow:hidden}}
body{{font-family:"DejaVu Sans","Noto Sans","Helvetica Neue",Arial,sans-serif;background:{paper};color:{ink};
 display:flex;flex-direction:column;justify-content:center;padding:{SAFE}px {SAFE}px {SAFE+40}px;position:relative}}
body.cover,body.stake{{background:{ink};color:#fff}} body.recap{{background:{teal};color:#fff}}
.kicker{{font-size:30px;letter-spacing:7px;font-weight:800;text-transform:uppercase;margin-bottom:26px}}
.gold{{color:{gold}}} h1{{font-size:104px;line-height:1.02;font-weight:800;letter-spacing:-3px}}
h2{{font-size:70px;line-height:1.1;font-weight:800;letter-spacing:-1.6px}} h2.stake{{font-size:76px}}
.rule{{width:150px;height:10px;background:{gold};border-radius:5px;margin:40px 0}}
.sub{{font-size:38px;line-height:1.42;opacity:.92;font-weight:500}}
p.body{{font-size:40px;line-height:1.45;margin-top:34px;opacity:.9}}
ul{{list-style:none;margin-top:38px}}
ul li{{font-size:40px;line-height:1.36;padding:19px 0 19px 48px;position:relative;border-top:2px solid rgba(255,255,255,.16)}}
body:not(.recap) ul li{{border-top-color:rgba(14,46,44,.12)}} ul li:first-child{{border-top:none}}
ul li:before{{content:"";position:absolute;left:0;top:34px;width:16px;height:16px;border-radius:50%;background:{gold}}}
ul.recap li{{font-size:36px;padding:15px 0 15px 48px}}
.cta{{margin-top:44px;display:inline-block;background:{gold};color:{ink};font-size:40px;font-weight:800;
 letter-spacing:1.5px;padding:26px 44px;border-radius:14px}}
.num{{position:absolute;top:{SAFE-56}px;right:{SAFE}px;font-size:28px;font-weight:700;letter-spacing:2px;opacity:.55}}
.handle{{position:absolute;bottom:{SAFE-66}px;left:{SAFE}px;font-size:26px;letter-spacing:2px;font-weight:700;opacity:.6}}
.logo{{position:absolute;top:{SAFE-70}px;left:{SAFE}px;height:52px;opacity:.95}}
body:not(.cover):not(.stake):not(.recap) .logo{{filter:invert(1) brightness(.35)}}
</style><body class="{k}">{mark}<div class="num">{i}/{n}</div>{inner}<div class="handle">{_e(handle)}</div></body>"""


def render(spec: dict) -> dict:
    b = brand(spec.get("brand", "dwt"))
    logo = _logo(b)
    out = PENDING / spec["slug"]
    out.mkdir(parents=True, exist_ok=True)
    binpath = chrome()
    n = len(spec["slides"])
    with tempfile.TemporaryDirectory() as td:
        for i, s in enumerate(spec["slides"], 1):
            hf = Path(td) / f"s{i}.html"
            hf.write_text(_slide_html(s, i, n, b, logo, spec.get("handle", "")), encoding="utf-8")
            subprocess.run([binpath, "--headless", "--disable-gpu", "--hide-scrollbars",
                            "--no-sandbox", "--disable-dev-shm-usage",
                            f"--window-size={W},{H}", f"--screenshot={out / f'{i:02d}.png'}",
                            f"file://{hf}"], check=True, capture_output=True, timeout=120)
    (out / "spec.json").write_text(json.dumps(spec, indent=2, ensure_ascii=False), encoding="utf-8")
    if spec.get("caption"):
        (out / "caption.txt").write_text(spec["caption"], encoding="utf-8")
    return {"slug": spec["slug"], "slides": n, "dir": str(out)}


def _py(script, *args, timeout=180):
    r = subprocess.run([sys.executable, str(VENDOR / script), *args],
                       capture_output=True, text=True, timeout=timeout)
    return r.stdout


def gate(slug: str) -> dict:
    d = PENDING / slug
    cap = d / "caption.txt"
    out = {"checked_at": datetime.now(timezone.utc).isoformat()}
    if not cap.exists():
        out |= {"caption_ok": False, "human_ok": False, "note": "no caption.txt"}
    else:
        so = _py("caption.py", str(cap))
        verdict = next((l.split()[-1] for l in so.splitlines() if "VERDICT" in l), "UNKNOWN")
        out["caption_verdict"] = verdict
        out["caption_ok"] = verdict == "READY"
        out["caption_fails"] = [l.strip() for l in so.splitlines() if l.strip().startswith(("FAIL", "WARN"))]
        so2 = _py("detect.py", "--lexicon", str(VENDOR / "slop.json"), str(cap))
        score = 0.0
        for l in so2.splitlines():
            if "HUMAN SCORE" in l:
                for tok in l.split():
                    try:
                        score = float(tok); break
                    except ValueError:
                        continue
        out["human_score"] = score
        out["human_ok"] = score >= 50.0       # floor is 50: detector is calibrated on English
    out["slides"] = len(sorted(d.glob("[0-9]*.png")))
    (d / "gate.json").write_text(json.dumps(out, indent=2))
    return out


def approve(slug, force=False):
    d = PENDING / slug
    g = gate(slug)
    if not g.get("caption_ok") and not force:
        raise RuntimeError("caption did not pass lint: " + "; ".join(g.get("caption_fails", [])))
    (d / "APPROVED").write_text(datetime.now(timezone.utc).isoformat())
    return {"slug": slug, "state": "APPROVED"}


def reject(slug):
    REJECTED.mkdir(parents=True, exist_ok=True)
    (PENDING / slug).rename(REJECTED / slug)
    return {"slug": slug, "state": "REJECTED"}


def publish(slug, dry_run=True):
    from services.instagram_publisher import post_carousel_sync
    from services.marketing_post_generator import _upload_imgbb
    d = PENDING / slug
    if not (d / "APPROVED").exists():
        raise RuntimeError(f"{slug} is not approved")
    imgs = sorted(d.glob("[0-9]*.png"))
    if not imgs:
        raise RuntimeError("no slides")
    caption = (d / "caption.txt").read_text(encoding="utf-8") if (d / "caption.txt").exists() else ""
    urls = []
    for p in imgs:
        u = _upload_imgbb(p, f"{slug}-{p.stem}")
        if not u:
            raise RuntimeError(f"imgbb upload failed for {p.name}")
        urls.append(u)
    if dry_run:
        res = {"success": True, "dry_run": True, "image_count": len(urls)}
    else:
        res = post_carousel_sync(urls, caption)
        PUBLISHED.mkdir(parents=True, exist_ok=True)
        d.rename(PUBLISHED / slug)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as fh:
        fh.write(json.dumps({"ts": datetime.now(timezone.utc).isoformat(), "slug": slug,
                             "dry_run": dry_run, "result": res}) + "\n")
    return res
