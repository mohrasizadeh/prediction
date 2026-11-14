// One page that shows every screen beside its measured numbers, so a review can be done in order
// and can cite evidence. Reads inventory.json; writes docs/redesign/v11/index.html.
const fs = require('fs'); const path = require('path');
const ROOT = path.join(__dirname, '..', 'docs', 'redesign', 'v11');
const inv = JSON.parse(fs.readFileSync(path.join(ROOT, 'inventory.json')));
const by = {};
for (const p of inv.pages) (by[p.key] ||= {})[p.viewport] = p;
const esc = (s) => String(s).replace(/[<>&]/g, (c) => ({ '<': '&lt;', '>': '&gt;', '&': '&amp;' }[c]));
const card = (key) => {
  const ph = by[key].phone, dk = by[key].desk, i = (ph || dk).inventory;
  const flag = (n, label) => (n ? `<b class="w">${n} ${label}</b>` : '');
  return `<section id="${key}">
    <h2>${esc(key)} <small>${esc((ph || dk).route)} &middot; ${(ph || dk).group}</small></h2>
    <p class="m">${flag(i.smallTapTargets.length, 'tap targets &lt;44px')} ${flag(i.tinyText.length, 'text &lt;12px')}
      ${i.horizontalOverflow ? '<b class="w">horizontal overflow</b>' : ''}
      ${flag((ph || dk).errors.length, 'JS errors')}
      <span>${Object.keys(i.fontSizes).length} font sizes</span>
      <span>${Object.keys(i.backgrounds).length} backgrounds</span>
      <span>${Object.keys(i.radii).length} radii</span>
      <span>${Object.keys(i.gaps).length} gaps</span>
      <span>${i.counts.elements} elements</span></p>
    <div class="pair">
      ${ph ? `<figure><figcaption>phone 390 &mdash; first screen</figcaption><img loading="lazy" src="fold/${key}.phone.png"></figure>` : ''}
      ${dk ? `<figure class="d"><figcaption>desktop 1440 &mdash; first screen</figcaption><img loading="lazy" src="fold/${key}.desk.png"></figure>` : ''}
    </div>
    <p class="l">full page: ${ph ? `<a href="shots/${key}.phone.png">phone</a>` : ''} ${dk ? `<a href="shots/${key}.desk.png">desktop</a>` : ''}
       &middot; standalone html: ${ph ? `<a href="html/${key}.phone.html">phone</a>` : ''} ${dk ? `<a href="html/${key}.desk.html">desktop</a>` : ''}</p>
  </section>`;
};
const keys = Object.keys(by).sort((a, b) => (by[a].phone || by[a].desk).group.localeCompare((by[b].phone || by[b].desk).group) || a.localeCompare(b));
fs.writeFileSync(path.join(ROOT, 'index.html'), `<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Screen inventory</title><style>
:root{--bg:#fff;--fg:#111;--mut:#667;--line:#e3e6ea;--warn:#a4401a}
@media(prefers-color-scheme:dark){:root{--bg:#14161a;--fg:#e8eaed;--mut:#9aa3ad;--line:#2a2f36}}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,-apple-system,sans-serif}
.wrap{max-width:1180px;margin:0 auto;padding:24px 16px 80px}
h1{font-size:24px;margin:0 0 4px} .sub{color:var(--mut);margin:0 0 24px}
nav{position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--line);padding:10px 0;margin-bottom:20px;z-index:5}
nav a{color:var(--fg);text-decoration:none;font-size:12.5px;margin-right:10px;white-space:nowrap}
nav a:hover{text-decoration:underline}
section{border-top:1px solid var(--line);padding:22px 0}
h2{font-size:17px;margin:0 0 6px} h2 small{color:var(--mut);font-weight:400;font-size:13px}
.m{margin:0 0 12px;display:flex;gap:10px;flex-wrap:wrap;font-size:12.5px;color:var(--mut)}
.m b.w{color:var(--warn)} .m span,.m b{background:color-mix(in srgb,currentColor 8%,transparent);padding:2px 7px;border-radius:999px}
.pair{display:grid;gap:14px;grid-template-columns:1fr}@media(min-width:900px){.pair{grid-template-columns:390px 1fr}}
figure{margin:0} figcaption{font-size:11.5px;color:var(--mut);margin-bottom:5px}
img{width:100%;height:auto;border:1px solid var(--line);border-radius:10px;display:block}
.l{font-size:12.5px;color:var(--mut);margin:10px 0 0} .l a{color:inherit}
</style></head><body><div class="wrap">
<h1>Screen inventory</h1>
<p class="sub">${inv.pages.length} page-views captured from the demo server on ${esc(inv.at.slice(0, 16).replace('T', ' '))}.
Every screen as a first-screen image, a full-page image, and standalone HTML. Numbers are measured off the live DOM.</p>
<nav>${keys.map((k) => `<a href="#${k}">${esc(k)}</a>`).join('')}</nav>
${keys.map(card).join('\n')}
</div></body></html>`);
console.log('index.html written:', keys.length, 'screens');
