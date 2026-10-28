// Makes a 1080x1350 Instagram teaser card (JPEG) for each post into static/social/<slug>.jpg.
//   node tools/make-social.js            (all posts that don't have a card yet)
//   node tools/make-social.js --force    (redo every card)
// Needs Playwright with Chromium. The card's text comes from the post's front matter:
// `social_title` if present, else `title`; `social_kicker` if present, else the pillar name.
const fs = require("fs"), path = require("path");
const { chromium } = require("playwright");
const ROOT = path.resolve(__dirname, "..");
const force = process.argv.includes("--force");
const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const field = (fm, k) => { const m = fm.match(new RegExp("^" + k + ':\\s*"?(.*?)"?\\s*$', "m")); return m ? m[1] : ""; };
const pillars = { "buying-guides": "Buying guide", local: "Dehradun local", comparisons: "Comparison", "real-projects": "Real project", seasonal: "Festival & season", "home-tips": "Home tips" };

(async () => {
  const outDir = path.join(ROOT, "static/social");
  fs.mkdirSync(outDir, { recursive: true });
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1080, height: 1350 } });
  for (const f of fs.readdirSync(path.join(ROOT, "content/posts")).filter(f => f.endsWith(".md")).sort()) {
    const fm = fs.readFileSync(path.join(ROOT, "content/posts", f), "utf8").split("\n---")[0];
    const slug = field(fm, "slug"), out = path.join(outDir, slug + ".jpg");
    if (!force && fs.existsSync(out)) continue;
    const title = field(fm, "social_title") || field(fm, "title");
    const kicker = field(fm, "social_kicker") || pillars[field(fm, "pillar")] || "";
    await page.setContent(`<!doctype html><html><head>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,700&family=Inter:wght@500;600&display=swap" rel="stylesheet">
<style>
body{margin:0;width:1080px;height:1350px;background:linear-gradient(160deg,#2f5d50,#1f3f36);color:#fff;font-family:Inter,sans-serif;display:flex;flex-direction:column;justify-content:space-between;padding:110px 96px 96px;box-sizing:border-box}
.k{font-size:34px;letter-spacing:.12em;text-transform:uppercase;color:#d9b56a;font-weight:600}
h1{font-family:Fraunces,serif;font-size:${title.length > 80 ? 76 : 88}px;line-height:1.1;margin:36px 0 0}
.b{display:flex;align-items:center;gap:24px;font-size:34px;border-top:2px solid rgba(255,255,255,.25);padding-top:40px}
.m{width:72px;height:72px;border-radius:18px;background:#faf7f2;display:grid;place-items:center}
.s{opacity:.8;font-size:28px;margin-top:6px}
</style></head><body>
<div><div class="k">${esc(kicker)}</div><h1>${esc(title)}</h1></div>
<div class="b"><div class="m"><svg width="48" height="48" viewBox="0 0 64 64"><path d="M14 34 32 18l18 16v14a2 2 0 0 1-2 2H16a2 2 0 0 1-2-2z" fill="#2f5d50"/><path d="M8 28 32 8l24 20" stroke="#d9b56a" stroke-width="5" fill="none" stroke-linecap="round"/><rect x="27" y="36" width="10" height="14" fill="#c2683c"/></svg></div>
<div><strong>Doon Home Guide</strong><div class="s">Poori guide: link in bio · by Home Decor Enterprises</div></div></div>
</body></html>`, { waitUntil: "networkidle" });
    await page.screenshot({ path: out, type: "jpeg", quality: 88 });
    console.log("made", path.relative(ROOT, out));
  }
  await browser.close();
})();
