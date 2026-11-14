// capture.js -- every screen of the product as standalone HTML, a screenshot, and a measured
// inventory of its design elements. For a design review that can cite evidence.
//
//   node scripts/capture.js                 # everything, both viewports
//   ROUTES=today,match node scripts/capture.js
//
// Needs the demo server (backend/tests/demo_server.py) on BASE. Writes to docs/redesign/v11/.
//
// Why the DOM and not the source: the source is JSX across ~90 components with twenty stylesheets
// and runtime themes. What a reader SEES is the computed result, and that is the only thing worth
// reviewing. Each page is saved with its computed CSS in one shared file beside it, so a folder of
// these opens in a browser with no server and no build.
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const BASE = process.env.BASE || 'http://127.0.0.1:8011';
const OUT = path.join(__dirname, '..', 'docs', 'redesign', 'v11');
const VIEWPORTS = { phone: { width: 390, height: 844 }, desk: { width: 1440, height: 900 } };
const VIEWS = (process.env.VIEWS || 'phone,desk').split(',');
const OWNER = { email: 'owner@example.com', password: 'demo-owner-pass-1' };

// key -> [path, waitFor testid or null, {auth}]
const PUBLIC_ROUTES = {
  today: ['/', 'today-page'], live: ['/live', 'live-page'],
  insights: ['/insights', 'insights-page'], likely: ['/likely', null],
  finder: ['/finder', 'finder-page'], explore: ['/explore', 'explore-page'],
  combos: ['/combos', 'combos-page'], compare: ['/compare', 'compare-page'],
  leagues: ['/leagues', null], teams: ['/teams', null],
  referees: ['/referees', 'referees-page'], 'track-record': ['/track-record', 'track-record-page'],
  search: ['/search?q=a', null], pricing: ['/pricing', 'pricing-page'],
  learn: ['/learn', 'learn-page'], contact: ['/contact', 'contact-page'],
  welcome: ['/welcome', 'welcome-page'], waitlist: ['/waitlist', null],
  terms: ['/legal/terms', null], 'sign-in': ['/sign-in', null], 'sign-up': ['/sign-up', null],
  'forgot-password': ['/forgot-password', null], notfound: ['/no-such-page', null],
  match: [':match', 'match-page'], league: [':league', null],
  team: [':team', null], player: [':player', null], referee: [':referee', null],
  following: ['/following', null, { auth: true }],
  account: ['/account', null, { auth: true }],
};
const ADMIN_ROUTES = {
  'admin-home': ['/admin', null], 'admin-feeds': ['/admin/data/feeds', null],
  'admin-apifootball': ['/admin/data/apifootball', null],
  'admin-leagues': ['/admin/data/leagues', null], 'admin-jobs': ['/admin/data/jobs', null],
  'admin-engine': ['/admin/engine', null], 'admin-settings': ['/admin/settings', null],
  'admin-logs': ['/admin/logs', null], 'admin-users': ['/admin/users', null],
};

const J = async (page, url) => { try { const r = await page.goto(url); return await r.json(); } catch { return null; } };
const slug = (s) => s.replace(/[^a-z0-9]+/gi, '-').toLowerCase();

// Everything a design review wants to cite, measured off the live page rather than guessed.
const INVENTORY = () => {
  const vis = [...document.querySelectorAll('body *')].filter((el) => {
    const r = el.getBoundingClientRect();
    const c = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && c.visibility !== 'hidden' && c.display !== 'none' && c.opacity !== '0';
  });
  const tally = (f) => { const m = {}; for (const el of vis) { const k = f(el); if (k) m[k] = (m[k] || 0) + 1; } return m; };
  const cs = (el) => getComputedStyle(el);
  const TEXTY = (el) => el.children.length === 0 && (el.textContent || '').trim().length > 0;

  // Tap targets: anything a finger must hit. 44x44 is the floor both Apple and WCAG 2.5.8 use.
  const tappable = vis.filter((el) => ['A', 'BUTTON', 'INPUT', 'SELECT', 'TEXTAREA'].includes(el.tagName)
    || el.getAttribute('role') === 'button' || el.onclick);
  const small = tappable.map((el) => { const r = el.getBoundingClientRect(); return { tag: el.tagName.toLowerCase(),
      text: (el.textContent || '').trim().slice(0, 40), w: Math.round(r.width), h: Math.round(r.height),
      cls: (el.className || '').toString().slice(0, 60) }; })
    .filter((t) => t.w < 44 || t.h < 44);

  // Text smaller than 12px is hard to read on a phone and is the commonest regression.
  const tiny = vis.filter(TEXTY).map((el) => ({ px: parseFloat(cs(el).fontSize),
      text: (el.textContent || '').trim().slice(0, 50), cls: (el.className || '').toString().slice(0, 50) }))
    .filter((t) => t.px && t.px < 12);

  // A raw hex or rgb that is not a token: the thing that drifts between screens.
  const styleAttrColours = [...document.querySelectorAll('body [style]')]
    .map((el) => el.getAttribute('style')).filter((s) => /#[0-9a-f]{3,8}\b|rgba?\(/i.test(s));

  const overflowX = document.documentElement.scrollWidth > window.innerWidth + 1;
  return {
    counts: { elements: vis.length, tappable: tappable.length },
    fontSizes: tally((el) => (TEXTY(el) ? cs(el).fontSize : null)),
    fontWeights: tally((el) => (TEXTY(el) ? cs(el).fontWeight : null)),
    colours: tally((el) => (TEXTY(el) ? cs(el).color : null)),
    backgrounds: tally((el) => { const b = cs(el).backgroundColor; return b && b !== 'rgba(0, 0, 0, 0)' ? b : null; }),
    radii: tally((el) => { const r = cs(el).borderRadius; return r && r !== '0px' ? r : null; }),
    gaps: tally((el) => { const g = cs(el).gap; return g && g !== 'normal' && g !== '0px' ? g : null; }),
    fontFamilies: tally((el) => (TEXTY(el) ? cs(el).fontFamily.split(',')[0].replace(/"/g, '') : null)),
    smallTapTargets: small.slice(0, 40),
    tinyText: tiny.slice(0, 40),
    inlineColourStyles: styleAttrColours.slice(0, 20),
    horizontalOverflow: overflowX,
    scrollWidth: document.documentElement.scrollWidth,
    headings: [...document.querySelectorAll('h1,h2,h3,h4')].map((h) => `${h.tagName}: ${(h.textContent || '').trim().slice(0, 60)}`),
    landmarks: [...document.querySelectorAll('header,nav,main,footer,[role]')].map((e) => e.tagName.toLowerCase() + (e.getAttribute('role') ? `[${e.getAttribute('role')}]` : '')),
    imagesWithoutAlt: [...document.querySelectorAll('img:not([alt])')].length,
    buttonsWithoutName: [...document.querySelectorAll('button')].filter((b) => !(b.textContent || '').trim() && !b.getAttribute('aria-label')).length,
  };
};

(async () => {
  fs.mkdirSync(path.join(OUT, 'html'), { recursive: true });
  fs.mkdirSync(path.join(OUT, 'shots'), { recursive: true });
  const browser = await chromium.launch({ args: ['--no-sandbox'] });

  // ids, so the entity pages have content
  const api = await browser.newContext();
  const p0 = await api.newPage();
  const ids = {};
  for (let off = 0; off < 10 && !ids.match; off++) {
    const d = new Date(Date.now() + off * 86400000).toISOString().slice(0, 10);
    const list = await J(p0, `${BASE}/api/fixtures?date=${d}`);
    if (Array.isArray(list) && list.length) {
      ids.match = `/match/${list[0].id}`;
      if (list[0].home?.id) ids.team = `/team/${list[0].home.id}`;
    }
  }
  const lg = await J(p0, `${BASE}/api/leagues`);
  const firstLg = lg?.countries?.[0]?.leagues?.[0];
  if (firstLg) ids.league = `/league/${firstLg.id}`;
  const ins = await J(p0, `${BASE}/api/insights?limit=50`);
  const rows = Array.isArray(ins) ? ins : (ins?.rows || []);
  const wp = rows.find((r) => r.player?.id); if (wp) ids.player = `/player/${wp.player.id}`;
  if (!ids.team) { const t = rows.find((r) => r.team?.id); if (t) ids.team = `/team/${t.team.id}`; }
  const refs = await J(p0, `${BASE}/api/referees`);
  const rr = Array.isArray(refs) ? refs : (refs?.rows || refs?.referees || []);
  const r0 = rr.find((r) => r && (r.name || r.referee));
  if (r0) ids.referee = `/referee/${encodeURIComponent(r0.name || r0.referee)}`;
  await api.close();
  console.log('resolved ids:', JSON.stringify(ids));

  const report = { base: BASE, at: new Date().toISOString(), ids, pages: [], failed: [] };
  let cssSaved = false;

  for (const vname of VIEWS) {
    for (const [group, ROUTES] of [['public', PUBLIC_ROUTES], ['admin', ADMIN_ROUTES]]) {
      const ctx = await browser.newContext({ viewport: VIEWPORTS[vname], deviceScaleFactor: 2 });
      const page = await ctx.newPage();
      const errors = [];
      page.on('pageerror', (e) => errors.push(String(e).slice(0, 200)));
      page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text().slice(0, 200)); });

      if (group === 'admin' || Object.values(ROUTES).some(([, , o]) => o?.auth)) {
        await page.goto(`${BASE}/sign-in`);
        await page.fill('input[type=email]', OWNER.email).catch(() => {});
        await page.fill('input[type=password]', OWNER.password).catch(() => {});
        await page.click('button[type=submit]').catch(() => {});
        await page.waitForTimeout(1500);
      }

      for (const [key, spec] of Object.entries(ROUTES)) {
        let [route, testid] = spec;
        if (route.startsWith(':')) { route = ids[route.slice(1)]; if (!route) { report.failed.push({ key, vname, why: 'no id' }); continue; } }
        const name = `${key}.${vname}`;
        errors.length = 0;
        try {
          // `domcontentloaded`, NOT `networkidle`. Several screens poll -- the live feed every 30s, the
          // admin home every 60 -- so the network never goes idle and the capture times out on exactly
          // the pages that matter most. Settle by waiting for the page's own marker instead.
          const resp = await page.goto(BASE + route, { waitUntil: 'domcontentloaded', timeout: 30000 });
          await page.waitForLoadState('load', { timeout: 15000 }).catch(() => {});
          if (testid) await page.waitForSelector(`[data-testid="${testid}"]`, { timeout: 8000 }).catch(() => {});
          await page.waitForTimeout(1200);

          if (!cssSaved) {
            const css = await page.evaluate(() => [...document.styleSheets].map((s) => {
              try { return [...s.cssRules].map((r) => r.cssText).join('\n'); } catch { return ''; }
            }).join('\n'));
            fs.writeFileSync(path.join(OUT, 'html', 'page.css'), css);
            cssSaved = true;
          }
          const html = await page.evaluate(() => {
            const d = document.documentElement.cloneNode(true);
            d.querySelectorAll('script,link[rel=stylesheet],style').forEach((n) => n.remove());
            const l = document.createElement('link'); l.rel = 'stylesheet'; l.href = 'page.css';
            d.querySelector('head').appendChild(l);
            return '<!doctype html>\n' + d.outerHTML;
          });
          fs.writeFileSync(path.join(OUT, 'html', `${name}.html`), html);
          await page.screenshot({ path: path.join(OUT, 'shots', `${name}.png`), fullPage: true });
          const inv = await page.evaluate(INVENTORY);
          report.pages.push({ key, group, viewport: vname, route, status: resp?.status(), errors: [...new Set(errors)], inventory: inv });
          process.stdout.write(`${name}${inv.horizontalOverflow ? ' [OVERFLOW]' : ''}${errors.length ? ' [JSERR]' : ''}  `);
        } catch (e) {
          report.failed.push({ key, vname, why: String(e).slice(0, 160) });
          process.stdout.write(`${name}[FAIL] `);
        }
      }
      await ctx.close();
    }
  }
  fs.writeFileSync(path.join(OUT, 'inventory.json'), JSON.stringify(report, null, 1));
  await browser.close();
  console.log(`\n\ncaptured ${report.pages.length} page-views, ${report.failed.length} failed`);
})();
