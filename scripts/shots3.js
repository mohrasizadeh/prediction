// Full-inventory screenshot harness for the v3 design review (docs/57 screen IDs).
// Captures every screen the inventory lists, signing in as the demo owner for admin and account.
//   node scripts/shots3.js before            everything, both viewports, dark
//   SCHEMES=dark,light node scripts/shots3.js after P-01 P-04
const { chromium } = require('playwright');
const fs = require('fs');

const BASE = process.env.BASE || 'http://127.0.0.1:8011';
const STAGE = process.argv[2] || 'before';
const OUT = `${__dirname}/../docs/redesign/v3/${STAGE}`;
const SCHEMES = (process.env.SCHEMES || 'dark').split(',');
const VIEWS = (process.env.VIEWS || 'phone,desk').split(',');
const OWNER = process.env.DEMO_OWNER || 'owner@example.com';
const PASS = process.env.DEMO_PASS || 'demo-owner-pass-1';

const VIEWPORTS = { phone: { width: 390, height: 844 }, desk: { width: 1440, height: 900 } };

// id -> [path, waitForTestId, needsAuth]. ':x' is filled from resolved ids below.
const PUBLIC = {
  'P-01': ['/', 'today-page'],
  'P-03': ['/live', 'live-page'],
  'P-04': ['/insights', 'insights-page'],
  'P-05': ['/finder', 'finder-page'],
  'P-06': ['/explore', 'explore-page'],
  'P-07': ['/compare', 'compare-page'],
  'P-08': ['/combos', 'combos-page'],
  'P-09': ['/leagues', null],
  'P-11': [':league', null],
  'P-12': [':team', null],
  'P-13': [':player', null],
  'P-14': ['/referees', 'referees-page'],
  'P-15': [':referee', null],
  'P-16': ['/following', 'following-page'],
  'P-17': ['/track-record', 'track-record-page'],
  'P-18': ['/search?q=Team', null],
  'P-19': ['/learn', 'learn-page'],
  'P-20': [':learn', null],
  'P-21': ['/pricing', 'pricing-page'],
  'P-22': ['/welcome', 'welcome-page'],
  'P-23': ['/contact', 'contact-page'],
  'P-24': ['/legal/terms', null],
  'P-26': ['/dev/kit', null],
  'P-27': ['/no-such-page-at-all', null],
  'P-28': ['/sign-in', null],
  'P-29': ['/sign-up', null],
  'P-30': ['/verify-email', null],
  'P-32': ['/forgot-password', null],
  'P-33': ['/reset-password', null],
  'P-35': ['/enroll-2fa', null],
  'P-36': ['/unsubscribe', null],
};
const MATCH_TABS = { 'M-01': 'live', 'M-02': 'recap', 'M-03': 'forecasts', 'M-04': 'lineups', 'M-05': 'analysis' };
const ACCOUNT = ['profile', 'security', 'devices', 'notifications', 'plan', 'privacy'];
const ADMIN = {
  'AD-01': '/admin', 'AD-02': '/admin/needs', 'AD-03': '/admin/analytics',
  'AD-04': '/admin/data/feeds', 'AD-05': '/admin/data/pitchapi', 'AD-06': '/admin/data/sportapi',
  'AD-07': '/admin/data/leagues', 'AD-08': '/admin/data/jobs', 'AD-09': '/admin/data/engine',
  'AD-10': '/admin/users', 'AD-11': '/admin/staff', 'AD-12': '/admin/inbox', 'AD-13': '/admin/popups',
  'AD-14': '/admin/announcements', 'AD-15': '/admin/campaigns', 'AD-16': '/admin/newsletter',
  'AD-17': '/admin/email/templates', 'AD-18': '/admin/email/log', 'AD-19': '/admin/email/suppressions',
  'AD-20': '/admin/plans', 'AD-21': '/admin/subscriptions', 'AD-22': '/admin/payments',
  'AD-23': '/admin/coupons', 'AD-24': '/admin/revenue', 'AD-25': '/admin/studio', 'AD-26': '/admin/pages',
  'AD-27': '/admin/media', 'AD-28': '/admin/settings', 'AD-29': '/admin/keys',
  'AD-30': '/admin/integrations', 'AD-31': '/admin/logs', 'AD-32': '/admin/security', 'AD-33': '/admin/health',
  'AD-03a': '/admin/analytics/overview', 'AD-03b': '/admin/analytics/audience',
  'AD-05a': '/admin/data/pitchapi/usage', 'AD-05b': '/admin/data/pitchapi/quality',
  'AD-05c': '/admin/data/pitchapi/explorer',
};

const J = async (page, url) => { try { const r = await page.goto(url); return await r.json(); } catch { return null; } };
const dismiss = async (page) => {
  for (const l of ['No thanks', 'Allow optional']) {
    const b = page.getByRole('button', { name: l });
    if (await b.count()) { await b.first().click().catch(() => {}); break; }
  }
};

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const want = process.argv.slice(3);
  const browser = await chromium.launch({ args: ['--no-sandbox'] });

  // ---- resolve real ids so entity pages have content
  const api = await browser.newContext();
  const p0 = await api.newPage();
  const ids = {};
  for (let off = 0; off < 8 && !ids.match; off++) {
    const d = new Date(Date.now() + off * 86400000).toISOString().slice(0, 10);
    const list = await J(p0, `${BASE}/api/fixtures?date=${d}`);
    if (Array.isArray(list) && list.length) {
      ids.matchId = list[0].id;
      ids.match = `/match/${list[0].id}`;
      if (list[0].home?.id) ids.team = `/team/${list[0].home.id}`;
    }
  }
  const lg = await J(p0, `${BASE}/api/leagues`);
  const firstLeague = lg?.countries?.[0]?.leagues?.[0];
  if (firstLeague) ids.league = `/league/${firstLeague.id}`;
  const ins = await J(p0, `${BASE}/api/insights?limit=50`);
  const rows = Array.isArray(ins) ? ins : (ins?.rows || []);
  const wp = rows.find((r) => r.player?.id);
  if (wp) ids.player = `/player/${wp.player.id}`;
  if (!ids.team) { const t = rows.find((r) => r.team?.id); if (t) ids.team = `/team/${t.team.id}`; }
  const refs = await J(p0, `${BASE}/api/referees`);
  const rlist = Array.isArray(refs) ? refs : (refs?.referees || refs?.rows || []);
  if (rlist && rlist[0]) ids.referee = `/referee/${encodeURIComponent(rlist[0].name || rlist[0].id)}`;
  const learn = await J(p0, `${BASE}/api/learn`);
  const llist = Array.isArray(learn) ? learn : (learn?.articles || learn?.rows || []);
  if (llist && llist[0]?.slug) ids.learn = `/learn/${llist[0].slug}`;
  await api.close();
  console.log('resolved:', JSON.stringify(ids));

  // ---- build the full job list
  const jobs = [];
  for (const [id, [path, tid]] of Object.entries(PUBLIC)) jobs.push({ id, path, tid, auth: false });
  if (ids.matchId) for (const [id, tab] of Object.entries(MATCH_TABS)) jobs.push({ id, path: `/match/${ids.matchId}?tab=${tab}`, tid: 'match-page', auth: false });
  ACCOUNT.forEach((s, i) => jobs.push({ id: `A-0${i + 1}`, path: `/account/${s}`, tid: null, auth: true }));
  for (const [id, path] of Object.entries(ADMIN)) jobs.push({ id, path, tid: null, auth: true });
  const picked = want.length ? jobs.filter((j) => want.includes(j.id)) : jobs;
  console.log(`${picked.length} screens x ${VIEWS.length} views x ${SCHEMES.length} schemes`);

  let shot = 0; const failed = [];
  for (const scheme of SCHEMES) {
    for (const vname of VIEWS) {
      const ctx = await browser.newContext({ viewport: VIEWPORTS[vname], deviceScaleFactor: 1, colorScheme: scheme });
      // one sign-in per context, reused by every authenticated screen
      let signedIn = false;
      if (picked.some((j) => j.auth)) {
        const sp = await ctx.newPage();
        try {
          await sp.goto(`${BASE}/sign-in`, { waitUntil: 'domcontentloaded', timeout: 20000 });
          await sp.waitForTimeout(1200);
          await dismiss(sp);
          await sp.fill('input[type="email"]', OWNER);
          await sp.fill('input[type="password"]', PASS);
          await sp.getByRole('button', { name: /sign in/i }).first().click();
          await sp.waitForTimeout(3500);
          signedIn = !/\/sign-in/.test(sp.url());
          console.log(`  sign-in ${vname}/${scheme}: ${signedIn ? 'ok' : 'FAILED (' + sp.url() + ')'}`);
        } catch (e) { console.log('  sign-in error:', String(e).split('\n')[0].slice(0, 80)); }
        await sp.close();
      }
      for (const j of picked) {
        if (j.auth && !signedIn) { failed.push(`${j.id} (not signed in)`); continue; }
        const page = await ctx.newPage();
        try {
          await page.goto(BASE + j.path, { waitUntil: 'domcontentloaded', timeout: 20000 });
          await dismiss(page);
          if (j.tid) await page.getByTestId(j.tid).first().waitFor({ timeout: 8000 }).catch(() => {});
          else await page.waitForTimeout(600);
          // let late data land without waiting on a polling page that never goes idle
          await page.waitForLoadState('load', { timeout: 6000 }).catch(() => {});
          await page.waitForTimeout(900);
          await page.screenshot({ path: `${OUT}/${j.id}-${vname}-${scheme}.png`, fullPage: true });
          shot++;
        } catch (e) {
          failed.push(`${j.id}-${vname}-${scheme}`);
          console.log(`  FAIL ${j.id}-${vname}-${scheme}: ${String(e).split('\n')[0].slice(0, 80)}`);
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
