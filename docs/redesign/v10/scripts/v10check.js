// The v10 card, checked against the real ForecastRow out of the built app.
const { chromium } = require('playwright');
const path = require('path'); const fs = require('fs');
const FE = '/home/user/prediction/frontend/build';
const DIR = '/tmp/claude-0/-home-user-prediction/2bfe3db5-981d-538c-8ca7-af9e11a3f551/scratchpad';
const T = []; const ok = (c, m) => T.push([!!c, m]);

(async () => {
  const b = await chromium.launch();
  const SITE = fs.readFileSync(DIR + '/siteconfig.json', 'utf8');
  for (const [w, sfx, touch] of [[1366, 'desktop', false], [390, 'phone', true]]) {
    const ctx = await b.newContext({ viewport: { width: w, height: 1000 }, deviceScaleFactor: 2,
                                     hasTouch: touch, isMobile: touch });
    const pg = await ctx.newPage();
    const errs = []; pg.on('pageerror', (e) => errs.push(e.message));
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
    await pg.waitForTimeout(300);
    ok(errs.length === 0, `${sfx}: no page errors${errs[0] ? ' -- ' + errs[0] : ''}`);
    const over = await pg.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    ok(over <= 0, `${sfx}: no horizontal overflow (${over}px past)`);

    // ---- the sentence -------------------------------------------------------
    const say = await pg.$eval('.lk-say', (e) => e.innerText.replace(/\s+/g, ' ').trim());
    ok(/makes/.test(say), `${sfx}: the row reads as a sentence ("${say}")`);
    const names = await pg.$$eval('.lk-name', (els) => els.map((e) => e.textContent));
    ok(!names.some((n) => /…|\.\.\.$/.test(n)), `${sfx}: no name is truncated (${names.join(', ')})`);

    // ---- the verb follows the market ---------------------------------------
    const before = await pg.$eval('.lk-verb', (e) => e.textContent.trim());
    await pg.$eval('[data-testid^="lk-mkt-"]', (e) => e.click());
    await pg.waitForSelector('.lk-mktlist');
    await pg.$$eval('.lk-mktlist button', (els) => {
      const other = els.find((x) => /shot/i.test(x.textContent)); (other || els[1]).click();
    });
    await pg.waitForTimeout(150);
    const after = await pg.$eval('.lk-verb', (e) => e.textContent.trim());
    ok(before !== after, `${sfx}: changing the market changes the verb (${before} -> ${after})`);
    await pg.reload({ waitUntil: 'networkidle' });
    await pg.waitForSelector('.lk-tbl tbody tr');

    // ---- the grades are told apart by FILL, not only by hue ------------------
    const fills = await pg.$$eval('.k-tier', (els) => [...new Set(els.map((e) => {
      const cs = getComputedStyle(e); return cs.backgroundColor + '|' + cs.color;
    }))]);
    ok(fills.length >= 2, `${sfx}: the grades differ in fill as well as hue (${fills.length} distinct)`);

    // ---- the result is a mark and a count -----------------------------------
    const res = await pg.$$eval('.lv-chip', (els) => els.map((e) => e.innerText.trim()));
    ok(res.some((r) => /^got \d/.test(r)), `${sfx}: a settled row says what they got (${res.join(' / ')})`);
    ok(await pg.$('.lv-chip--hit svg') !== null, `${sfx}: ...with a mark, so colour is not carrying the verdict alone`);

    if (!touch) {
      // ---- eight columns, one kind of data each ----------------------------
      const cols = await pg.$eval('.lk-tbl tbody tr', (r) => [...r.querySelectorAll('td')].map((td) => ({
        cls: td.className.split(' ')[0], d: getComputedStyle(td).display,
        w: Math.round(td.getBoundingClientRect().width) })));
      ok(cols.length === 8, `desktop: eight columns, one per kind of data (${cols.length})`);
      ok(cols.every((c) => c.d === 'table-cell'), `desktop: every cell is still a table cell`);
      const tw = await pg.$eval('.lk-tbl', (e) => Math.round(e.getBoundingClientRect().width));
      const sum = cols.reduce((a, c) => a + c.w, 0);
      ok(Math.abs(sum - tw) <= 4, `desktop: the columns account for the whole table (${sum} of ${tw}px)`);
      // the header must take the widths too: with table-layout fixed the FIRST row sets them
      const head = await pg.$$eval('.lk-tbl thead th', (els) => els.map((e) => Math.round(e.getBoundingClientRect().width)));
      ok(head.length === 8 && Math.abs(head[0] - cols[0].w) <= 1,
         `desktop: the header sits on the body's columns (${head[0]} vs ${cols[0].w})`);
      // one x per column, down every row
      const x = (sel) => pg.$$eval('.lk-tbl tbody tr ' + sel, (els) => [...new Set(els.map((e) => Math.round(e.getBoundingClientRect().left)))]);
      for (const [sel, name] of [['.lk-runwrap', 'evidence'], ['.k-tier', 'grade'], ['.lk-why', 'why']]) {
        const xs = await x(sel);
        // centred content of differing width rounds to within a pixel; that is not a misalignment
        ok(Math.max(...xs) - Math.min(...xs) <= 1, `desktop: the ${name} column holds one x (${xs.join('/')})`);
      }
      const rowH = await pg.$$eval('.lk-tbl tbody tr:not(.lk-whyrow)', (rs) => [...new Set(rs.map((r) => Math.round(r.getBoundingClientRect().height)))]);
      ok(Math.max(...rowH) <= 80, `desktop: rows stay near 70px (${rowH.join('/')})`);
    } else {
      // ---- the phone card ---------------------------------------------------
      const sep = await pg.$eval('.lk-tbl tbody tr', (r) => {
        const cs = getComputedStyle(r);
        return { radius: parseFloat(cs.borderTopLeftRadius), border: cs.borderTopWidth };
      });
      ok(sep.radius >= 12 && parseFloat(sep.border) >= 1, `phone: each forecast is its own card (radius ${sep.radius})`);
      const small = await pg.$$eval('.lk-tbl tbody tr button', (els) => els.filter((e) => {
        const r = e.getBoundingClientRect();
        if (e.classList.contains('lk-tk') || e.classList.contains('lk-mkt')) return false;  // 44px via ::after
        if (r.width === 0 && r.height === 0) return false;        // hidden: the wide-screen stepper
        return r.height < 44 || r.width < 44;
      }).map((e) => `${e.className.split(' ')[0]} ${Math.round(e.getBoundingClientRect().width)}x${Math.round(e.getBoundingClientRect().height)}`));
      ok(small.length === 0, `phone: every target is 44px${small.length ? ' -- ' + small.join(', ') : ''}`);
      // the two changeable words are WORDS, not pills
      const tok = await pg.$eval('.lk-mkt', (e) => {
        const cs = getComputedStyle(e);
        return { bg: cs.backgroundColor, border: cs.borderBottomStyle, size: parseFloat(cs.fontSize) };
      });
      ok(/rgba\(0, 0, 0, 0\)|transparent/.test(tok.bg) && tok.border === 'dotted',
         `phone: the market reads as a word, not a pill (${tok.bg}, ${tok.border})`);
      const claimSize = await pg.$eval('.lk-verb', (e) => parseFloat(getComputedStyle(e).fontSize));
      ok(Math.abs(tok.size - claimSize) <= 1, `phone: ...at the size of the words around it (${tok.size} vs ${claimSize})`);
      const panel = await pg.$eval('td.lk-cell-run', (e) => Math.round(e.getBoundingClientRect().width));
      const card = await pg.$eval('.lk-tbl tbody tr', (e) => Math.round(e.getBoundingClientRect().width));
      ok(panel > card * 0.8, `phone: the evidence panel takes the card's width (${panel} of ${card}px)`);
      ok(await pg.$('.lk-evlabel') !== null, `phone: ...and says what the bars mean`);
    }

    // ---- stepping the line, and the range that follows it in Why ------------
    const pick = touch ? '[data-testid^="lk-line-"]' : '[data-testid^="lk-step-up-"]';
    const read = () => pg.$eval('.lk-tbl tbody tr', (r) => ({
      p: r.querySelector('.lk-figure').textContent,
      n: r.innerText.match(/(\d+)\+/)?.[1] || null }));
    const b1 = await read();
    if (touch) {
      await pg.$eval(pick, (e) => e.click());
      await pg.waitForSelector('.lk-tklist');
      await pg.$$eval('.lk-tklist button', (els) => els[els.length - 1].click());
    } else {
      await pg.$eval(pick, (e) => e.click());
    }
    await pg.waitForTimeout(150);
    const a1 = await read();
    ok(a1.n !== b1.n, `${sfx}: the line moves (${b1.n}+ -> ${a1.n}+)`);
    ok(a1.p !== b1.p, `${sfx}: ...and the number follows (${b1.p} -> ${a1.p})`);
    // the range left the row for Why; the behaviour it pinned has to follow it there
    await pg.$eval('[data-testid^="lk-why-"]', (e) => e.click());
    await pg.waitForSelector('.lk-whybox');
    const rng1 = await pg.$eval('.lk-whybox', (e) => e.innerText.match(/Likely range [\d]+–[\d]+%/)?.[0] || null);
    ok(rng1 !== null, `${sfx}: Why carries the likely range the row no longer prints (${rng1})`);
    await ctx.close();
  }
  await b.close();
  for (const [p, m] of T) console.log(p ? '  ok   ' : '  FAIL ', m);
  const bad = T.filter(([p]) => !p).length;
  console.log(bad ? `\n${bad} FAILED` : `\nall ${T.length} passed`);
  process.exit(bad ? 1 : 0);
})();
