// Screenshot harness for the v2 redesign.
//   node scripts/shots.js <before|after> [key ...]          both schemes, both viewports
//   SCHEMES=light VIEWS=desk node scripts/shots.js after player
const { chromium } = require('playwright');

const BASE = process.env.BASE || 'http://127.0.0.1:8011';
const STAGE = process.argv[2] || 'after';
const OUT = `${__dirname}/../docs/redesign/v2/${STAGE}`;
const SCHEMES = (process.env.SCHEMES || 'dark,light').split(',');
const VIEWS = (process.env.VIEWS || 'phone,desk').split(',');

const VIEWPORTS = {
  phone: { width: 390, height: 844 },
  desk: { width: 1440, height: 900 },
};

// key -> [path, testid to wait for]. Paths with :id are filled from the API below.
const ROUTES = {
  today: ['/', 'today-page'],
  insights: ['/insights', 'insights-page'],
  match: [':match', 'match-page'],
  finder: ['/finder', 'finder-page'],
  explore: ['/explore', 'explore-page'],
  combos: ['/combos', 'combos-page'],
  track: ['/track-record', 'track-record-page'],
  following: ['/following', 'following-page'],
  pricing: ['/pricing', 'pricing-page'],
  learn: ['/learn', 'learn-page'],
  referees: ['/referees', 'referees-page'],
  contact: ['/contact', 'contact-page'],
  compare: ['/compare', 'compare-page'],
  live: ['/live', 'live-page'],
  leagues: ['/leagues', null],
  league: [':league', null],
  team: [':team', null],
  player: [':player', null],
  search: ['/search?q=Team', null],
  welcome: ['/welcome', 'welcome-page'],
  pwa: ['/legal/terms', null],
  signin: ['/sign-in', null],
  signup: ['/sign-up', null],
  notfound: ['/no-such-page', null],
};

const J = async (page, url) => { try { const r = await page.goto(url); return await r.json(); } catch { return null; } };

(async () => {
  const want = process.argv.slice(3);
  const browser = await chromium.launch({ args: ['--no-sandbox'] });

  // resolve real ids so the entity pages have content
  const api = await browser.newContext();
  const p0 = await api.newPage();
  const ids = {};
  for (let off = 0; off < 8 && !ids.match; off++) {
    const d = new Date(Date.now() + off * 86400000).toISOString().slice(0, 10);
    const list = await J(p0, `${BASE}/api/fixtures?date=${d}`);
    if (Array.isArray(list) && list.length) {
      ids.match = `/match/${list[0].id}`;
      if (list[0].home?.id) ids.team = `/team/${list[0].home.id}`;
    }
  }
  const lg = await J(p0, `${BASE}/api/leagues`);
  const first = lg?.countries?.[0]?.leagues?.[0];
  if (first) ids.league = `/league/${first.id}`;
  const ins = await J(p0, `${BASE}/api/insights?limit=50`);
  const rows = Array.isArray(ins) ? ins : (ins?.rows || []);
  const withPlayer = rows.find((r) => r.player?.id);
  if (withPlayer) ids.player = `/player/${withPlayer.player.id}`;
  if (!ids.team) { const t = rows.find((r) => r.team?.id); if (t) ids.team = `/team/${t.team.id}`; }
  await api.close();
  console.log('resolved:', JSON.stringify(ids));

  const keys = want.length ? want : Object.keys(ROUTES);
  let shot = 0, failed = [];
  for (const scheme of SCHEMES) {
    for (const vname of VIEWS) {
      const ctx = await browser.newContext({ viewport: VIEWPORTS[vname], deviceScaleFactor: 2, colorScheme: scheme });
      for (const key of keys) {
        let [path, testid] = ROUTES[key] || [];
        if (!path) { console.log(`  skip ${key} (no route)`); continue; }
        if (path.startsWith(':')) { path = ids[path.slice(1)]; if (!path) { console.log(`  skip ${key} (no id)`); continue; } }
        const page = await ctx.newPage();
        try {
          await page.goto(BASE + path, { waitUntil: 'networkidle', timeout: 45000 });
          for (const l of ['No thanks', 'Allow optional']) {
            const b = page.getByRole('button', { name: l });
            if (await b.count()) { await b.first().click().catch(() => {}); break; }
          }
          if (testid) await page.getByTestId(testid).first().waitFor({ timeout: 20000 });
          await page.waitForTimeout(800);
          await page.screenshot({ path: `${OUT}/${key}-${vname}-${scheme}.png`, fullPage: true });
          shot++;
        } catch (e) {
          failed.push(`${key}-${vname}-${scheme}`);
          console.log(`  FAIL ${key}-${vname}-${scheme}: ${String(e).split('\n')[0].slice(0, 90)}`);
        }
        await page.close();
      }
      await ctx.close();
      console.log(`done ${vname}/${scheme}`);
    }
  }
  console.log(`\n${shot} shots, ${failed.length} failed${failed.length ? ': ' + failed.join(', ') : ''}`);
  await browser.close();
})();
