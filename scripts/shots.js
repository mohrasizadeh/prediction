// Screenshot harness for the v2 redesign. node scripts/shots.js <before|after> [route-key ...]
const { chromium } = require('playwright');

const BASE = process.env.BASE || 'http://127.0.0.1:8011';
const OUT = `${__dirname}/../docs/redesign/v2/${process.argv[2] || 'after'}`;

// id -> [path, waitForTestId]
const ROUTES = {
  'today':      ['/', 'today-page'],
  'insights':   ['/insights', 'insights-page'],
  'match':      [null, 'match-page'],          // resolved from the API
  'finder':     ['/finder', 'finder-page'],
  'explore':    ['/explore', 'explore-page'],
  'combos':     ['/combos', 'combos-page'],
  'track':      ['/track-record', 'track-record-page'],
  'following':  ['/following', 'following-page'],
  'pricing':    ['/pricing', 'pricing-page'],
  'learn':      ['/learn', 'learn-page'],
  'referees':   ['/referees', 'referees-page'],
  'contact':    ['/contact', 'contact-page'],
  'compare':    ['/compare', 'compare-page'],
  'live':       ['/live', 'live-page'],
};

const VIEWPORTS = [
  { name: 'phone', width: 390, height: 844, dsf: 2 },
  { name: 'desk', width: 1440, height: 900, dsf: 2 },
];

(async () => {
  const which = process.argv.slice(3);
  const browser = await chromium.launch({ args: ['--no-sandbox'] });

  // find a real match id from the API so the match page has content
  const api = await browser.newContext();
  const p0 = await api.newPage();
  // /api/fixtures needs a date and returns a bare array; walk a few days until one has a fixture
  let matchPath = null;
  const d0 = new Date();
  for (let off = 0; off < 8 && !matchPath; off++) {
    const d = new Date(d0.getTime() + off * 86400000).toISOString().slice(0, 10);
    try {
      const r = await p0.goto(`${BASE}/api/fixtures?date=${d}`);
      const list = await r.json();
      if (Array.isArray(list) && list.length) matchPath = `/match/${list[0].id}`;
    } catch (e) { /* try the next day */ }
  }
  if (matchPath) ROUTES.match[0] = matchPath; else delete ROUTES.match;
  await api.close();
  console.log('match route:', matchPath || 'NOT FOUND (skipped)');

  const keys = which.length ? which : Object.keys(ROUTES);
  for (const vp of VIEWPORTS) {
    const ctx = await browser.newContext({
      viewport: { width: vp.width, height: vp.height },
      deviceScaleFactor: vp.dsf,
      colorScheme: 'dark',
    });
    for (const key of keys) {
      const spec = ROUTES[key];
      if (!spec) { console.log(`  skip ${key}`); continue; }
      const page = await ctx.newPage();
      try {
        await page.goto(BASE + spec[0], { waitUntil: 'networkidle', timeout: 45000 });
        // The consent banner is fixed, so in a full-page shot it lands in the middle of the image
        // and hides the content underneath. Answer it once, as a reader would.
        for (const label of ['No thanks', 'Allow optional']) {
          const b = page.getByRole('button', { name: label });
          if (await b.count()) { await b.first().click().catch(() => {}); break; }
        }
        await page.waitForTimeout(250);
        if (spec[1]) await page.getByTestId(spec[1]).first().waitFor({ timeout: 20000 });
        await page.waitForTimeout(900);
        const file = `${OUT}/${key}-${vp.name}.png`;
        await page.screenshot({ path: file, fullPage: true });
        const h = await page.evaluate(() => document.body.scrollHeight);
        console.log(`  ${key}-${vp.name}  ${h}px`);
      } catch (e) {
        console.log(`  FAIL ${key}-${vp.name}: ${String(e).split('\n')[0]}`);
      }
      await page.close();
    }
    await ctx.close();
  }
  await browser.close();
})();
