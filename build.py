#!/usr/bin/env python3
"""Doon Home Guide static site builder.

    python3 build.py [--out DIR] [--today YYYY-MM-DD] [--url URL]

--url overrides site.yaml's url, e.g. the GitHub Pages address while the
domain is not connected yet. A sub-path (…github.io/doon-home-guide) works:
every internal link is prefixed with it.

Reads site.yaml, content/posts/*.md (YAML front matter + Markdown) and static/,
writes a ready-to-deploy folder (default ./dist).

A post goes live only when its front matter has `status: approved` AND its
`date` is today or earlier (India time). Every other post is built under
/preview/<slug>/ with a DRAFT banner and noindex, for the owner to review.

Body shortcodes (each on its own line):
    [[product:ID]]          one HDE product card (ID from data/hde-products.json)
    [[products:ID,ID,ID]]   a row of product cards
    [[cta]]                 the post's WhatsApp box

Product photos are served from this site: copy <id>.jpg from
hdewebsite/site/assets/img/products/ into data/product-images/ before building.
"""
import argparse, datetime as dt, html, json, re, shutil, sys
from pathlib import Path
from urllib.parse import quote, urlencode, urlparse, parse_qsl, urlunparse
import markdown, yaml

ROOT = Path(__file__).resolve().parent
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
E = html.escape
WA_ICON = ('<svg class="ico" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path fill="currentColor" d="M12 2a10 10 0 0 0-8.6 15.1L2 22l5-1.3A10 10 0 1 0 12 2Zm0 18.2a8.2 8.2 0 0 1-4.2-1.2l-.3-.2-3 .8.8-2.9-.2-.3A8.2 8.2 0 1 1 12 20.2Zm4.5-6.1c-.2-.1-1.5-.7-1.7-.8-.2-.1-.4-.1-.6.1l-.8 1c-.1.2-.3.2-.5.1a6.7 6.7 0 0 1-3.3-2.9c-.2-.4.3-.4.8-1.3.1-.2 0-.3 0-.4l-.8-1.8c-.2-.5-.4-.4-.6-.4h-.5a1 1 0 0 0-.7.3 3 3 0 0 0-.9 2.2 5.2 5.2 0 0 0 1.1 2.8 11.9 11.9 0 0 0 4.6 4c1.7.7 2.4.8 3.2.7.5-.1 1.5-.6 1.8-1.2.2-.6.2-1.1.1-1.2l-.5-.3Z"/></svg>')
LOGO = ('<svg viewBox="0 0 40 40" aria-hidden="true" focusable="false"><path d="M8 19 20 9l12 10v12a1.5 1.5 0 0 1-1.5 1.5h-21A1.5 1.5 0 0 1 8 31Z" fill="currentColor" opacity=".14"/>'
        '<path d="M5 18 20 6l15 12" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>'
        '<path d="M16.5 32.5v-8h7v8" fill="none" stroke="var(--brass)" stroke-width="2.4" stroke-linejoin="round"/></svg>')


def load_posts():
    posts = []
    for f in sorted((ROOT / "content/posts").glob("*.md")):
        raw = f.read_text(encoding="utf-8")
        m = re.match(r"^---\n(.*?)\n---\n(.*)$", raw, re.S)
        if not m:
            sys.exit(f"{f.name}: missing front matter")
        meta = yaml.safe_load(m.group(1)) or {}
        for k in ("title", "slug", "date", "status", "pillar", "description"):
            if not meta.get(k):
                sys.exit(f"{f.name}: front matter needs '{k}'")
        meta["date"] = dt.date.fromisoformat(str(meta["date"]))
        meta["updated"] = dt.date.fromisoformat(str(meta.get("updated") or meta["date"]))
        meta["body"] = m.group(2)
        meta["file"] = f.name
        posts.append(meta)
    return posts


class Site:
    def __init__(self, cfg, products, today, out):
        self.c, self.products, self.today, self.out = cfg, products, today, out
        self.base = cfg["url"].rstrip("/")
        self.root = urlparse(self.base).path.rstrip("/")  # "" on a domain, "/repo" on a project site

    # ---------- helpers ----------
    @staticmethod
    def inr(n):
        """₹ in Indian grouping: 186056 -> 1,86,056"""
        s = str(int(n))
        if len(s) <= 3:
            return s
        head, tail = s[:-3], s[-3:]
        head = re.sub(r"(\d)(?=(\d{2})+$)", r"\1,", head)
        return f"{head},{tail}"

    def read_min(self, p):
        return max(1, round(len(p["body"].split()) / 200))

    def cover(self, p):
        """Photo for cards and the post header: `cover:` product id, else the first product in the post."""
        pid = p.get("cover")
        if not pid:
            m = re.search(r"\[\[products?:([\w-]+)", p["body"])
            pid = m.group(1) if m else None
        if not pid or pid not in self.products:
            return None, None
        img = Path(self.products[pid]["image"]).name
        src = ROOT / "data/product-images" / img
        if not src.exists():
            return None, None
        dest = self.out / "assets/products" / img
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
        return f"/assets/products/{img}", self.products[pid]["name"]

    def wa(self, msg):
        return f"https://wa.me/{self.c['whatsapp']}?text={quote(msg)}"

    def utm(self, url, campaign):
        if "hdefurniture.netlify.app" not in url:
            return url
        p = urlparse(url)
        q = dict(parse_qsl(p.query))
        q.update(utm_source="doonhomeguide", utm_medium="blog", utm_campaign=campaign)
        return urlunparse(p._replace(query=urlencode(q)))

    def product_card(self, pid, campaign):
        p = self.products.get(pid)
        if not p:
            sys.exit(f"Unknown product id {pid}")
        owner = self.c["owner_url"].rstrip("/")
        link = self.utm(f"{owner}/product.html?id={pid}", campaign)
        price = f"MRP from <span class=\"num\">₹{self.inr(p['from'])}</span>" if p.get("from") else "Price on request"
        img = Path(p["image"]).name
        src = ROOT / "data/product-images" / img
        if not src.exists():
            sys.exit(f"Product photo {img} missing: copy it from hdewebsite/site/assets/img/products/ into data/product-images/")
        dest = self.out / "assets/products" / img
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
        return (f'<a class="pcard" href="{E(link)}" data-track="hde_product" data-label="{E(pid)}" rel="sponsored">'
                f'<span class="pcard__img"><img src="/assets/products/{E(img)}" alt="{E(p["name"])}" loading="lazy" width="320" height="240"></span>'
                f'<span class="pcard__body"><span class="pcard__brand">Godrej Interio</span><span class="pcard__name">{E(p["name"])}</span>'
                f'<span class="pcard__price">{price}</span><span class="pcard__go">HDE par dekhein <span aria-hidden="true">→</span></span></span></a>')

    def cta_box(self, post):
        msg = post.get("whatsapp") or "Hi HDE, kuch poochna hai"
        msg += " (Doon Home Guide)"  # lets the sales team count leads that came from the blog
        text = post.get("cta") or "Sawal hai? HDE ki team WhatsApp par seedha jawab degi."
        c = self.c
        return (f'<aside class="cta"><div class="cta__text"><span class="eyebrow">HDE se poochhein</span><p>{E(text)}</p>'
                f'<span class="cta__meta">{E(c["store_name"])} · {E(c["store_hours"])}</span></div>'
                f'<div class="cta__btns"><a class="btn btn--wa" href="{E(self.wa(msg))}" data-track="whatsapp_click" data-label="{E(post["slug"])}" target="_blank" rel="noopener">{WA_ICON}WhatsApp par poochhein</a>'
                f'<a class="btn btn--line" href="{E(c["store_map"])}" data-track="directions_click" data-label="{E(post["slug"])}" target="_blank" rel="noopener">Showroom ka rasta</a></div></aside>')

    def render_body(self, post):
        camp = post["slug"]
        lines = []
        for line in post["body"].split("\n"):
            s = line.strip()
            if m := re.fullmatch(r"\[\[product:([\w-]+)\]\]", s):
                lines.append(f'<div class="pgrid pgrid--one">{self.product_card(m.group(1), camp)}</div>')
            elif m := re.fullmatch(r"\[\[products:([\w,\s-]+)\]\]", s):
                cards = "".join(self.product_card(i.strip(), camp) for i in m.group(1).split(","))
                lines.append(f'<div class="pgrid">{cards}</div>')
            elif s == "[[cta]]":
                lines.append(self.cta_box(post))
            else:
                lines.append(line)
        md = markdown.Markdown(extensions=["tables", "attr_list", "toc", "sane_lists"],
                               extension_configs={"toc": {"toc_depth": "2-2"}})
        body = md.convert("\n".join(lines))
        # UTM-tag links to the HDE site and mark them sponsored
        body = re.sub(r'href="(https://hdefurniture\.netlify\.app[^"]*)"',
                      lambda m: f'href="{E(self.utm(html.unescape(m.group(1)), camp))}" rel="sponsored" data-track="hde_link" data-label="{camp}"', body)
        body = body.replace("<table>", '<div class="tablewrap"><table>').replace("</table>", "</table></div>")
        return body, md.toc_tokens

    # ---------- layout ----------
    def page(self, path, title, desc, content, *, noindex=False, jsonld=None, og_type="website", banner=""):
        c = self.c
        canonical = self.base + path
        noindex = noindex or not c.get("launched")
        head_extra = ""
        if noindex:
            head_extra += '<meta name="robots" content="noindex, nofollow">\n'
        if c.get("gsc_verification"):
            head_extra += f'<meta name="google-site-verification" content="{E(c["gsc_verification"])}">\n'
        if c.get("ga4_id"):
            g = E(c["ga4_id"])
            head_extra += (f'<script async src="https://www.googletagmanager.com/gtag/js?id={g}"></script>\n'
                           f"<script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments)}}gtag('js',new Date());gtag('config','{g}');</script>\n")
        for j in jsonld or []:
            head_extra += f'<script type="application/ld+json">{json.dumps(j, ensure_ascii=False)}</script>\n'
        nav = "".join(f'<a href="/topics/{k}/"{" aria-current=\"page\"" if path == f"/topics/{k}/" else ""}>{E(v["name"])}</a>' for k, v in c["pillars"].items())
        doc = f"""<!doctype html>
<html lang="{c['lang']}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{E(title)}</title>
<meta name="description" content="{E(desc)}">
<link rel="canonical" href="{E(canonical)}">
<meta property="og:title" content="{E(title)}">
<meta property="og:description" content="{E(desc)}">
<meta property="og:type" content="{og_type}">
<meta property="og:url" content="{E(canonical)}">
<meta property="og:site_name" content="{E(c['name'])}">
<meta name="theme-color" content="#f6f1ea" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#16120f" media="(prefers-color-scheme: dark)">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="alternate" type="application/rss+xml" title="{E(c['name'])}" href="/feed.xml">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,500;6..72,600&family=Instrument+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@500&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/assets/style.css">
{head_extra}</head>
<body>
<a class="skip" href="#main">Seedha article par jaayein</a>
{banner}<header class="top"><div class="wrap top__in">
<a class="brand" href="/" aria-label="{E(c['name'])} home"><span class="brand__mark" aria-hidden="true">{LOGO}</span><span class="brand__name">{E(c['name'])}<span class="brand__by">by {E(c['owner'])}</span></span></a>
<nav class="nav" aria-label="Topics">{nav}</nav>
</div></header>
<main id="main">{content}</main>
<footer class="foot"><div class="wrap foot__grid">
<div class="foot__about"><p class="foot__brand">{E(c['name'])}</p>
<p>Dehradun aur Uttarakhand ke gharon ke liye seedhi salah. {E(c['owner'])} ({E(c['owner_short'])}) ki ek pahal.</p>
<p class="foot__disc"><strong>Disclosure:</strong> ye site {E(c['owner'])} chalata hai, jo {E(c['owner_line'])} hai. Kuch posts mein HDE ke products aur WhatsApp link hote hain. Comparisons mein hum dono taraf ke fayde-nuksaan likhte hain. <a href="/disclosure/">Poori disclosure</a></p></div>
<nav class="foot__col" aria-label="Topics"><p class="foot__h">Topics</p>{nav}</nav>
<div class="foot__col"><p class="foot__h">Showroom</p><p>{E(c['store_address'])}</p><p>{E(c['store_hours'])}</p><a href="{E(c['store_map'])}" target="_blank" rel="noopener" data-track="directions_click" data-label="footer">Google Maps</a><a href="https://wa.me/{c['whatsapp']}" target="_blank" rel="noopener" data-track="whatsapp_click" data-label="footer">{E(c['phone'])}</a></div>
<div class="foot__base"><span>© {self.today.year} {E(c['owner'])}</span><span><a href="/about/">About</a> · <a href="/contact/">Contact</a> · <a href="/privacy/">Privacy</a> · <a href="/feed.xml">RSS</a></span></div>
</div></footer>
<a class="wa-float" href="{E(self.wa('Hi HDE, Doon Home Guide se aaya hoon'))}" data-track="whatsapp_click" data-label="float" target="_blank" rel="noopener" aria-label="WhatsApp par HDE se baat karein">{WA_ICON}<span>WhatsApp</span></a>
<script src="/assets/site.js" defer></script>
</body></html>"""
        self.write(path, doc)
        return canonical

    def write(self, path, text):
        if self.root:
            text = re.sub(r'(href|src)="/(?!/)', rf'\1="{self.root}/', text)
        f = self.out / (path.strip("/") + "/index.html" if path.endswith("/") else path.lstrip("/"))
        if path == "/":
            f = self.out / "index.html"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding="utf-8")

    def card(self, p, href):
        pil = self.c["pillars"].get(p["pillar"], {"name": p["pillar"]})
        img, alt = self.cover(p)
        pic = f'<span class="card__img"><img src="{img}" alt="" loading="lazy" width="480" height="360"></span>' if img else ""
        draft = '<span class="badge">Draft</span>' if href.startswith("/preview/") else ""
        return (f'<article class="card"><a href="{href}">{pic}<span class="card__body">'
                f'<span class="card__meta"><span class="eyebrow">{E(pil["name"])}</span>{draft}</span>'
                f'<h3>{E(p.get("social_title") or p["title"])}</h3><p>{E(p["description"])}</p>'
                f'<span class="card__foot"><time datetime="{p["date"].isoformat()}">{p["date"].strftime("%d %b %Y")}</time> · {self.read_min(p)} min read</span>'
                f'</span></a></article>')

    # ---------- pages ----------
    def post_page(self, p, live):
        c = self.c
        path = f"/{p['slug']}/" if live else f"/preview/{p['slug']}/"
        body, toc = self.render_body(p)
        pil = c["pillars"].get(p["pillar"], {"name": p["pillar"]})
        toc_html = ""
        if len(toc) >= 3:
            toc_html = '<details class="toc" open><summary>Is article mein</summary><ol>' + "".join(
                f'<li><a href="#{t["id"]}">{E(html.unescape(t["name"]))}</a></li>' for t in toc) + "</ol></details>"
        faq = p.get("faq") or []
        faq_html = ""
        if faq:
            faq_html = '<section class="faq"><h2 id="faq">Log ye bhi poochte hain</h2>' + "".join(
                f'<details><summary>{E(f["q"])}</summary><p>{E(f["a"])}</p></details>' for f in faq) + "</section>"
        url = self.base + f"/{p['slug']}/"
        jsonld = [{
            "@context": "https://schema.org", "@type": "BlogPosting", "headline": p["title"],
            "description": p["description"], "datePublished": p["date"].isoformat(),
            "dateModified": p["updated"].isoformat(), "mainEntityOfPage": url, "inLanguage": c["lang"],
            "author": {"@type": "Organization", "name": f"{c['name']} team"},
            "publisher": {"@type": "Organization", "name": c["owner"], "url": c["owner_url"]},
        }, {
            "@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": c["name"], "item": self.base + "/"},
                {"@type": "ListItem", "position": 2, "name": pil["name"], "item": self.base + f"/topics/{p['pillar']}/"},
                {"@type": "ListItem", "position": 3, "name": p["title"], "item": url}]}]
        if faq:
            jsonld.append({"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
                {"@type": "Question", "name": f["q"], "acceptedAnswer": {"@type": "Answer", "text": f["a"]}} for f in faq]})
        banner = ""
        if not live:
            when = p["date"].strftime("%d %b %Y")
            banner = (f'<div class="draft" role="status"><strong>Draft for review</strong> · live hoga {when} ko (approve ke baad) · '
                      f'file: {E(p["file"])} · Google par nahi dikhta</div>')
        updated = ""
        if p["updated"] > p["date"]:
            updated = f'<span>Updated {p["updated"].strftime("%d %b %Y")}</span>'
        img, alt = self.cover(p)
        figure = f'<figure class="post__cover"><img src="{img}" alt="{E(alt)}" width="640" height="480"></figure>' if img else ""
        content = f"""<article class="post">
<header class="post__head"><div class="wrap post__headin">
<div class="post__titles"><nav class="crumbs" aria-label="Breadcrumb"><a href="/">Home</a><span aria-hidden="true">/</span><a href="/topics/{E(p['pillar'])}/">{E(pil['name'])}</a></nav>
<h1>{E(p['title'])}</h1>
<p class="post__lede">{E(p['description'])}</p>
<p class="post__meta"><span>{E(c['name'])} team</span><time datetime="{p['date'].isoformat()}">{p['date'].strftime('%d %b %Y')}</time>{updated}<span>{self.read_min(p)} min read</span></p></div>
{figure}</div></header>
<div class="wrap post__grid">
<aside class="post__aside">{toc_html}</aside>
<div class="post__main">
<div class="prose">{body}</div>
{faq_html}
{self.cta_box(p)}
<p class="post__disc">Ye article {E(c['name'])} ne likha hai, jo {E(c['owner'])} (HDE), Dehradun chalata hai. HDE {E(c['owner_line'])} hai, isliye kuch suggestions HDE ke products ke hain.</p>
</div></div>
</article>"""
        seo_title = p.get("seo_title") or f"{p['title']} | {c['name']}"
        self.page(path, seo_title, p["description"], content, noindex=not live, jsonld=jsonld, og_type="article", banner=banner)
        return path

    def build(self, posts):
        c = self.c
        if self.out.exists():
            shutil.rmtree(self.out)
        shutil.copytree(ROOT / "static", self.out)
        live = sorted([p for p in posts if p["status"] == "approved" and p["date"] <= self.today],
                      key=lambda p: p["date"], reverse=True)
        pending = sorted([p for p in posts if p not in live], key=lambda p: p["date"])
        urls = []
        for p in live:
            self.post_page(p, True)
            urls.append((f"/{p['slug']}/", p["updated"]))
        for p in pending:
            self.post_page(p, False)

        # home. Before launch the drafts stand in for articles so the owner can review the whole site.
        shown = [(p, f"/{p['slug']}/") for p in live]
        if not c.get("launched"):
            shown += [(p, f"/preview/{p['slug']}/") for p in pending]
        empty = '<div class="empty"><p class="empty__h">Pehla article jald aa raha hai</p><p>Har Monday aur Thursday naya article. Tab tak sawal ho to WhatsApp kijiye.</p></div>'
        feat_html, rest = "", shown
        if shown:
            fp, fh = shown[0]
            fimg, falt = self.cover(fp)
            fpil = c["pillars"].get(fp["pillar"], {"name": fp["pillar"]})
            feat_html = (f'<a class="feature" href="{fh}">' + (f'<span class="feature__img"><img src="{fimg}" alt="{E(falt)}" width="640" height="480"></span>' if fimg else "")
                         + f'<span class="feature__body"><span class="eyebrow">{E(fpil["name"])} · {fp["date"].strftime("%d %b")}</span>'
                         f'<span class="feature__title">{E(fp.get("social_title") or fp["title"])}</span>'
                         f'<span class="feature__go">Padhiye <span aria-hidden="true">→</span></span></span></a>')
            rest = shown[1:]
        cards = "".join(self.card(p, h) for p, h in rest[:9])
        upcoming = sorted((d for d in c.get("dates") or [] if dt.date.fromisoformat(str(d["date"])) >= self.today), key=lambda d: str(d["date"]))[:4]
        dates = "".join(f'<li><time datetime="{d["date"]}">{dt.date.fromisoformat(str(d["date"])).strftime("%d %b")}</time><span>{E(d["what"])}</span></li>' for d in upcoming)
        ribbon = f'<section class="ribbon" aria-label="Aane wale din"><div class="wrap ribbon__in"><span class="eyebrow">Aane wale din</span><ul>{dates}</ul></div></section>' if dates else ""
        pills = "".join(f'<a class="pill" href="/topics/{k}/"><span class="pill__n">{i:02d}</span><strong>{E(v["name"])}</strong><span>{E(v["blurb"])}</span></a>' for i, (k, v) in enumerate(c["pillars"].items(), 1))
        home = f"""<section class="hero"><div class="wrap hero__in">
<div class="hero__text"><p class="eyebrow">Dehradun · Mussoorie · Rishikesh · Haridwar</p>
<h1>Doon ke ghar ke liye <em>seedhi, kaam ki</em> salah</h1>
<p class="hero__lead">Furniture kaise chunein, seelan aur deemak se kaise bachayein, aur shaadi ya griha pravesh ki planning kaise karein. Sab Dehradun ke mausam aur gharon ke hisaab se.</p>
<div class="hero__btns"><a class="btn btn--solid" href="/blog/">Articles padhein</a><a class="btn btn--wa" href="{E(self.wa('Hi HDE, Doon Home Guide se aaya hoon, ghar ke liye salah chahiye'))}" data-track="whatsapp_click" data-label="home_hero" target="_blank" rel="noopener">{WA_ICON}WhatsApp par poochhein</a></div></div>
{feat_html}
</div></section>
{ribbon}
<section class="wrap block"><div class="block__head"><h2>Naye articles</h2><a href="/blog/">Saare articles <span aria-hidden="true">→</span></a></div>{f'<div class="grid">{cards}</div>' if cards else ('' if feat_html else empty)}</section>
<section class="wrap block"><div class="block__head"><h2>Topics</h2></div><div class="pills">{pills}</div></section>
<section class="wrap block"><div class="store"><div class="store__text"><span class="eyebrow">Showroom</span><h2>Furniture chhookar, baith kar dekhna hai?</h2><p>{E(c['store_name'])}, {E(c['store_address'])}. {E(c['store_hours'])}.</p></div>
<div class="store__btns"><a class="btn btn--solid" href="{E(c['store_map'])}" data-track="directions_click" data-label="home" target="_blank" rel="noopener">Google Maps par kholein</a><a class="btn btn--line" href="https://wa.me/{c['whatsapp']}" data-track="whatsapp_click" data-label="home_store" target="_blank" rel="noopener">{E(c['phone'])}</a></div></div></section>"""
        site_ld = [{"@context": "https://schema.org", "@type": "WebSite", "name": c["name"], "url": self.base + "/", "inLanguage": c["lang"],
                    "publisher": {"@type": "Organization", "name": c["owner"], "url": c["owner_url"]}}]
        self.page("/", f"{c['name']}: Dehradun home & furniture guide", f"{c['tagline']}. Buying guides, Dehradun local tips, comparisons aur festival planning.", home, jsonld=site_ld)
        urls.append(("/", self.today))

        # blog index + topics
        allc = "".join(self.card(p, h) for p, h in shown)
        self.page("/blog/", f"Saare articles | {c['name']}", "Doon Home Guide ke saare articles.",
                  f'<section class="wrap block"><h1 class="pagetitle">Saare articles</h1><p class="lead">Buying guides, Dehradun local tips, comparisons aur festival planning.</p>{f"<div class=grid>{allc}</div>" if allc else empty}</section>')
        urls.append(("/blog/", self.today))
        for k, v in c["pillars"].items():
            ps = [p for p in live if p["pillar"] == k]
            tcards = "".join(self.card(p, h) for p, h in shown if p["pillar"] == k)
            tempty = '<div class="empty"><p class="empty__h">Is topic par articles jald aa rahe hain</p><p>Tab tak <a href="/blog/">saare articles</a> dekhiye.</p></div>'
            self.page(f"/topics/{k}/", f"{v['name']} | {c['name']}", f"{v['blurb']} Dehradun aur Uttarakhand ke gharon ke liye.",
                      f'<section class="wrap block"><p class="eyebrow">Topic</p><h1 class="pagetitle">{E(v["name"])}</h1><p class="lead">{E(v["blurb"])}</p>{f"<div class=grid>{tcards}</div>" if tcards else tempty}</section>',
                      noindex=not ps)
            if ps:
                urls.append((f"/topics/{k}/", max(p["updated"] for p in ps)))

        # preview index (for owner review only)
        rows = "".join(f'<tr><td>{p["date"]}</td><td><a href="/preview/{p["slug"]}/">{E(p["title"])}</a></td><td>{E(p["status"])}</td></tr>' for p in pending)
        self.page("/preview/", "Drafts for review", "Drafts", f'<section class="wrap block"><h1 class="pagetitle">Drafts for review</h1><div class="tablewrap"><table><tr><th>Planned</th><th>Title</th><th>Status</th></tr>{rows}</table></div></section>', noindex=True)

        # static info pages
        for slug, title, desc, md_text in self.info_pages():
            body = markdown.markdown(md_text, extensions=["sane_lists"])
            self.page(f"/{slug}/", f"{title} | {c['name']}", desc, f'<section class="wrap wrap--narrow block"><h1 class="pagetitle">{E(title)}</h1><div class="prose">{body}</div></section>')
            urls.append((f"/{slug}/", self.today))

        self.page("/404.html", f"Page nahi mila | {c['name']}", "Page nahi mila", '<section class="wrap wrap--narrow block"><h1 class="pagetitle">Ye page nahi mila</h1><p><a href="/">Home par jaayein</a> ya <a href="/blog/">saare articles</a> dekhein.</p></section>', noindex=True)

        # sitemap, robots, feed
        sm = "".join(f"<url><loc>{E(self.base + u)}</loc><lastmod>{d.isoformat()}</lastmod></url>" for u, d in urls)
        (self.out / "sitemap.xml").write_text(f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{sm}</urlset>\n', encoding="utf-8")
        if c.get("launched"):
            robots = f"User-agent: *\nAllow: /\nDisallow: /preview/\n\nSitemap: {self.base}/sitemap.xml\n"
        else:
            robots = "# Preview phase: not open to search engines yet.\nUser-agent: *\nDisallow: /\n"
        (self.out / "robots.txt").write_text(robots, encoding="utf-8")
        if c.get("launched") and not self.root:
            (self.out / "CNAME").write_text(urlparse(self.base).hostname + "\n", encoding="utf-8")
        (self.out / ".nojekyll").write_text("", encoding="utf-8")
        items = "".join(
            f"<item><title>{E(p['title'])}</title><link>{self.base}/{p['slug']}/</link><guid>{self.base}/{p['slug']}/</guid>"
            f"<pubDate>{dt.datetime.combine(p['date'], dt.time(8), IST).strftime('%a, %d %b %Y %H:%M:%S %z')}</pubDate>"
            f"<description>{E(p['description'])}</description></item>" for p in live[:20])
        (self.out / "feed.xml").write_text(
            f'<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel><title>{E(c["name"])}</title><link>{self.base}/</link>'
            f'<description>{E(c["tagline"])}</description><language>en-in</language>{items}</channel></rss>\n', encoding="utf-8")
        (self.out / "build.json").write_text(json.dumps({
            "built": dt.datetime.now(IST).isoformat(timespec="seconds"), "today": self.today.isoformat(),
            "live": [p["slug"] for p in live], "preview": [p["slug"] for p in pending]}, indent=1), encoding="utf-8")
        return live, pending

    def info_pages(self):
        c = self.c
        return [
            ("about", "About Doon Home Guide", "Doon Home Guide kya hai aur kaun chalata hai.", f"""
Doon Home Guide Dehradun aur Uttarakhand ke gharon ke liye ek seedhi, kaam ki guide hai: furniture kaise chunein, Doon ke mausam aur seelan mein ghar kaise sambhalein, naye flat ki planning, aur festival season ki kharidari.

**Kaun chalata hai:** ye site [{c['owner']}]({c['owner_url']}) (HDE) chalata hai. HDE {c['owner_line']} hai. Hum roz showroom mein jo sawal sunte hain, unhi ke jawab yahan likhte hain.

**Humara vaada:**

- Comparisons mein dono taraf ke fayde aur nuksaan likhenge, chahe wo cheez HDE na bechta ho.
- Price hamesha "MRP from" ya range ke roop mein denge, aur likhenge ki final price showroom se confirm karein.
- Har article par likha hoga ki ye HDE ki site hai.

Koi galti dikhe ya kisi topic par article chahiye, to [WhatsApp karein](https://wa.me/{c['whatsapp']}).
"""),
            ("disclosure", "Disclosure", "Doon Home Guide ka ownership aur advertising disclosure.", f"""
Doon Home Guide ko **{c['owner']} (HDE), Dehradun** chalata hai. HDE {c['owner_line']} hai aur furniture, mattresses, modular kitchens aur storage bechta hai.

- Jin articles mein HDE ke products, product cards, ya WhatsApp/showroom links hain, wo HDE ka promotion hain. Aise links par `rel="sponsored"` laga hai.
- Hum kisi aur brand se paise lekar review nahi likhte.
- Prices "MRP from" ke roop mein HDE ke catalogue se li jaati hain aur badal sakti hain.
- Muhurat, vastu aur health se jude articles general jaankari ke liye hain. Apne pandit, expert ya doctor se confirm karein.

Ye disclosure ASCI ke influencer aur native advertising guidelines ke hisaab se hai.
"""),
            ("contact", "Contact", "Doon Home Guide aur HDE se sampark.", f"""
- **WhatsApp / call:** [{c['phone']}](https://wa.me/{c['whatsapp']})
- **Showroom:** {c['store_address']}. {c['store_hours']}. [Google Maps]({c['store_map']})
- **Instagram:** [{c['instagram']}]({c['instagram']})
"""),
            ("privacy", "Privacy policy", "Doon Home Guide privacy policy.", """
- Ye site koi account ya form nahi rakhti. Aap WhatsApp par message karte hain to wo seedha HDE ke WhatsApp number par jaata hai.
- Hum Google Analytics se anonymous visit data (kaunsa page padha, kahan se aaye) dekhte hain taaki behtar articles likh sakein. Isme cookies use ho sakti hain.
- Aap apne browser mein cookies band kar sakte hain.
- Sawal ho to Contact page par diye number par WhatsApp karein.
"""),
        ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "dist"))
    ap.add_argument("--today", help="override today's date (YYYY-MM-DD) for testing")
    ap.add_argument("--url", help="override site.yaml url (e.g. the GitHub Pages address)")
    a = ap.parse_args()
    cfg = yaml.safe_load((ROOT / "site.yaml").read_text(encoding="utf-8"))
    if a.url:
        cfg["url"] = a.url
    products = json.loads((ROOT / "data/hde-products.json").read_text(encoding="utf-8"))["products"]
    today = dt.date.fromisoformat(a.today) if a.today else dt.datetime.now(IST).date()
    live, pending = Site(cfg, products, today, Path(a.out)).build(load_posts())
    print(f"Built {a.out}: {len(live)} live, {len(pending)} preview (today {today}, launched={cfg.get('launched')})")
    for p in live:
        print("  LIVE    ", p["date"], p["slug"])
    for p in pending:
        print("  PREVIEW ", p["date"], p["status"], p["slug"])


if __name__ == "__main__":
    main()
