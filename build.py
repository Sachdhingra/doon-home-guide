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
        price = f"MRP from ₹{p['from']:,}" if p.get("from") else "Price on request"
        img = Path(p["image"]).name
        src = ROOT / "data/product-images" / img
        if not src.exists():
            sys.exit(f"Product photo {img} missing: copy it from hdewebsite/site/assets/img/products/ into data/product-images/")
        dest = self.out / "assets/products" / img
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
        return (f'<a class="pcard" href="{E(link)}" data-track="hde_product" data-label="{E(pid)}" rel="sponsored">'
                f'<img src="/assets/products/{E(img)}" alt="{E(p["name"])}" loading="lazy" width="320" height="240">'
                f'<span class="pcard__name">{E(p["name"])}</span><span class="pcard__price">{price}</span>'
                f'<span class="pcard__by">Godrej Interio at HDE, Dehradun</span></a>')

    def cta_box(self, post):
        msg = post.get("whatsapp") or "Hi HDE, kuch poochna hai"
        msg += " (Doon Home Guide)"  # lets the sales team count leads that came from the blog
        text = post.get("cta") or "Sawal hai? HDE ki team WhatsApp par seedha jawab degi."
        return (f'<aside class="cta"><p>{E(text)}</p>'
                f'<a class="btn btn--wa" href="{E(self.wa(msg))}" data-track="whatsapp_click" data-label="{E(post["slug"])}" target="_blank" rel="noopener">WhatsApp par poochhein</a>'
                f'<a class="btn btn--ghost" href="{E(self.c["store_map"])}" data-track="directions_click" data-label="{E(post["slug"])}" target="_blank" rel="noopener">Showroom ka rasta</a></aside>')

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
        nav = "".join(f'<a href="/topics/{k}/">{E(v["name"])}</a>' for k, v in c["pillars"].items())
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
<meta name="theme-color" content="#2f5d50">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="alternate" type="application/rss+xml" title="{E(c['name'])}" href="/feed.xml">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,600;9..144,700&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/assets/style.css">
{head_extra}</head>
<body>
{banner}<header class="top"><div class="wrap top__in">
<a class="brand" href="/"><span class="brand__mark" aria-hidden="true"></span><span>{E(c['name'])}</span></a>
<nav class="nav" aria-label="Topics">{nav}</nav>
</div></header>
<main>{content}</main>
<footer class="foot"><div class="wrap">
<p class="foot__brand"><strong>{E(c['name'])}</strong> by {E(c['owner'])} ({E(c['owner_short'])}), Dehradun.</p>
<p class="foot__disc">Disclosure: Doon Home Guide {E(c['owner'])} chalata hai, jo {E(c['owner_line'])} hai. Kuch posts mein HDE ke products aur WhatsApp link hote hain. Hum comparisons mein dono taraf ke fayde-nuksaan likhte hain. <a href="/disclosure/">Poori disclosure</a></p>
<p class="foot__links"><a href="/about/">About</a> · <a href="/blog/">Saare articles</a> · <a href="/contact/">Contact</a> · <a href="/privacy/">Privacy</a> · <a href="/feed.xml">RSS</a></p>
<p class="foot__small">© {self.today.year} {E(c['owner'])}. {E(c['store_address'])}.</p>
</div></footer>
<a class="wa-float" href="{E(self.wa('Hi HDE, Doon Home Guide se aaya hoon'))}" data-track="whatsapp_click" data-label="float" target="_blank" rel="noopener" aria-label="WhatsApp HDE">WhatsApp</a>
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
        return (f'<article class="card card--{E(p["pillar"])}"><a href="{href}">'
                f'<span class="card__tag">{E(pil["name"])}</span><h3>{E(p["title"])}</h3>'
                f'<p>{E(p["description"])}</p><span class="card__date">{p["date"].strftime("%d %b %Y")}</span></a></article>')

    # ---------- pages ----------
    def post_page(self, p, live):
        c = self.c
        path = f"/{p['slug']}/" if live else f"/preview/{p['slug']}/"
        body, toc = self.render_body(p)
        pil = c["pillars"].get(p["pillar"], {"name": p["pillar"]})
        toc_html = ""
        if len(toc) >= 3:
            toc_html = '<nav class="toc" aria-label="Is article mein"><strong>Is article mein</strong><ol>' + "".join(
                f'<li><a href="#{t["id"]}">{E(html.unescape(t["name"]))}</a></li>' for t in toc) + "</ol></nav>"
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
            banner = (f'<div class="draft">DRAFT for review · status: {E(p["status"])} · planned date: {when} · '
                      f'file: {E(p["file"])}. Ye page Google par nahi dikhta.</div>')
        updated = ""
        if p["updated"] > p["date"]:
            updated = f' · Updated {p["updated"].strftime("%d %b %Y")}'
        content = f"""<article class="post wrap wrap--narrow">
<p class="crumbs"><a href="/">Home</a> › <a href="/topics/{E(p['pillar'])}/">{E(pil['name'])}</a></p>
<h1>{E(p['title'])}</h1>
<p class="post__meta">{E(c['name'])} team · {p['date'].strftime('%d %b %Y')}{updated} · {max(1, round(len(p['body'].split()) / 200))} min read</p>
{toc_html}
<div class="prose">{body}</div>
{faq_html}
{self.cta_box(p)}
<p class="post__disc">Ye article {E(c['name'])} ne likha hai, jo {E(c['owner'])} (HDE), Dehradun chalata hai. HDE {E(c['owner_line'])} hai, isliye kuch suggestions HDE ke products ke hain.</p>
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

        # home
        cards = "".join(self.card(p, f"/{p['slug']}/") for p in live[:9]) or '<p class="empty">Pehla article jald aa raha hai.</p>'
        pills = "".join(f'<a class="pill" href="/topics/{k}/"><strong>{E(v["name"])}</strong><span>{E(v["blurb"])}</span></a>' for k, v in c["pillars"].items())
        home = f"""<section class="hero"><div class="wrap">
<p class="hero__kicker">Dehradun · Mussoorie · Rishikesh · Haridwar</p>
<h1>Doon ke ghar ke liye <em>seedhi, kaam ki</em> salah</h1>
<p class="hero__lead">{E(c['tagline'])}. Furniture kaise chunein, mausam aur seelan se kaise bachayein, aur kaunsa area aapke liye sahi hai.</p>
<div class="hero__btns"><a class="btn btn--primary" href="/blog/">Articles padhein</a><a class="btn btn--wa" href="{E(self.wa('Hi HDE, Doon Home Guide se aaya hoon, ghar ke liye salah chahiye'))}" data-track="whatsapp_click" data-label="home_hero" target="_blank" rel="noopener">WhatsApp par poochhein</a></div>
</div></section>
<section class="wrap"><h2 class="sec">Naye articles</h2><div class="grid">{cards}</div></section>
<section class="wrap"><h2 class="sec">Topics</h2><div class="pills">{pills}</div></section>
<section class="wrap"><div class="store"><div><h2>Furniture dekh kar lena chahte hain?</h2><p>{E(c['store_name'])}: {E(c['store_address'])}. {E(c['store_hours'])}.</p></div>
<a class="btn btn--ghost" href="{E(c['store_map'])}" data-track="directions_click" data-label="home" target="_blank" rel="noopener">Google Maps par kholein</a></div></section>"""
        site_ld = [{"@context": "https://schema.org", "@type": "WebSite", "name": c["name"], "url": self.base + "/", "inLanguage": c["lang"],
                    "publisher": {"@type": "Organization", "name": c["owner"], "url": c["owner_url"]}}]
        self.page("/", f"{c['name']}: Dehradun home & furniture guide", f"{c['tagline']}. Buying guides, Dehradun local tips, comparisons aur festival planning.", home, jsonld=site_ld)
        urls.append(("/", self.today))

        # blog index + topics
        allc = "".join(self.card(p, f"/{p['slug']}/") for p in live) or '<p class="empty">Pehla article jald aa raha hai.</p>'
        self.page("/blog/", f"Saare articles | {c['name']}", "Doon Home Guide ke saare articles.", f'<section class="wrap"><h1 class="pagetitle">Saare articles</h1><div class="grid">{allc}</div></section>')
        urls.append(("/blog/", self.today))
        for k, v in c["pillars"].items():
            ps = [p for p in live if p["pillar"] == k]
            cards = "".join(self.card(p, f"/{p['slug']}/") for p in ps) or '<p class="empty">Is topic par articles jald aa rahe hain.</p>'
            self.page(f"/topics/{k}/", f"{v['name']} | {c['name']}", f"{v['blurb']} Dehradun aur Uttarakhand ke gharon ke liye.",
                      f'<section class="wrap"><h1 class="pagetitle">{E(v["name"])}</h1><p class="lead">{E(v["blurb"])}</p><div class="grid">{cards}</div></section>',
                      noindex=not ps)
            if ps:
                urls.append((f"/topics/{k}/", max(p["updated"] for p in ps)))

        # preview index (for owner review only)
        rows = "".join(f'<tr><td>{p["date"]}</td><td><a href="/preview/{p["slug"]}/">{E(p["title"])}</a></td><td>{E(p["status"])}</td></tr>' for p in pending)
        self.page("/preview/", "Drafts for review", "Drafts", f'<section class="wrap"><h1 class="pagetitle">Drafts for review</h1><div class="tablewrap"><table><tr><th>Planned</th><th>Title</th><th>Status</th></tr>{rows}</table></div></section>', noindex=True)

        # static info pages
        for slug, title, desc, md_text in self.info_pages():
            body = markdown.markdown(md_text, extensions=["sane_lists"])
            self.page(f"/{slug}/", f"{title} | {c['name']}", desc, f'<section class="wrap wrap--narrow prose"><h1 class="pagetitle">{E(title)}</h1>{body}</section>')
            urls.append((f"/{slug}/", self.today))

        self.page("/404.html", f"Page nahi mila | {c['name']}", "Page nahi mila", '<section class="wrap wrap--narrow"><h1 class="pagetitle">Ye page nahi mila</h1><p><a href="/">Home par jaayein</a> ya <a href="/blog/">saare articles</a> dekhein.</p></section>', noindex=True)

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
