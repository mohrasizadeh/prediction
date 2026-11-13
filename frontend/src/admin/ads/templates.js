// The ad templates (docs/60 section 2). Each one leads with ONE claim the data can carry.
//
// The temptation with an ad builder is eight arrangements of a logo and a photo. What this product
// has that nobody else has is a finding: this player's number for this market departs from his usual
// by this much, and here are the ten games behind it. docs/56 says that departure is the only
// quantity comparable down a feed and docs/redesign/v2 calls the run strip the signature graphic, so
// the ingredients the owner asked for -- crest, league mark, photo, position, last ten, the Finder
// sentence -- attach to whichever claim needs them rather than being arranged for their own sake.
//
// Every template is `(ctx, W, H, p, t, data) => void`, drawing in its size's own coordinates.
//   p     palette tokens (sizes.js)
//   t     type: {body, heading} family names, and `s`, the size's scale knob
//   data  {card, cards, brand, logo, text:{headline,...}, disclaimer, images}
import * as D from "./draw";

const pct = (x) => (x == null ? "–" : `${Math.round(x * 100)}%`);
const band = (lo, hi) => (lo == null || hi == null || Math.round(lo * 100) === Math.round(hi * 100)
  ? null : `${Math.round(lo * 100)} to ${Math.round(hi * 100)}`);
const initials = (n) => String(n || "?").trim().split(/\s+/).map((w) => w[0]).filter(Boolean).slice(0, 2).join("").toUpperCase();
// Shorten the first name, never the surname, as the card does.
const shortName = (n) => { const q = String(n || "").trim().split(/\s+/); return n && n.length > 16 && q.length > 1 ? `${q[0][0]}. ${q.slice(1).join(" ")}` : n; };
const fixtureText = (c) => {
  if (!c) return "";
  const home = c.home_iid != null && c.opp_iid != null ? c.home_iid !== c.opp_iid : true;
  const a = c.team?.name, b = c.opp?.name;
  if (!a) return "";
  if (!b) return a;
  return home ? `${a} v ${b}` : `${b} v ${a}`;
};

// ---------------------------------------------------------------- 1. the card
// The product's own object at poster size. Everything a reader needs to judge the claim: who, for
// which club, in which position, against whom, the market, the likelihood with its range, the tier,
// the departure from usual, and the ten games.
//
// Two arrangements, not five. A story is nearly twice as tall as a square, so the blocks are laid
// out with `spread` and the run takes whatever is left -- fixed offsets from the top left a void in
// the bottom half. A landscape is wider than it is tall, where a stack does not work at all, so the
// identity goes in a left column and the claim and the strip in a right one.
const isWide = (W, H) => W / H > 1.35;
// The footer is a fixed stack of type, so its room is a function of WIDTH, not of height. Taking it
// as H * 0.12 left 76px on a 630-tall landscape, and the run strip's label was drawn straight
// through the disclaimer.
const footRoom = (W, H) => Math.max(H * 0.11, W * 0.072 * 1.35);

function cardHead(ctx, c, d, p, t, x, y, w, ph) {
  D.portrait(ctx, d.images.player, x + ph / 2, y + ph / 2, ph, p, initials(c.player?.name), t.heading);
  const tx = x + ph + 34 * t.s, tw = w - ph - 34 * t.s;
  ctx.textAlign = "left"; ctx.fillStyle = p.text;
  ctx.font = D.font(t.heading, 800, Math.min(70 * t.s, ph * 0.3));
  ctx.fillText(D.fit(ctx, shortName(c.player?.name) || c.team?.name || "", tw), tx, y + ph * 0.46);
  let sx = tx;
  if (d.images.team || c.team?.name) { D.chip(ctx, d.images.team, sx + 19 * t.s, y + ph * 0.68, 38 * t.s, p); sx += 50 * t.s; }
  ctx.fillStyle = p.text2; ctx.font = D.font(t.body, 600, 30 * t.s);
  const sub = [c.team?.name, c.pos ? String(c.pos).toUpperCase() : null, c.opp?.name ? `vs ${c.opp.name}` : null].filter(Boolean).join("  ·  ");
  ctx.fillText(D.fit(ctx, sub, tw - (sx - tx)), sx, y + ph * 0.72);
}

function claimBox(ctx, c, d, p, t, x, y, w, h) {
  D.card(ctx, x, y, w, h, 34, p.surface1, p.border);
  const px = x + 40 * t.s, pw = w - 80 * t.s;
  ctx.textAlign = "left"; ctx.fillStyle = p.text3; ctx.font = D.font(t.body, 600, 28 * t.s);
  ctx.fillText(D.fit(ctx, c.market || "", pw * 0.55), px, y + 62 * t.s);
  ctx.textAlign = "right"; ctx.fillStyle = p.ink;
  ctx.font = D.font(t.heading, 800, Math.min(110 * t.s, h * 0.45));
  ctx.fillText(pct(c.p), x + w - 40 * t.s, y + 104 * t.s);
  const rng = band(c.lo, c.hi);
  if (rng) { ctx.fillStyle = p.text3; ctx.font = D.font(t.body, 600, 24 * t.s); ctx.fillText(rng, x + w - 40 * t.s, y + 140 * t.s); }
  ctx.textAlign = "left";
  D.tier(ctx, c.tier, px, y + 88 * t.s, p, t.body, t.s);
  if (c.p_usual != null) {
    const dep = Math.round((c.p - c.p_usual) * 100);
    ctx.fillStyle = p.text2; ctx.font = D.font(t.body, 600, 26 * t.s);
    ctx.fillText(`Usual ${pct(c.p_usual)}   ${dep > 0 ? "+" : ""}${dep} points`, px, y + 182 * t.s);
  }
  D.meter(ctx, { p: c.p, lo: c.lo, hi: c.hi, usual: c.p_usual }, px, y + h - 46 * t.s, pw, 18 * t.s, p);
}

function card(ctx, W, H, p, t, d) {
  const c = d.card || {};
  const pad = W * 0.072, inner = W - pad * 2;
  const kick = (d.text.kicker || "Forecast").toUpperCase();
  const foot = footRoom(W, H);
  const runLabel = d.text.subhead || `His last ${(c.run || []).filter((g) => g && g.v != null).length}, and this match`;
  const downward = c.p_usual != null && c.p < c.p_usual;

  if (isWide(W, H)) {
    const colW = (inner - 48 * t.s) / 2;
    ctx.fillStyle = p.ink; ctx.textAlign = "left"; ctx.font = D.font(t.heading, 800, 24 * t.s);
    ctx.fillText(kick, pad, pad + 20 * t.s);
    const top = pad + 52 * t.s;
    const ph = Math.min(colW * 0.42, (H - top - foot) * 0.46);
    cardHead(ctx, c, d, p, t, pad, top, colW, ph);
    const rh = H - (top + ph + 34 * t.s) - foot;
    if (rh > 120 * t.s) {
      D.run(ctx, c.run, c.thr, pct(c.p), pad, top + ph + 34 * t.s, colW, rh, p, t.body, { down: downward, label: runLabel });
    }
    claimBox(ctx, c, d, p, t, pad + colW + 48 * t.s, top, colW, Math.min(H - top - foot, 300 * t.s));
  } else {
    const ph = Math.min(W * 0.26, 250 * t.s);
    const headH = 52 * t.s + ph;
    const claimH = (H / W > 1.5 ? 300 : 260) * t.s;
    const runMax = Math.min((H / W > 1.5 ? 520 : 300) * t.s, H * 0.3);
    const avail = H - pad * 1.05 - foot;
    const gap = D.spread(avail, [headH, claimH, runMax], 34 * t.s);
    let y = pad * 1.05;
    ctx.fillStyle = p.ink; ctx.textAlign = "left"; ctx.font = D.font(t.heading, 800, 26 * t.s);
    ctx.fillText(kick, pad, y + 24 * t.s);
    y += 52 * t.s;
    cardHead(ctx, c, d, p, t, pad, y, inner, ph);
    y += ph + gap;
    claimBox(ctx, c, d, p, t, pad, y, inner, claimH);
    y += claimH + gap;
    const rh = Math.min(runMax, H - foot - y);
    if (rh > 130 * t.s) D.run(ctx, c.run, c.thr, pct(c.p), pad, y, inner, rh, p, t.body, { down: downward, label: runLabel });
  }
  D.footer(ctx, W, H, p, t.heading, { brand: d.brand, site: d.site, logo: d.images.logo, disclaimer: d.disclaimer });
}

// ---------------------------------------------------------------- 2. the run
// The signature graphic as the whole image, with almost no words: a shape a reader recognises
// before they have read it, which is what stops a thumb.
function run(ctx, W, H, p, t, d) {
  const c = d.card || {};
  const pad = W * 0.072, inner = W - pad * 2;
  const foot = footRoom(W, H);
  const kick = (d.text.kicker || "The last ten").toUpperCase();
  const label = d.text.subhead || "Each bar is one game. The dashed column is this match.";
  const line2 = [c.market, c.opp?.name && `vs ${c.opp.name}`].filter(Boolean).join("   ·   ");
  const downward = c.p_usual != null && c.p < c.p_usual;
  if (isWide(W, H)) {
    const colW = inner * 0.34;
    let y = pad;
    ctx.textAlign = "left"; ctx.fillStyle = p.ink; ctx.font = D.font(t.heading, 800, 24 * t.s);
    ctx.fillText(kick, pad, y + 22 * t.s);
    y += 56 * t.s;
    ctx.fillStyle = p.text; ctx.font = D.font(t.heading, 800, 60 * t.s);
    y = D.block(ctx, shortName(c.player?.name) || c.team?.name || "", pad, y + 52 * t.s, colW, { lineHeight: 64 * t.s, lines: 2 });
    ctx.fillStyle = p.text2; ctx.font = D.font(t.body, 600, 30 * t.s);
    D.block(ctx, line2, pad, y + 42 * t.s, colW, { lineHeight: 38 * t.s, lines: 2 });
    const rx = pad + colW + 44 * t.s;
    D.run(ctx, c.run, c.thr, pct(c.p), rx, pad + 14 * t.s, W - pad - rx, H - foot - (pad + 14 * t.s), p, t.body, { down: downward, label });
  } else {
    let y = pad * 1.1;
    ctx.textAlign = "left"; ctx.fillStyle = p.ink; ctx.font = D.font(t.heading, 800, 26 * t.s);
    ctx.fillText(kick, pad, y + 24 * t.s);
    y += 62 * t.s;
    ctx.fillStyle = p.text; ctx.font = D.font(t.heading, 800, 86 * t.s);
    y = D.block(ctx, shortName(c.player?.name) || c.team?.name || "", pad, y + 70 * t.s, inner, { lineHeight: 92 * t.s, lines: 2 });
    ctx.fillStyle = p.text2; ctx.font = D.font(t.body, 600, 34 * t.s);
    ctx.fillText(D.fit(ctx, line2, inner), pad, y + 44 * t.s);
    y += 76 * t.s;
    // The strip takes everything left: in a story that is most of the image, which is the point.
    D.run(ctx, c.run, c.thr, pct(c.p), pad, y, inner, H - foot - y - 10 * t.s, p, t.body, { down: downward, label });
  }
  D.footer(ctx, W, H, p, t.heading, { brand: d.brand, site: d.site, logo: d.images.logo, disclaimer: d.disclaimer });
}

// ---------------------------------------------------------------- 3. the table
// The densest template, and the one people save. Crests carry the identification so the rows can
// stay short. A wide canvas splits the rows into two columns rather than stretching four of them.
function table(ctx, W, H, p, t, d) {
  const pad = W * 0.072, inner = W - pad * 2;
  const wide = isWide(W, H);
  const ratio = H / W;
  const want = wide ? 8 : ratio > 1.4 ? 8 : ratio > 1.1 ? 6 : 5;
  const rows = (d.cards || []).slice(0, want);
  const foot = footRoom(W, H);
  let y = pad * 1.05;
  ctx.textAlign = "left"; ctx.fillStyle = p.ink; ctx.font = D.font(t.heading, 800, 26 * t.s);
  ctx.fillText((d.text.kicker || "Tonight").toUpperCase(), pad, y + 24 * t.s);
  y += 52 * t.s;
  ctx.fillStyle = p.text; ctx.font = D.font(t.heading, 800, (wide ? 56 : 68) * t.s);
  y = D.block(ctx, d.text.headline || "The strongest forecasts", pad, y + (wide ? 48 : 56) * t.s, inner, { lineHeight: (wide ? 62 : 74) * t.s, lines: 2 });
  if (d.text.subhead) {
    ctx.fillStyle = p.text2; ctx.font = D.font(t.body, 500, 28 * t.s);
    y = D.block(ctx, d.text.subhead, pad, y + 34 * t.s, inner, { lineHeight: 36 * t.s, lines: 2 });
  }
  y += 26 * t.s;
  const cols = wide ? 2 : 1;
  const perCol = Math.ceil(rows.length / cols);
  const colW = (inner - (cols - 1) * 20 * t.s) / cols;
  const avail = H - y - foot;
  const rh = Math.min(avail / Math.max(perCol, 1), 150 * t.s);
  rows.forEach((c, i) => {
    const col = Math.floor(i / perCol), k = i % perCol;
    const rx = pad + col * (colW + 20 * t.s);
    const ry = y + k * rh;
    D.card(ctx, rx, ry, colW, rh - 12 * t.s, 24, p.surface1, p.border);
    const cy = ry + (rh - 12 * t.s) / 2;
    const cd = Math.min(rh * 0.5, 62 * t.s);
    D.chip(ctx, d.images.rows?.[i], rx + 22 * t.s + cd / 2, cy, cd, p);
    const nx = rx + 22 * t.s + cd + 20 * t.s;
    const textW = colW - (nx - rx) - 130 * t.s;
    ctx.textAlign = "left"; ctx.fillStyle = p.text; ctx.font = D.font(t.heading, 800, Math.min(rh * 0.27, 38 * t.s));
    ctx.fillText(D.fit(ctx, shortName(c.player?.name) || c.team?.name || "", textW), nx, cy - 4 * t.s);
    ctx.fillStyle = p.text3; ctx.font = D.font(t.body, 600, Math.min(rh * 0.2, 26 * t.s));
    ctx.fillText(D.fit(ctx, [c.market, c.opp?.name && `vs ${c.opp.name}`].filter(Boolean).join("  ·  "), textW), nx, cy + Math.min(rh * 0.22, 30 * t.s));
    ctx.textAlign = "right"; ctx.fillStyle = p.ink; ctx.font = D.font(t.heading, 800, Math.min(rh * 0.42, 54 * t.s));
    ctx.fillText(pct(c.p), rx + colW - 26 * t.s, cy + Math.min(rh * 0.14, 18 * t.s));
  });
  D.footer(ctx, W, H, p, t.heading, { brand: d.brand, site: d.site, logo: d.images.logo, disclaimer: d.disclaimer });
}

// ---------------------------------------------------------------- 4. the fixture
function fixture(ctx, W, H, p, t, d) {
  const c = d.card || {};
  const pad = W * 0.072, inner = W - pad * 2;
  const foot = footRoom(W, H);
  const wide = isWide(W, H);
  const cd = Math.min(W * (wide ? 0.2 : 0.3), 300 * t.s, (H - foot) * 0.34);
  const leadH = c.market ? 160 * t.s : 0;
  const headH = 112 * t.s + 40 * t.s;
  const titleH = 70 * t.s + (d.text.subhead ? 44 * t.s : 0);
  const gap = D.spread(H - pad - foot, [headH, cd, titleH, leadH].filter(Boolean), 26 * t.s);
  let y = pad;
  if (d.images.league) D.chip(ctx, d.images.league, W / 2, y + 44 * t.s, 84 * t.s, p);
  ctx.textAlign = "center"; ctx.fillStyle = p.text3; ctx.font = D.font(t.body, 600, 26 * t.s);
  ctx.fillText(D.fit(ctx, c.league_name || "", inner), W / 2, y + 118 * t.s);
  y += headH + gap * 0.5;
  const homeFirst = c.home_iid == null || c.home_iid !== c.opp_iid;
  D.chip(ctx, homeFirst ? d.images.team : d.images.opp, W * 0.28, y + cd / 2, cd, p);
  D.chip(ctx, homeFirst ? d.images.opp : d.images.team, W * 0.72, y + cd / 2, cd, p);
  ctx.fillStyle = p.text2; ctx.font = D.font(t.heading, 800, 46 * t.s);
  ctx.fillText("v", W / 2, y + cd / 2 + 16 * t.s);
  y += cd + gap;
  ctx.fillStyle = p.text; ctx.font = D.font(t.heading, 800, 54 * t.s);
  y = D.block(ctx, d.text.headline || fixtureText(c), W / 2, y + 44 * t.s, inner, { lineHeight: 62 * t.s, lines: 2, align: "center" });
  if (d.text.subhead) {
    ctx.fillStyle = p.text3; ctx.font = D.font(t.body, 500, 30 * t.s);
    y = D.block(ctx, d.text.subhead, W / 2, y + 36 * t.s, inner, { lineHeight: 38 * t.s, lines: 1, align: "center" });
  }
  if (leadH) {
    const by = Math.min(y + gap, H - foot - leadH);
    D.card(ctx, pad, by, inner, leadH, 30, p.surface1, p.border);
    ctx.textAlign = "left"; ctx.fillStyle = p.text3; ctx.font = D.font(t.body, 600, 24 * t.s);
    ctx.fillText(d.text.kicker || "Leading forecast", pad + 36 * t.s, by + 48 * t.s);
    ctx.fillStyle = p.text; ctx.font = D.font(t.heading, 800, 38 * t.s);
    ctx.fillText(D.fit(ctx, `${shortName(c.player?.name) || c.team?.name || ""} · ${c.market}`, inner * 0.6), pad + 36 * t.s, by + 102 * t.s);
    ctx.textAlign = "right"; ctx.fillStyle = p.ink; ctx.font = D.font(t.heading, 800, 72 * t.s);
    ctx.fillText(pct(c.p), W - pad - 36 * t.s, by + 100 * t.s);
  }
  D.footer(ctx, W, H, p, t.heading, { brand: d.brand, site: d.site, logo: d.images.logo, disclaimer: d.disclaimer });
}

// ---------------------------------------------------------------- 5. the Finder sentence
// Nobody else's product IS a sentence. This sets the question as type, large, with the answer
// underneath, which is the whole pitch for the Finder in one image.
function finder(ctx, W, H, p, t, d) {
  const pad = W * 0.082, inner = W - pad * 2;
  let y = pad * 1.2;
  ctx.textAlign = "left"; ctx.fillStyle = p.ink; ctx.font = D.font(t.heading, 800, 26 * t.s);
  ctx.fillText((d.text.kicker || "Forecast Finder").toUpperCase(), pad, y + 24 * t.s);
  y += 86 * t.s;
  // the question, set big, with the brand accent swiped behind the part it turns on
  ctx.fillStyle = p.text; ctx.font = D.font(t.heading, 700, 76 * t.s);
  y = D.block(ctx, d.text.finder_q || "Players with 2+ shots in 7 of the last 10", pad, y + 70 * t.s, inner,
    { lineHeight: 92 * t.s, lines: H / W > 1.3 ? 6 : 4 });
  y += 58 * t.s;
  ctx.strokeStyle = p.accent; ctx.lineWidth = 6 * t.s;
  ctx.beginPath(); ctx.moveTo(pad, y); ctx.lineTo(pad + inner * 0.22, y); ctx.stroke();
  y += 64 * t.s;
  const names = (d.cards || []).slice(0, 4).map((c) => shortName(c.player?.name) || c.team?.name).filter(Boolean);
  if (d.text.stat_value) {
    ctx.fillStyle = p.ink; ctx.font = D.font(t.heading, 800, 120 * t.s);
    ctx.fillText(d.text.stat_value, pad, y + 100 * t.s);
    y += 136 * t.s;
  }
  if (names.length) {
    ctx.fillStyle = p.text2; ctx.font = D.font(t.body, 600, 36 * t.s);
    y = D.block(ctx, names.join("   ·   "), pad, y + 40 * t.s, inner, { lineHeight: 46 * t.s, lines: 2 });
  }
  if (d.text.subhead) {
    ctx.fillStyle = p.text3; ctx.font = D.font(t.body, 500, 30 * t.s);
    D.block(ctx, d.text.subhead, pad, y + 54 * t.s, inner, { lineHeight: 38 * t.s, lines: 2 });
  }
  D.footer(ctx, W, H, p, t.heading, { brand: d.brand, site: d.site, logo: d.images.logo, disclaimer: d.disclaimer });
}

// ---------------------------------------------------------------- 6. one number
function stat(ctx, W, H, p, t, d) {
  const pad = W * 0.082, inner = W - pad * 2;
  ctx.textAlign = "center";
  const mid = H * 0.44;
  ctx.fillStyle = p.ink; ctx.font = D.font(t.heading, 800, Math.min(W * 0.34, 380 * t.s));
  ctx.fillText(D.fit(ctx, d.text.stat_value || "72%", inner), W / 2, mid);
  ctx.fillStyle = p.text; ctx.font = D.font(t.heading, 800, 56 * t.s);
  let y = D.block(ctx, d.text.headline || "", W / 2, mid + 80 * t.s, inner, { lineHeight: 66 * t.s, lines: 3, align: "center" });
  if (d.text.subhead) {
    ctx.fillStyle = p.text3; ctx.font = D.font(t.body, 500, 32 * t.s);
    D.block(ctx, d.text.subhead, W / 2, y + 48 * t.s, inner, { lineHeight: 40 * t.s, lines: 3, align: "center" });
  }
  D.footer(ctx, W, H, p, t.heading, { brand: d.brand, site: d.site, logo: d.images.logo, disclaimer: d.disclaimer });
}

// ---------------------------------------------------------------- 7. headline, and 8. cover
function headline(ctx, W, H, p, t, d, big) {
  const pad = W * 0.082, inner = W - pad * 2;
  ctx.textAlign = "left";
  let y = H * (big ? 0.3 : 0.34);
  if (d.text.kicker) {
    ctx.fillStyle = p.ink; ctx.font = D.font(t.heading, 800, 28 * t.s);
    ctx.fillText(d.text.kicker.toUpperCase(), pad, y);
    y += 56 * t.s;
  }
  ctx.fillStyle = p.text; ctx.font = D.font(t.heading, 800, (big ? 108 : 84) * t.s);
  y = D.block(ctx, d.text.headline || "", pad, y + (big ? 96 : 76) * t.s, inner, { lineHeight: (big ? 118 : 94) * t.s, lines: 4 });
  if (d.text.subhead) {
    ctx.fillStyle = p.text2; ctx.font = D.font(t.body, 500, 36 * t.s);
    y = D.block(ctx, d.text.subhead, pad, y + 52 * t.s, inner, { lineHeight: 46 * t.s, lines: 3 });
  }
  if (d.text.cta) {
    const h = 86 * t.s;
    ctx.font = D.font(t.heading, 700, 34 * t.s);
    const w = ctx.measureText(d.text.cta).width + 72 * t.s;
    D.card(ctx, pad, y + 48 * t.s, w, h, h / 2, p.accent);
    ctx.fillStyle = p.onAccent; ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.fillText(d.text.cta, pad + w / 2, y + 48 * t.s + h / 2);
    ctx.textBaseline = "alphabetic"; ctx.textAlign = "left";
  }
  if (big) {
    // the cover says it is a carousel, because a reader has to know to swipe
    ctx.fillStyle = p.text3; ctx.textAlign = "right"; ctx.font = D.font(t.body, 600, 28 * t.s);
    ctx.fillText("Swipe →", W - pad, H * 0.2);
  }
  D.footer(ctx, W, H, p, t.heading, { brand: d.brand, site: d.site, logo: d.images.logo, disclaimer: d.disclaimer });
}

// ---------------------------------------------------------------- 9. a club's own numbers
// Not a forecast: the evidence a reader can check. For and against, side by side, because a club
// that takes eight corners and concedes two is a different story from one that trades them.
function teamstat(ctx, W, H, p, t, d) {
  const ts = d.teamStat || {};
  const pad = W * 0.072, inner = W - pad * 2;
  const foot = footRoom(W, H);
  let y = pad * 1.05;
  ctx.textAlign = "left"; ctx.fillStyle = p.ink; ctx.font = D.font(t.heading, 800, 26 * t.s);
  ctx.fillText((d.text.kicker || "").toUpperCase(), pad, y + 24 * t.s);
  y += 56 * t.s;
  const cd = Math.min(96 * t.s, W * 0.1);
  D.chip(ctx, d.images.team, pad + cd / 2, y + cd / 2, cd, p);
  ctx.fillStyle = p.text; ctx.font = D.font(t.heading, 800, 58 * t.s);
  ctx.fillText(D.fit(ctx, ts.team?.name || "", inner - cd - 28 * t.s), pad + cd + 28 * t.s, y + cd * 0.62);
  y += cd + 18 * t.s;
  ctx.fillStyle = p.text3; ctx.font = D.font(t.body, 600, 28 * t.s);
  ctx.fillText(D.fit(ctx, [ts.league_name, `last ${ts.games} matches`, ts.opp?.name && `next: ${ts.opp.name}`].filter(Boolean).join("  ·  "), inner), pad, y + 26 * t.s);
  y += 64 * t.s;
  const rows = (ts.stats || []).slice(0, 4);
  const avail = H - y - foot;
  const rh = Math.min(avail / Math.max(rows.length, 1), 230 * t.s);
  rows.forEach((r, i) => {
    const ry = y + i * rh;
    D.card(ctx, pad, ry, inner, rh - 14 * t.s, 24, p.surface1, p.border);
    const cy = ry + (rh - 14 * t.s) / 2;
    ctx.textAlign = "left"; ctx.fillStyle = p.text2; ctx.font = D.font(t.body, 600, Math.min(rh * 0.2, 30 * t.s));
    ctx.fillText(r.label, pad + 32 * t.s, cy + 8 * t.s);
    // for
    ctx.textAlign = "right"; ctx.fillStyle = p.ink; ctx.font = D.font(t.heading, 800, Math.min(rh * 0.34, 48 * t.s));
    ctx.fillText(r.avg.toFixed(1), pad + inner * 0.68, cy + 12 * t.s);
    ctx.fillStyle = p.text3; ctx.font = D.font(t.body, 600, Math.max(20 * t.s, Math.min(rh * 0.14, 26 * t.s)));
    ctx.fillText("made", pad + inner * 0.68, cy + 38 * t.s);
    if (r.against != null) {
      ctx.fillStyle = p.text; ctx.font = D.font(t.heading, 800, Math.min(rh * 0.34, 48 * t.s));
      ctx.fillText(r.against.toFixed(1), pad + inner - 32 * t.s, cy + 12 * t.s);
      ctx.fillStyle = p.text3; ctx.font = D.font(t.body, 600, Math.max(20 * t.s, Math.min(rh * 0.14, 26 * t.s)));
      ctx.fillText("faced", pad + inner - 32 * t.s, cy + 38 * t.s);
    }
  });
  D.footer(ctx, W, H, p, t.heading, { brand: d.brand, site: d.site, logo: d.images.logo, disclaimer: d.disclaimer });
}

// ---------------------------------------------------------------- 10. how we did
// Phrased as calibration, never as a score: "we said 84%, it happened 86%" is the honest shape of
// the answer (queries.py track_record), and the sample size is on the image because a percentage
// without one is not a record.
function record(ctx, W, H, p, t, d) {
  const r = d.record || {};
  const pad = W * 0.082, inner = W - pad * 2;
  const foot = footRoom(W, H);
  let y = pad;
  ctx.textAlign = "left"; ctx.fillStyle = p.ink; ctx.font = D.font(t.heading, 800, 26 * t.s);
  ctx.fillText((d.text.kicker || "Our record").toUpperCase(), pad, y + 24 * t.s);
  y += 50 * t.s;
  if (d.images.league) { D.chip(ctx, d.images.league, pad + 34 * t.s, y + 34 * t.s, 68 * t.s, p); }
  ctx.fillStyle = p.text; ctx.font = D.font(t.heading, 800, 50 * t.s);
  y = D.block(ctx, d.text.headline || "", pad + (d.images.league ? 86 * t.s : 0), y + 46 * t.s, inner - (d.images.league ? 86 * t.s : 0), { lineHeight: 56 * t.s, lines: 2 });
  const mid = y + (H - foot - y) * 0.36;
  ctx.textAlign = "center";
  ctx.fillStyle = p.ink; ctx.font = D.font(t.heading, 800, Math.min(W * 0.3, 320 * t.s));
  ctx.fillText(d.text.stat_value || "", W / 2, mid);
  ctx.fillStyle = p.text2; ctx.font = D.font(t.body, 600, 32 * t.s);
  let yy = D.block(ctx, d.text.subhead || "", W / 2, mid + 56 * t.s, inner, { lineHeight: 42 * t.s, lines: 3, align: "center" });
  if (r.n) {
    ctx.fillStyle = p.text3; ctx.font = D.font(t.body, 600, 24 * t.s);
    ctx.fillText(`${Number(r.n).toLocaleString()} forecasts scored after the match`, W / 2, yy + 44 * t.s);
  }
  D.footer(ctx, W, H, p, t.heading, { brand: d.brand, site: d.site, logo: d.images.logo, disclaimer: d.disclaimer });
}

// ================================================================ the match, before and after
// docs/60 section 4. These three read backend/ad_sources.py rather than the public feed: one match's
// two squads, and one scored match day with its misses left in.

// A whole number prints as one ("5", not "5.0"); anything else keeps one decimal.
const count = (x) => (x == null ? "–" : Number.isInteger(+x) ? String(+x) : (+x).toFixed(1));
// The thing being counted, singular or plural. `noun` is ["shot", "shots"] off the forecast.
const unit = (c, n) => {
  const nn = Array.isArray(c?.noun) && c.noun.length === 2 ? c.noun : null;
  const base = nn ? (+n === 1 ? nn[0] : nn[1]) : String(c?.stat || "").replace(/_/g, " ");
  return base || "";
};
// The subject of a sentence: the player as the card names him (shortName), or the club for a team
// line. Never "he" -- the ad names who it is about.
const subject = (c) => shortName(c?.player?.name) || c?.team?.name || "";
// Kick-off as a reader says it: "Sat 15 Nov, 19:00". The API's datetimes are UTC, sometimes
// without the Z, so it is added before parsing; shown in the owner's own time.
const when = (k, withTime = true) => {
  if (!k) return "";
  const d = new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(k) ? k : `${k}Z`);
  if (Number.isNaN(d.getTime())) return "";
  const day = d.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" });
  return withTime ? `${day}, ${d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}` : day;
};

/** A tick or a cross in a filled circle. Shape AND colour, so the result never rests on colour
 *  alone (docs/03). */
function mark(ctx, ok, cx, cy, d, p) {
  ctx.save();
  ctx.fillStyle = ok ? p.accent : p.down;
  ctx.beginPath(); ctx.arc(cx, cy, d / 2, 0, Math.PI * 2); ctx.fill();
  ctx.strokeStyle = ok ? p.onAccent : "#fff"; ctx.lineWidth = Math.max(3, d * 0.12); ctx.lineCap = "round"; ctx.lineJoin = "round";
  ctx.beginPath();
  if (ok) { ctx.moveTo(cx - d * 0.22, cy + d * 0.02); ctx.lineTo(cx - d * 0.05, cy + d * 0.19); ctx.lineTo(cx + d * 0.24, cy - d * 0.17); }
  else { ctx.moveTo(cx - d * 0.18, cy - d * 0.18); ctx.lineTo(cx + d * 0.18, cy + d * 0.18); ctx.moveTo(cx + d * 0.18, cy - d * 0.18); ctx.lineTo(cx - d * 0.18, cy + d * 0.18); }
  ctx.stroke();
  ctx.restore();
}

/** The published line against what he recorded: the track is the scale, the bar is the count, the
 *  upright is the line. The waitlist page's proof strip, at poster size. */
function lineStrip(ctx, thr, actual, ok, x, y, w, h, p, fam, s) {
  const steps = Math.max(Math.ceil(+actual || 0), Math.ceil(+thr || 0)) + 1;
  const ux = w / steps;
  D.card(ctx, x, y, w, h, h / 2, D.alpha(p.text, 0.1));
  if (+actual > 0) D.card(ctx, x, y, Math.max(h, (+actual) * ux), h, h / 2, ok ? p.accent : p.down);
  const xt = x + (+thr) * ux;
  ctx.fillStyle = p.text; ctx.fillRect(xt - 3 * s, y - 14 * s, 6 * s, h + 28 * s);
  ctx.fillStyle = p.text3; ctx.font = D.font(fam, 600, 22 * s); ctx.textAlign = "center";
  // "needed 3", not "the line: 2.5": a reader counts shots, the half is the engine's bookkeeping
  ctx.fillText(`needed ${Math.floor(+thr) + 1}`, Math.min(Math.max(xt, x + 70 * s), x + w - 70 * s), y + h + 46 * s);
  ctx.textAlign = "left";
}

// ---------------------------------------------------------------- 11. head to head
// One player from each side, before kick-off. Two columns in every size, because the comparison is
// the claim: in a stack, the second player is read as an afterthought.
//
// With no market picked each player shows his strongest lines, one per market. With one picked,
// both stand on the same question and the number is set large, because then the two numbers ARE
// the ad.
function faceoff(ctx, W, H, p, t, d) {
  const m = d.matchup || {};
  const pad = W * 0.072, inner = W - pad * 2;
  const foot = footRoom(W, H);
  const wide = isWide(W, H);
  const one = !!m.stat;
  const gap = (wide ? 90 : 40) * t.s;
  // A story is 9:16. Laid out at square proportions it left half the frame empty, so on a tall
  // canvas every block is allowed to grow.
  const grow = H / W > 1.5 ? 1.32 : 1;
  const colW = (inner - gap) / 2;
  let y = pad;
  ctx.textAlign = "left"; ctx.fillStyle = p.ink; ctx.font = D.font(t.heading, 800, 26 * t.s);
  ctx.fillText((d.text.kicker || "Before kick-off").toUpperCase(), pad, y + 24 * t.s);
  ctx.textAlign = "right"; ctx.fillStyle = p.text3; ctx.font = D.font(t.body, 600, 24 * t.s);
  ctx.fillText(D.fit(ctx, [m.league_name, when(m.kickoff)].filter(Boolean).join("  ·  "), inner * 0.58), W - pad, y + 24 * t.s);
  y += 52 * t.s;
  if (d.text.headline) {
    ctx.textAlign = "left"; ctx.fillStyle = p.text; ctx.font = D.font(t.heading, 800, (wide ? 46 : 58) * t.s);
    y = D.block(ctx, d.text.headline, pad, y + (wide ? 44 : 54) * t.s, inner, { lineHeight: (wide ? 52 : 64) * t.s, lines: 2 });
    y += 10 * t.s;
  }
  const sides = [m.home, m.away];
  const pics = [d.images.homeP, d.images.awayP], crests = [d.images.homeT, d.images.awayT];
  const avail = H - foot - y - (d.text.subhead ? 50 * t.s : 0);
  // Sized from the room there is, then centred in it: fixed sizes left a story two-thirds empty
  // and squeezed a landscape's rows to slivers.
  const cd = 54 * t.s;
  const headH = 18 * t.s + cd + 26 * t.s;
  const ph = wide ? Math.min(colW * 0.3, 160 * t.s, avail * 0.36) : Math.min(colW * 0.62, 300 * grow * t.s, avail * 0.3);
  const idH = wide ? ph + 30 * t.s : ph + 56 * grow * t.s + 66 * grow * t.s;
  const lh = one ? Math.min(Math.max(avail * 0.24, 170 * t.s), 260 * grow * t.s)
    : Math.min(Math.max(avail * (wide ? 0.2 : 0.11), (wide ? 70 : 84) * t.s), (wide ? 96 : 124 * grow) * t.s);
  const nLines = one ? 1 : Math.max(1, Math.min(3, Math.floor((avail - headH - idH) / lh)));
  const used = one ? 1 : Math.max(1, ...sides.map((sd) => Math.min(nLines, sd?.pick?.lines?.length || 0)));
  const content = headH + idH + used * lh;
  const top = y + Math.max(0, (avail - content) * 0.42);

  sides.forEach((sd, i) => {
    const c = sd?.pick;
    const x = pad + i * (colW + gap);
    let yy = top + 18 * t.s;
    // the club, small, above its player
    D.chip(ctx, crests[i], x + cd / 2, yy + cd / 2, cd, p);
    ctx.textAlign = "left"; ctx.fillStyle = p.text2; ctx.font = D.font(t.body, 700, 28 * t.s);
    ctx.fillText(D.fit(ctx, sd?.team?.name || "", colW - cd - 16 * t.s), x + cd + 16 * t.s, yy + cd * 0.66);
    yy += cd + 26 * t.s;
    if (wide) {
      D.portrait(ctx, pics[i], x + ph / 2, yy + ph / 2, ph, p, initials(c?.player?.name), t.heading);
      const tx = x + ph + 20 * t.s, tw = colW - ph - 20 * t.s;
      ctx.fillStyle = p.text; ctx.font = D.font(t.heading, 800, 40 * t.s);
      ctx.fillText(D.fit(ctx, shortName(c?.player?.name) || "Nobody yet", tw), tx, yy + ph * 0.48);
      ctx.fillStyle = p.text3; ctx.font = D.font(t.body, 600, 24 * t.s);
      ctx.fillText(D.fit(ctx, c?.pos ? String(c.pos).toUpperCase() : "", tw), tx, yy + ph * 0.48 + 36 * t.s);
      yy += ph + 30 * t.s;
    } else {
      D.portrait(ctx, pics[i], x + colW / 2, yy + ph / 2, ph, p, initials(c?.player?.name), t.heading);
      yy += ph + 56 * grow * t.s;
      ctx.textAlign = "center"; ctx.fillStyle = p.text; ctx.font = D.font(t.heading, 800, 46 * grow * t.s);
      ctx.fillText(D.fit(ctx, shortName(c?.player?.name) || "Nobody yet", colW), x + colW / 2, yy);
      ctx.fillStyle = p.text3; ctx.font = D.font(t.body, 600, 24 * grow * t.s);
      ctx.fillText(D.fit(ctx, c?.pos ? String(c.pos).toUpperCase() : "", colW), x + colW / 2, yy + 36 * grow * t.s);
      yy += 66 * grow * t.s;
    }
    const lines = (c?.lines || []).slice(0, nLines);
    if (one && lines[0]) {
      const l = lines[0];
      D.card(ctx, x, yy, colW, lh, 28, p.surface1, p.border);
      ctx.textAlign = "center"; ctx.fillStyle = p.ink; ctx.font = D.font(t.heading, 800, Math.min(lh * 0.46, 120 * t.s));
      ctx.fillText(pct(l.p), x + colW / 2, yy + lh * 0.5);
      ctx.fillStyle = p.text2; ctx.font = D.font(t.body, 700, 28 * t.s);
      ctx.fillText(D.fit(ctx, l.market || "", colW - 40 * t.s), x + colW / 2, yy + lh * 0.5 + 44 * t.s);
      D.meter(ctx, { p: l.p, lo: l.lo, hi: l.hi }, x + 30 * t.s, yy + lh - 34 * t.s, colW - 60 * t.s, 12 * t.s, p);
    } else {
      lines.forEach((l, k) => {
        const ry = yy + k * lh, h = lh - 12 * t.s;
        D.card(ctx, x, ry, colW, h, 20, p.surface1, p.border);
        ctx.textAlign = "left"; ctx.fillStyle = p.text2; ctx.font = D.font(t.body, 700, Math.min(28 * grow * t.s, h * 0.3));
        ctx.fillText(D.fit(ctx, l.market || "", colW * 0.58), x + 22 * t.s, ry + h * 0.48);
        ctx.textAlign = "right"; ctx.fillStyle = p.ink; ctx.font = D.font(t.heading, 800, Math.min(46 * grow * t.s, h * 0.46));
        ctx.fillText(pct(l.p), x + colW - 22 * t.s, ry + h * 0.52);
        D.meter(ctx, { p: l.p, lo: l.lo, hi: l.hi }, x + 22 * t.s, ry + h * 0.74, colW - 44 * t.s, Math.max(8 * t.s, h * 0.09), p);
      });
      if (!lines.length) {
        ctx.textAlign = "left"; ctx.fillStyle = p.text3; ctx.font = D.font(t.body, 600, 26 * t.s);
        D.block(ctx, one ? "No published line on this market" : "No published line yet", x, yy + 30 * t.s, colW, { lineHeight: 34 * t.s, lines: 2 });
      }
    }
  });
  // the "v" sits between the two portraits
  const vy = top + headH + ph / 2;
  ctx.textAlign = "center"; ctx.fillStyle = p.text3; ctx.font = D.font(t.heading, 800, 40 * t.s);
  ctx.fillText("v", W / 2, vy + 14 * t.s);
  if (d.text.subhead) {
    ctx.textAlign = "left"; ctx.fillStyle = p.text3; ctx.font = D.font(t.body, 500, 26 * t.s);
    ctx.fillText(D.fit(ctx, d.text.subhead, inner), pad, H - foot - 6 * t.s);
  }
  D.footer(ctx, W, H, p, t.heading, { brand: d.brand, site: d.site, logo: d.images.logo, disclaimer: d.disclaimer });
}

// ---------------------------------------------------------------- 12. we said, it happened
// One forecast as it was published, and what happened. Drawn the same way whether it came in or
// not: a builder that could only draw hits would be a builder for cherry-picking.
function verdict(ctx, W, H, p, t, d) {
  const c = d.card || {};
  const pad = W * 0.072, inner = W - pad * 2;
  const foot = footRoom(W, H);
  const wide = isWide(W, H);
  const ok = !!c.reached;
  const grow = H / W > 1.5 ? 1.4 : 1;                       // a story gets bigger blocks, not more empty frame
  const kick = (d.text.kicker || "We said. It happened.").toUpperCase();
  let y = pad;
  ctx.textAlign = "left"; ctx.fillStyle = p.ink; ctx.font = D.font(t.heading, 800, 26 * t.s);
  ctx.fillText(kick, pad, y + 24 * t.s);
  ctx.textAlign = "right"; ctx.fillStyle = p.text3; ctx.font = D.font(t.body, 600, 24 * t.s);
  ctx.fillText(D.fit(ctx, when(c.kickoff, false), inner * 0.4), W - pad, y + 24 * t.s);
  y += 52 * t.s;
  const ph = Math.min(W * (wide ? 0.13 : 0.2 * grow), 200 * grow * t.s);
  const headW = wide ? inner * 0.42 : inner;
  cardHead(ctx, c, d, p, t, pad, y, headW, ph);
  // two boxes: what we said, what happened
  const bx = wide ? pad + headW + 40 * t.s : pad;
  const bw = wide ? W - pad - bx : inner;
  const by = wide ? y : y + ph + 40 * grow * t.s;
  const stripRoom = 120 * t.s;
  const bh = Math.min(wide ? H - foot - by - stripRoom : 400 * grow * t.s, (H - foot - by - stripRoom - 30 * t.s));
  const half = (bw - 24 * t.s) / 2;
  [0, 1].forEach((k) => {
    const x = bx + k * (half + 24 * t.s);
    D.card(ctx, x, by, half, bh, 30, p.surface1, k === 1 ? (ok ? p.accent : p.down) : p.border);
    ctx.textAlign = "left"; ctx.fillStyle = p.text3; ctx.font = D.font(t.body, 700, 24 * t.s);
    ctx.fillText(k === 0 ? "WE SAID" : "IT HAPPENED", x + 30 * t.s, by + 50 * t.s);
    const big = Math.min(bh * 0.4, 128 * grow * t.s, half * 0.42);
    ctx.font = D.font(t.heading, 800, big);
    ctx.fillStyle = k === 0 ? p.ink : p.text;
    ctx.fillText(k === 0 ? pct(c.p) : count(c.actual), x + 30 * t.s, by + 50 * t.s + big * 1.02);
    ctx.fillStyle = p.text2; ctx.font = D.font(t.body, 600, Math.min(26 * t.s, half * 0.07));
    const sub = k === 0 ? `for ${c.market || "the line"}` : `${unit(c, c.actual)} for ${subject(c)}`;
    D.block(ctx, sub, x + 30 * t.s, by + 50 * t.s + big * 1.02 + 44 * t.s, half - 60 * t.s, { lineHeight: 32 * t.s, lines: 2 });
    if (k === 1) {
      const md = 44 * t.s;
      mark(ctx, ok, x + half - 30 * t.s - md / 2, by + 40 * t.s, md, p);
    } else {
      D.tier(ctx, c.tier, x + 30 * t.s, by + bh - 76 * t.s, p, t.body, t.s * 0.9);
    }
  });
  // the line, and how far past (or short of) it he finished
  const sy = by + bh + 44 * t.s;
  if (sy + 30 * t.s < H - foot) lineStrip(ctx, c.thr, c.actual, ok, bx, sy, bw, 22 * t.s, p, t.body, t.s);
  if (d.text.subhead && !wide) {
    ctx.textAlign = "left"; ctx.fillStyle = p.text3; ctx.font = D.font(t.body, 500, 26 * t.s);
    D.block(ctx, d.text.subhead, pad, Math.min(sy + 120 * t.s, H - foot - 40 * t.s), inner, { lineHeight: 34 * t.s, lines: 2 });
  }
  D.footer(ctx, W, H, p, t.heading, { brand: d.brand, site: d.site, logo: d.images.logo, disclaimer: d.disclaimer });
}

// ---------------------------------------------------------------- 13. how the day went
// A match day's forecasts against what happened. The rows are the owner's pick; the COUNT on the
// image is the whole day's, always, so showing the five that came in cannot pass for a perfect day.
function results(ctx, W, H, p, t, d) {
  const st = d.settled || {};
  const pad = W * 0.072, inner = W - pad * 2;
  const wide = isWide(W, H);
  const ratio = H / W;
  const want = wide ? 8 : ratio > 1.4 ? 8 : ratio > 1.1 ? 6 : 5;
  const rows = (st.rows || []).slice(0, want);
  const foot = footRoom(W, H);
  let y = pad;
  ctx.textAlign = "left"; ctx.fillStyle = p.ink; ctx.font = D.font(t.heading, 800, 26 * t.s);
  ctx.fillText((d.text.kicker || "After the whistle").toUpperCase(), pad, y + 24 * t.s);
  ctx.textAlign = "right"; ctx.fillStyle = p.text3; ctx.font = D.font(t.body, 600, 24 * t.s);
  ctx.fillText(D.fit(ctx, when(st.day, false), inner * 0.4), W - pad, y + 24 * t.s);
  y += 52 * t.s;
  ctx.textAlign = "left"; ctx.fillStyle = p.text; ctx.font = D.font(t.heading, 800, (wide ? 50 : 62) * t.s);
  y = D.block(ctx, d.text.headline || "What we said, and what happened", pad, y + (wide ? 46 : 56) * t.s, inner, { lineHeight: (wide ? 56 : 68) * t.s, lines: 2 });
  // The day's own count, in words, under the headline.
  if (st.n) {
    ctx.fillStyle = p.text2; ctx.font = D.font(t.body, 600, 28 * t.s);
    const line = `${st.came_in} of ${st.n} came in that day.${rows.length < st.n ? ` Showing ${rows.length}; every scored line counts.` : ""}`;
    // Not replaceable by the sub-head: this sentence is what keeps a list of five hits honest.
    y = D.block(ctx, line, pad, y + 8 * t.s, inner, { lineHeight: 36 * t.s, lines: 2 });
  }
  y += 24 * t.s;
  const cols = wide ? 2 : 1;
  const perCol = Math.ceil(rows.length / cols);
  const colW = (inner - (cols - 1) * 20 * t.s) / cols;
  const rh = Math.min((H - y - foot) / Math.max(perCol, 1), 140 * t.s);
  rows.forEach((c, i) => {
    const col = Math.floor(i / perCol), k = i % perCol;
    const rx = pad + col * (colW + 20 * t.s), ry = y + k * rh;
    const h = rh - 12 * t.s;
    D.card(ctx, rx, ry, colW, h, 22, p.surface1, p.border);
    const cy = ry + h / 2;
    const cd = Math.min(h * 0.58, 60 * t.s);
    D.chip(ctx, d.images.rows?.[i], rx + 20 * t.s + cd / 2, cy, cd, p);
    const nx = rx + 20 * t.s + cd + 18 * t.s;
    const right = Math.min(250 * t.s, colW * 0.42);
    const tw = colW - (nx - rx) - right;
    ctx.textAlign = "left"; ctx.fillStyle = p.text; ctx.font = D.font(t.heading, 800, Math.min(h * 0.27, 34 * t.s));
    ctx.fillText(D.fit(ctx, shortName(c.player?.name) || c.team?.name || "", tw), nx, cy - 3 * t.s);
    ctx.fillStyle = p.text3; ctx.font = D.font(t.body, 600, Math.min(h * 0.2, 24 * t.s));
    ctx.fillText(D.fit(ctx, [c.market, c.opp?.name && `vs ${c.opp.name}`].filter(Boolean).join("  ·  "), tw), nx, cy + Math.min(h * 0.24, 30 * t.s));
    // right side: said -> happened, then the mark
    const md = Math.min(h * 0.42, 44 * t.s);
    const mx = rx + colW - 18 * t.s - md / 2;
    mark(ctx, !!c.reached, mx, cy, md, p);
    const ax = mx - md / 2 - 16 * t.s;
    ctx.textAlign = "right";
    ctx.fillStyle = p.text; ctx.font = D.font(t.heading, 800, Math.min(h * 0.34, 40 * t.s));
    ctx.fillText(count(c.actual), ax, cy + 6 * t.s);
    const aw = ctx.measureText(count(c.actual)).width;
    ctx.fillStyle = p.text3; ctx.font = D.font(t.body, 600, Math.min(h * 0.18, 22 * t.s));
    ctx.fillText("had", ax, cy + Math.min(h * 0.3, 32 * t.s));
    ctx.fillStyle = p.ink; ctx.font = D.font(t.heading, 800, Math.min(h * 0.3, 34 * t.s));
    const px = ax - aw - 26 * t.s;
    ctx.fillText(pct(c.p), px, cy + 6 * t.s);
    ctx.fillStyle = p.text3; ctx.font = D.font(t.body, 600, Math.min(h * 0.18, 22 * t.s));
    ctx.fillText("said", px, cy + Math.min(h * 0.3, 32 * t.s));
  });
  D.footer(ctx, W, H, p, t.heading, { brand: d.brand, site: d.site, logo: d.images.logo, disclaimer: d.disclaimer });
}

export const TEMPLATES = {
  card, run, table, fixture, finder, stat, teamstat, record, faceoff, verdict, results,
  quote: (ctx, W, H, p, t, d) => headline(ctx, W, H, p, t, d, false),
  cover: (ctx, W, H, p, t, d) => headline(ctx, W, H, p, t, d, true),
  // A question and an ask are the same composition as a headline. They are separate ids because the
  // planner fills slots by id, and because "curiosity" and "cta" are what the owner calls them.
  curiosity: (ctx, W, H, p, t, d) => headline(ctx, W, H, p, t, d, false),
  cta: (ctx, W, H, p, t, d) => headline(ctx, W, H, p, t, d, false),
};

// Which background goes under each template. Drawn full-bleed by paint() BEFORE the safe-area
// inset, so a story still fills the frame while its content stays clear of Instagram's interface.
export const BG = {
  card: "wash", run: "wash", table: "wash", fixture: "wash", finder: "wash", teamstat: "wash", record: "wash",
  stat: "wash", quote: "brand", cover: "brand", curiosity: "brand", cta: "brand",
  faceoff: "wash", verdict: "wash", results: "wash",
};

/** The images a template needs, so the page can fetch them before it draws. */
export function needed(template, dcard, cards, logo, extra) {
  const out = { logo };
  if (template === "teamstat") out.team = extra?.teamStat?.team?.image || null;
  if (template === "record") out.league = extra?.record?.league_image || null;
  if (template === "table") out.rows = (cards || []).map((c) => c.player?.image || c.team?.image || null);
  if (template === "faceoff") {
    const m = extra?.matchup || {};
    out.homeP = m.home?.pick?.player?.image || null; out.awayP = m.away?.pick?.player?.image || null;
    out.homeT = m.home?.team?.image || null; out.awayT = m.away?.team?.image || null;
    return out;
  }
  if (template === "results") {
    out.rows = (extra?.settled?.rows || []).map((c) => c.player?.image || c.team?.image || null);
    return out;
  }
  if (dcard) {
    out.player = dcard.player?.image || null;
    out.team = dcard.team?.image || null;
    out.opp = dcard.opp?.image || null;
    // The league mark is not on a forecast: _decorate copies league_name and league_id only, so the
    // page looks the image up from /api/leagues and hangs it here.
    out.league = dcard.league_image || null;
  }
  return out;
}
