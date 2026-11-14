// The FIRST SCREEN of every page, at real viewport height. The full-page captures run to 22,000px
// on a match page, which is a record but not something anyone can review; what a reader judges in
// the first second is what fits above the fold. Reuses the routes inventory.json already resolved.
const { chromium } = require('playwright');
const fs = require('fs'); const path = require('path');
const BASE = process.env.BASE || 'http://127.0.0.1:8011';
const OUT = path.join(__dirname, '..', 'docs', 'redesign', 'v11', 'fold');
const VP = { phone: { width: 390, height: 844 }, desk: { width: 1440, height: 900 } };
const OWNER = { email: 'owner@example.com', password: 'demo-owner-pass-1' };
(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const inv = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'docs', 'redesign', 'v11', 'inventory.json')));
  const b = await chromium.launch({ args: ['--no-sandbox'] });
  let n = 0;
  for (const vname of Object.keys(VP)) {
    const pages = inv.pages.filter((p) => p.viewport === vname);
    const ctx = await b.newContext({ viewport: VP[vname], deviceScaleFactor: 2 });
    const page = await ctx.newPage();
    await page.goto(`${BASE}/sign-in`);
    await page.fill('input[type=email]', OWNER.email).catch(() => {});
    await page.fill('input[type=password]', OWNER.password).catch(() => {});
    await page.click('button[type=submit]').catch(() => {});
    await page.waitForTimeout(1200);
    for (const p of pages) {
      try {
        await page.goto(BASE + p.route, { waitUntil: 'domcontentloaded', timeout: 25000 });
        await page.waitForLoadState('load', { timeout: 12000 }).catch(() => {});
        await page.waitForTimeout(1100);
        await page.screenshot({ path: path.join(OUT, `${p.key}.${vname}.png`) });   // viewport only
        n++; process.stdout.write('.');
      } catch { process.stdout.write('x'); }
    }
    await ctx.close();
  }
  await b.close();
  console.log(`\nfold shots: ${n}`);
})();
