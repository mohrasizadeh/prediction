// The FIRST SCREEN of every page, at real viewport height. The full-page captures run to 22,000px
// on a match page, which is a record but not something anyone can review; what a reader judges in
// the first second is what fits above the fold. Reuses the routes inventory.json already resolved.
const { chromium } = require('playwright');
const fs = require('fs'); const path = require('path');
const BASE = process.env.BASE || 'http://127.0.0.1:8011';
const OUT = path.join(__dirname, '..', 'docs', 'redesign', 'v11', 'fold');
const VP = { phone: { width: 390, height: 844, touch: true }, desk: { width: 1440, height: 900, touch: false } };
const OWNER = { email: 'owner@example.com', password: 'demo-owner-pass-1', newPassword: 'Capture-Review-9xQ!' };
// ------------------------------------------------------------------ signing in as the owner
// Three gates, not one. `button[type=submit]` on this page hits the THEME TOGGLE -- there are two
// forms and eight submit buttons -- so every admin capture silently came out as the sign-in page,
// byte-identical, and nothing said so. Past that the owner must enrol in two-factor sign-in and
// then choose a password, both forced. A harness that does not walk all three captures the
// onboarding and calls it the admin.
const crypto = require('crypto');
function totp(secret, t = Date.now()) {              // RFC 6238, so there is no new dependency
  const A = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567'; let bits = '';
  for (const c of secret.replace(/[\s=]/g, '').toUpperCase()) { const v = A.indexOf(c); if (v >= 0) bits += v.toString(2).padStart(5, '0'); }
  const by = Buffer.from((bits.match(/.{8}/g) || []).map((x) => parseInt(x, 2)));
  const ctr = Buffer.alloc(8); ctr.writeUInt32BE(Math.floor(t / 1000 / 30), 4);
  const h = crypto.createHmac('sha1', by).update(ctr).digest(); const o = h[h.length - 1] & 0xf;
  return String(((h.readUInt32BE(o) & 0x7fffffff) % 1e6)).padStart(6, '0');
}
// The secret, kept across contexts. THE FIRST sign-in enrols two-factor; every one after it is
// challenged for a code, and the capture signs in four times (two viewports x public/admin). A
// helper that only knows how to ENROL gets through once and is bounced to /sign-in for the rest --
// which is how nine admin screens came out as the sign-in page, byte-identical, in silence.
let OWNER_2FA_SECRET = null;

async function signInAsOwner(page, BASE, OWNER) {
  await page.goto(`${BASE}/sign-in`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(1200);
  await page.fill('[data-testid=signin-email]', OWNER.email).catch(() => {});
  await page.fill('[data-testid=signin-password]', OWNER.changed ? OWNER.newPassword : OWNER.password).catch(() => {});
  await page.click('[data-testid=signin-submit]').catch(() => {});
  await page.waitForTimeout(2200);
  // The key is printed in a <code> in groups of four, so a regex over innerText never matches it.
  const secretOf = () => page.evaluate(() => {
    for (const e of document.querySelectorAll('code,kbd,samp')) {
      const t = (e.textContent || '').replace(/\s+/g, '').toUpperCase();
      if (/^[A-Z2-7]{16,}$/.test(t)) return t;
    } return null; });
  if (page.url().includes('enroll-2fa')) {
    const s = await secretOf();
    if (s) { OWNER_2FA_SECRET = s;
             await page.fill('[data-testid=twofa-code]', totp(s)).catch(() => {});
             await page.click('[data-testid=twofa-confirm]').catch(() => {});
             await page.waitForTimeout(2200); }
  } else if (OWNER_2FA_SECRET && await page.$('[data-testid=twofa-code]')) {
    // The challenge, not the enrolment: same field, different step.
    await page.fill('[data-testid=twofa-code]', totp(OWNER_2FA_SECRET)).catch(() => {});
    await page.click('[data-testid=twofa-confirm]').catch(async () => {
      await page.click('[data-testid=signin-submit]').catch(() => {}); });
    await page.waitForTimeout(2200);
  }
  if (page.url().includes('change-password')) {
    const ids = await page.evaluate(() => [...document.querySelectorAll('input')]
      .map((i) => i.getAttribute('data-testid')).filter((x) => x && /pass/i.test(x)));
    for (const id of ids) await page.fill(`[data-testid=${id}]`, OWNER.newPassword).catch(() => {});
    await page.click('button[type=submit]:below([data-testid=' + (ids[0] || 'x') + '])').catch(async () => {
      await page.getByRole('button', { name: /save|change|set|continue/i }).first().click().catch(() => {});
    });
    await page.waitForTimeout(2500);
    OWNER.changed = true;              // every later sign-in uses the password we just set
  }
  const path = new URL(page.url()).pathname;
  if (/sign-in|enroll-2fa|change-password/.test(path)) console.log(`\n  WARNING: sign-in stopped at ${path}`);
  return path;
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const inv = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'docs', 'redesign', 'v11', 'inventory.json')));
  const b = await chromium.launch({ args: ['--no-sandbox'] });
  let n = 0;
  for (const vname of Object.keys(VP)) {
    const pages = inv.pages.filter((p) => p.viewport === vname);
    const ctx = await b.newContext({ viewport: { width: VP[vname].width, height: VP[vname].height },
      deviceScaleFactor: 2, hasTouch: VP[vname].touch, isMobile: VP[vname].touch });
    const page = await ctx.newPage();
    await page.goto(`${BASE}/sign-in`);
    await signInAsOwner(page, BASE, OWNER);
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
