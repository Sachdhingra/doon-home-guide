# Doon Home Guide (uttarakhandhomes.in)

Dehradun/Uttarakhand home-living guide, run by Home Decor Enterprises (HDE).
Plain static site: Markdown posts in, HTML out. No database, no CMS.

## How a post goes live

1. **Draft** – Claude writes `content/posts/YYYY-MM-DD-slug.md` with `status: review`
   and pushes it. It appears at `/preview/<slug>/` (marked DRAFT, hidden from Google).
2. **Review** – Sachin reads the preview and replies in the project thread:
   "approve", or what to change.
3. **Approve** – Claude changes the post to `status: approved`. Approving a post also
   approves its Instagram teaser (the `instagram:` caption + `static/social/<slug>.jpg`).
4. **Publish** – every morning at 6:15 AM IST GitHub Actions rebuilds the site.
   Any approved post whose `date` has arrived goes live automatically and is added
   to the sitemap and RSS feed. The Instagram teaser goes out the same morning.

Nothing goes live without `status: approved`.

## Files

| Path | What |
|---|---|
| `site.yaml` | Site name, domain, WhatsApp, showroom, GA4 id, Search Console tag, `launched` switch |
| `content/posts/*.md` | Posts (front matter + Markdown) |
| `data/hde-products.json` | Snapshot of HDE's Godrej Interio catalogue (from Sachdhingra/hdewebsite) |
| `data/product-images/` | Product photos used in posts (copied from hdewebsite) |
| `static/` | CSS, JS, favicon, Instagram cards (`static/social/`) |
| `build.py` | The builder |
| `tools/make-social.js` | Makes 1080x1350 Instagram teaser cards |
| `.github/workflows/deploy.yml` | Build + deploy to GitHub Pages, daily 6:15 AM IST |

## Post front matter

```yaml
title: "..."            # H1
seo_title: "..."        # <title>, English keyword first
social_title: "..."     # short line for the Instagram card
slug: dhanteras-2026    # URL: /dhanteras-2026/
date: 2026-11-05        # go-live date
status: review          # review | approved
pillar: seasonal        # buying-guides | local | comparisons | real-projects | seasonal | home-tips
keyword: dhanteras 2026 # target keyword from the content plan
description: "..."      # meta description, ~155 characters
whatsapp: "Hi HDE, ..." # prefilled WhatsApp message (" (Doon Home Guide)" is added automatically)
cta: "..."              # line above the WhatsApp button
faq:                    # shown as "Log ye bhi poochte hain" + FAQ schema
  - q: "..."
    a: "..."
instagram: |            # teaser caption
  ...
```

Body shortcodes: `[[product:ID]]`, `[[products:ID,ID]]`, `[[cta]]`. IDs come from
`data/hde-products.json`; copy the photo `<id>.jpg` into `data/product-images/`.

## Build locally

```bash
pip install -r requirements.txt
python3 build.py                       # -> dist/
python3 build.py --today 2026-11-13    # see what is live on a given day
```

## Going live on the domain

1. GitHub repo Settings → Pages → Source: **GitHub Actions**.
2. Settings → Pages → Custom domain: `uttarakhandhomes.in`, tick Enforce HTTPS.
3. At the domain registrar: A records for `@` → 185.199.108.153, 185.199.109.153,
   185.199.110.153, 185.199.111.153, and CNAME `www` → `sachdhingra.github.io`.
4. In `site.yaml` set `launched: true` (removes noindex, opens robots.txt).
5. Add GA4 id and Search Console tag in `site.yaml`, submit `/sitemap.xml` in Search Console.

## Disclosure (ASCI)

Every page footer and every post end says the site is run by HDE, an authorised
Godrej Interio channel partner. HDE links carry `rel="sponsored"` and UTM tags
(`utm_source=doonhomeguide&utm_medium=blog&utm_campaign=<slug>`).
