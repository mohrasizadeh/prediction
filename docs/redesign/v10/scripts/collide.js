// Which lineup words actually CROSS INTO the next cell?
// A word that overruns its content box but stays inside the cell only eats its own 7px padding
// and collides with nothing. Only a word past the cell's border-box edge hits the neighbour.
const { chromium } = require('playwright');
const path = require('path'); const fs = require('fs');
const FE = '/home/user/prediction/frontend/build';
const DIR = '/tmp/claude-0/-home-user-prediction/2bfe3db5-981d-538c-8ca7-af9e11a3f551/scratchpad';
// The words are READ FROM THE SOURCE, never retyped here: a probe with its own copy of the list
// measures whatever it was last told, which is how this script first reported a fix as broken.
// Pass words on the command line to try candidates before editing the component.
const SRC = '/home/user/prediction/frontend/src/components/ui/ForecastRow.jsx';
const extra = process.argv.slice(2).filter((a) => !a.startsWith('-'));
const WORDS = extra.length ? extra
  : [...new Set([...fs.readFileSync(SRC, 'utf8').matchAll(/\bword:\s*"([^"]+)"/g)].map((m) => m[1]))];
if (!WORDS.length) { console.error(`no lineup words found in ${SRC}`); process.exit(1); }

let FAIL = 0;
(async () => {
  console.log(`words from ${path.basename(SRC)}: ${WORDS.map((w) => `"${w}"`).join(', ')}`);
  const b = await chromium.launch();
  const SITE = fs.readFileSync(DIR + '/siteconfig.json', 'utf8');
  for (const w of [1600, 1440, 1366, 1280, 1180, 1024, 900]) {
    const ctx = await b.newContext({ viewport: { width: w, height: 1000 }, deviceScaleFactor: 1 });
    const pg = await ctx.newPage();
    await pg.route('**/*', (r) => {
      const u = new URL(r.request().url());
      if (u.pathname === '/api/site/config') return r.fulfill({ body: SITE, contentType: 'application/json' });
      if (u.pathname.startsWith('/api/')) return r.fulfill({ status: 200, body: '{}', contentType: 'application/json' });
      let f = path.join(FE, u.pathname);
      if (!fs.existsSync(f) || fs.statSync(f).isDirectory()) f = path.join(FE, 'index.html');
      const t = f.endsWith('.js') ? 'application/javascript' : f.endsWith('.css') ? 'text/css'
              : f.endsWith('.woff2') ? 'font/woff2' : 'text/html';
      r.fulfill({ body: fs.readFileSync(f), contentType: t });
    });
    await pg.goto('https://forecast.zone/dev/card', { waitUntil: 'networkidle' });
    await pg.waitForSelector('.lk-tbl tbody tr');
    await pg.waitForTimeout(200);

    const out = await pg.evaluate((WORDS) => {
      const card = getComputedStyle(document.querySelector('.lk-tbl thead')).display === 'none';
      const td = document.querySelector('td.lk-cell-lu');
      const lu = td.querySelector('.lk-lu');
      const holder = lu.lastChild;
      const was = holder.nodeType === 3 ? holder.nodeValue : holder.textContent;
      const words = [];
      for (const word of WORDS) {
        if (holder.nodeType === 3) holder.nodeValue = word; else holder.textContent = word;
        const c = lu.getBoundingClientRect(), cell = td.getBoundingClientRect();
        // positive = crosses the cell's own edge, i.e. paints on the neighbour
        words.push({ word, w: Math.ceil(c.width),
                     cross: Math.round(Math.max(c.right - cell.right, cell.left - c.left)) });
      }
      if (holder.nodeType === 3) holder.nodeValue = was; else holder.textContent = was;
      // and every other cell, same test
      const cells = [...document.querySelectorAll('.lk-tbl tbody tr:first-child td')].map((td) => {
        const cell = td.getBoundingClientRect();
        const cross = [...td.children].reduce((m, e) => {
          const r = e.getBoundingClientRect();
          return Math.max(m, r.right - cell.right, cell.left - r.left);
        }, -999);
        return { cls: td.className.replace('lk-cell-', '').split(' ')[0], cross: Math.round(cross) };
      });
      return { card, cellW: Math.round(td.getBoundingClientRect().width), words, cells };
    }, WORDS);

    const hit = out.words.filter((x) => x.cross > 0);
    const cellHit = out.cells.filter((c) => c.cross > 0);
    console.log(`\n== ${w}px${out.card ? '  [card layout - no columns, nothing to collide]' : `  LINEUP cell ${out.cellW}px`}`);
    if (!out.card) {
      for (const x of out.words)
        console.log(`   ${x.cross > 0 ? 'COLLIDES' : '  clear '}  ${String(x.w).padStart(4)}px  ${x.cross > 0 ? `${x.cross}px onto the neighbour` : ''}   "${x.word}"`);
      console.log(`   other cells crossing their edge: ${cellHit.length ? cellHit.map((c) => `${c.cls} +${c.cross}px`).join(', ') : 'none'}`);
    }
    if (!out.card && hit.length) FAIL++;
    await ctx.close();
  }
  await b.close();
  console.log(FAIL === 0
    ? '\nNo lineup word crosses its cell at any width where the table is used.'
    : `\n${FAIL} width(s) have a word painting onto the neighbouring cell.`);
  process.exit(FAIL ? 1 : 0);
})();
