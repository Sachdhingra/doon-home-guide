"""Writes one self-contained HTML page with every draft (status: review) for the owner to read.
    python3 tools/review_page.py OUT.html
"""
import base64, datetime as dt, html, json, sys
from pathlib import Path
import yaml
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import build

ROOT = build.ROOT
cfg = yaml.safe_load((ROOT / "site.yaml").read_text(encoding="utf-8"))
products = json.loads((ROOT / "data/hde-products.json").read_text(encoding="utf-8"))["products"]
site = build.Site(cfg, products, dt.date.today(), Path("/tmp/dhg-review-unused"))
E = html.escape

def card(pid, campaign):
    p = products[pid]
    img = (ROOT / "data/product-images" / Path(p["image"]).name).read_bytes()
    price = f"MRP from ₹{p['from']:,}" if p.get("from") else "Price on request"
    return (f'<div class="pcard"><img src="data:image/jpeg;base64,{base64.b64encode(img).decode()}" alt="{E(p["name"])}">'
            f'<span class="pcard__name">{E(p["name"])}</span><span class="pcard__price">{price}</span>'
            f'<span class="pcard__by">Godrej Interio at HDE, Dehradun</span></div>')
site.product_card = card

posts = sorted([p for p in build.load_posts() if p["status"] != "approved"], key=lambda p: p["date"])
css = (ROOT / "static/assets/style.css").read_text(encoding="utf-8")
LOGO64 = base64.b64encode((ROOT / "static/assets/brand/hde-logo-192.png").read_bytes()).decode()
nav, arts = [], []
for i, p in enumerate(posts, 1):
    body, _ = site.render_body(p)
    faq = "".join(f'<details><summary>{E(f["q"])}</summary><p>{E(f["a"])}</p></details>' for f in p.get("faq") or [])
    ig = E(p.get("instagram") or "").replace("\n", "<br>")
    sid = f"d{i}"
    nav.append(f'<a href="#{sid}"><span>{p["date"].strftime("%a %d %b")}</span>{E(p.get("social_title") or p["title"])}</a>')
    arts.append(f"""<article class="post wrap wrap--narrow" id="{sid}">
<p class="crumbs">Draft {i} of {len(posts)} · goes live {p["date"].strftime("%A %d %B %Y")} · keyword: <strong>{E(p.get("keyword",""))}</strong></p>
<h1>{E(p["title"])}</h1>
<p class="post__meta">Google title: {E(p.get("seo_title",""))}<br>Description: {E(p["description"])}</p>
<div class="prose">{body}</div>
<section class="faq"><h2>Log ye bhi poochte hain</h2>{faq}</section>
{site.cta_box(p)}
<div class="ig"><strong>Instagram teaser caption</strong><p>{ig}</p></div>
</article>""")
page = f"""<title>Doon Home Guide Drafts</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,600;9..144,700&family=Inter:wght@400;500;600&display=swap">
<style>{css}
:root{{color-scheme:light}}
.top{{position:static}}.reviewhead{{background:#5e3116;color:#fff;padding-block:28px}}
.reviewhead h1{{color:#fff;margin:0 0 6px;font-size:30px}}.reviewhead p{{margin:0;opacity:.9;max-width:62ch}}
.drafts{{display:grid;gap:8px;margin-top:18px}}.drafts a{{color:#fff;text-decoration:none;display:flex;gap:12px;padding:10px 14px;border:1px solid rgba(255,255,255,.25);border-radius:10px}}
.drafts a span{{color:var(--gold);min-width:92px;font-variant-numeric:tabular-nums}}
.post{{border-bottom:6px solid var(--line);margin-bottom:24px}}
.ig{{background:var(--paper);border:1px dashed var(--line);border-radius:12px;padding:14px 18px;margin:20px 0;font-size:15px}}
</style>
<header class="reviewhead"><div class="wrap wrap--narrow">
<img src="data:image/png;base64,{LOGO64}" alt="Home Decor Enterprises logo" width="72" height="72" style="margin-bottom:14px">
<h1>Doon Home Guide: drafts for review</h1>
<p>Har draft padhiye aur thread mein "approve" likhiye ya jo badalna hai bataiye. Approve karne par post apni date par subah 6:15 baje live hoga aur usi din Instagram teaser jaayega. Product cards aur WhatsApp button live site par HDE se link honge.</p>
<nav class="drafts">{''.join(nav)}</nav></div></header>
{''.join(arts)}
<footer class="foot"><div class="wrap"><p class="foot__disc">Doon Home Guide by Home Decor Enterprises (HDE), Dehradun. Authorised Godrej Interio channel partner.</p></div></footer>"""
Path(sys.argv[1]).write_text(page, encoding="utf-8")
print("wrote", sys.argv[1], len(posts), "drafts")
