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
  ctx.textAlign = "right"; ctx.fillStyle = p.accent;
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
  D.backdrop(ctx, W, H, p);
  const kick = (d.text.kicker || "Forecast").toUpperCase();
  const foot = footRoom(W, H);
  const runLabel = d.text.subhead || `His last ${(c.run || []).filter((g) => g && g.v != null).length}, and this match`;
  const downward = c.p_usual != null && c.p < c.p_usual;

  if (isWide(W, H)) {
    const colW = (inner - 48 * t.s) / 2;
    ctx.fillStyle = p.accent; ctx.textAlign = "left"; ctx.font = D.font(t.heading, 800, 24 * t.s);
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
    ctx.fillStyle = p.accent; ctx.textAlign = "left"; ctx.font = D.font(t.heading, 800, 26 * t.s);
    ctx.fillText(kick, pad, y + 24 * t.s);
    y += 52 * t.s;
    cardHead(ctx, c, d, p, t, pad, y, inner, ph);
    y += ph + gap;
    claimBox(ctx, c, d, p, t, pad, y, inner, claimH);
    y += claimH + gap;
    const rh = Math.min(runMax, H - foot - y);
    if (rh > 130 * t.s) D.run(ctx, c.run, c.thr, pct(c.p), pad, y, inner, rh, p, t.body, { down: downward, label: runLabel });
  }
  D.footer(ctx, W, H, p, t.heading, { brand: d.brand, logo: d.images.logo, disclaimer: d.disclaimer });
}

// ---------------------------------------------------------------- 2. the run
// The signature graphic as the whole image, with almost no words: a shape a reader recognises
// before they have read it, which is what stops a thumb.
function run(ctx, W, H, p, t, d) {
  const c = d.card || {};
  const pad = W * 0.072, inner = W - pad * 2;
  D.backdrop(ctx, W, H, p);
  const foot = footRoom(W, H);
  const kick = (d.text.kicker || "The last ten").toUpperCase();
  const label = d.text.subhead || "Each bar is one game. The dashed column is this match.";
  const line2 = [c.market, c.opp?.name && `vs ${c.opp.name}`].filter(Boolean).join("   ·   ");
  const downward = c.p_usual != null && c.p < c.p_usual;
  if (isWide(W, H)) {
    const colW = inner * 0.34;
    let y = pad;
    ctx.textAlign = "left"; ctx.fillStyle = p.accent; ctx.font = D.font(t.heading, 800, 24 * t.s);
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
    ctx.textAlign = "left"; ctx.fillStyle = p.accent; ctx.font = D.font(t.heading, 800, 26 * t.s);
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
  D.footer(ctx, W, H, p, t.heading, { brand: d.brand, logo: d.images.logo, disclaimer: d.disclaimer });
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
  D.backdrop(ctx, W, H, p);
  const foot = footRoom(W, H);
  let y = pad * 1.05;
  ctx.textAlign = "left"; ctx.fillStyle = p.accent; ctx.font = D.font(t.heading, 800, 26 * t.s);
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
    ctx.textAlign = "right"; ctx.fillStyle = p.accent; ctx.font = D.font(t.heading, 800, Math.min(rh * 0.42, 54 * t.s));
    ctx.fillText(pct(c.p), rx + colW - 26 * t.s, cy + Math.min(rh * 0.14, 18 * t.s));
  });
  D.footer(ctx, W, H, p, t.heading, { brand: d.brand, logo: d.images.logo, disclaimer: d.disclaimer });
}

// ---------------------------------------------------------------- 4. the fixture
function fixture(ctx, W, H, p, t, d) {
  const c = d.card || {};
  const pad = W * 0.072, inner = W - pad * 2;
  D.backdrop(ctx, W, H, p);
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
    ctx.textAlign = "right"; ctx.fillStyle = p.accent; ctx.font = D.font(t.heading, 800, 72 * t.s);
    ctx.fillText(pct(c.p), W - pad - 36 * t.s, by + 100 * t.s);
  }
  D.footer(ctx, W, H, p, t.heading, { brand: d.brand, logo: d.images.logo, disclaimer: d.disclaimer });
}

// ---------------------------------------------------------------- 5. the Finder sentence
// Nobody else's product IS a sentence. This sets the question as type, large, with the answer
// underneath, which is the whole pitch for the Finder in one image.
function finder(ctx, W, H, p, t, d) {
  const pad = W * 0.082, inner = W - pad * 2;
  D.backdrop(ctx, W, H, p);
  let y = pad * 1.2;
  ctx.textAlign = "left"; ctx.fillStyle = p.accent; ctx.font = D.font(t.heading, 800, 26 * t.s);
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
    ctx.fillStyle = p.accent; ctx.font = D.font(t.heading, 800, 120 * t.s);
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
  D.footer(ctx, W, H, p, t.heading, { brand: d.brand, logo: d.images.logo, disclaimer: d.disclaimer });
}

// ---------------------------------------------------------------- 6. one number
function stat(ctx, W, H, p, t, d) {
  const pad = W * 0.082, inner = W - pad * 2;
  D.backdrop(ctx, W, H, p);
  ctx.textAlign = "center";
  const mid = H * 0.44;
  ctx.fillStyle = p.accent; ctx.font = D.font(t.heading, 800, Math.min(W * 0.34, 380 * t.s));
  ctx.fillText(D.fit(ctx, d.text.stat_value || "72%", inner), W / 2, mid);
  ctx.fillStyle = p.text; ctx.font = D.font(t.heading, 800, 56 * t.s);
  let y = D.block(ctx, d.text.headline || "", W / 2, mid + 80 * t.s, inner, { lineHeight: 66 * t.s, lines: 3, align: "center" });
  if (d.text.subhead) {
    ctx.fillStyle = p.text3; ctx.font = D.font(t.body, 500, 32 * t.s);
    D.block(ctx, d.text.subhead, W / 2, y + 48 * t.s, inner, { lineHeight: 40 * t.s, lines: 3, align: "center" });
  }
  D.footer(ctx, W, H, p, t.heading, { brand: d.brand, logo: d.images.logo, disclaimer: d.disclaimer });
}

// ---------------------------------------------------------------- 7. headline, and 8. cover
function headline(ctx, W, H, p, t, d, big) {
  const pad = W * 0.082, inner = W - pad * 2;
  ctx.fillStyle = p.bg; ctx.fillRect(0, 0, W, H);
  const g = ctx.createLinearGradient(0, H, W, 0);
  g.addColorStop(0, D.alpha(p.accent, 0.3)); g.addColorStop(0.6, D.alpha(p.brand, 0.14)); g.addColorStop(1, D.alpha(p.bg, 0));
  ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
  ctx.textAlign = "left";
  let y = H * (big ? 0.3 : 0.34);
  if (d.text.kicker) {
    ctx.fillStyle = p.accent; ctx.font = D.font(t.heading, 800, 28 * t.s);
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
  D.footer(ctx, W, H, p, t.heading, { brand: d.brand, logo: d.images.logo, disclaimer: d.disclaimer });
}

export const TEMPLATES = {
  card, run, table, fixture, finder, stat,
  quote: (ctx, W, H, p, t, d) => headline(ctx, W, H, p, t, d, false),
  cover: (ctx, W, H, p, t, d) => headline(ctx, W, H, p, t, d, true),
};

/** The images a template needs, so the page can fetch them before it draws. */
export function needed(template, dcard, cards, logo) {
  const out = { logo };
  if (template === "table") out.rows = (cards || []).map((c) => c.player?.image || c.team?.image || null);
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
