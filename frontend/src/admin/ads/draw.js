// Canvas primitives for the ad builder (docs/60).
//
// Everything here draws into a context whose transform is ALREADY scaled, so a template lays itself
// out in its own coordinate space (see sizes.js: 1080 wide for a square) and the same code exports
// at any pixel size. Nothing in this file knows a colour or a font name: both arrive from Site
// Studio through the palette object, because the share card that hardcoded them has been drawing a
// palette that was replaced two redesigns ago.
import { getBlob } from "../../lib/api";

// ---------------------------------------------------------------- images
// Our own addresses only, fetched through the same helper the share card uses, so the canvas is
// never tainted and toBlob keeps working.
const cache = new Map();
export async function bitmap(image) {
  if (!image) return null;
  if (cache.has(image)) return cache.get(image);
  const p = (async () => {
    try { return await createImageBitmap(await getBlob(image)); } catch { return null; }
  })();
  cache.set(image, p);
  return p;
}

// ---------------------------------------------------------------- type
export const font = (fam, weight, px, stretch) =>
  `${stretch ? `${stretch} ` : ""}${weight} ${px}px ${fam.includes(" ") ? `"${fam}"` : fam}, system-ui, sans-serif`;

/** One line, shortened with an ellipsis rather than overflowing. */
export function fit(ctx, text, max) {
  let t = String(text ?? "");
  if (ctx.measureText(t).width <= max) return t;
  while (t.length > 1 && ctx.measureText(t + "…").width > max) t = t.slice(0, -1);
  return t.trimEnd() + "…";
}

/** The largest size at or below `px` at which `text` fits `max`, down to `min`. Used where the
 *  string is fixed and cutting it would be wrong -- the disclaimer, above all, which must be
 *  readable in full or it is not a disclaimer. */
export function shrinkToFit(ctx, text, max, px, min, fam, weight) {
  let size = px;
  while (size > min) {
    ctx.font = font(fam, weight, size);
    if (ctx.measureText(text).width <= max) return size;
    size -= 1;
  }
  ctx.font = font(fam, weight, min);
  return min;
}

/** Lays `n` blocks of the given heights into `avail`, spreading whatever is left over as equal gaps
 *  (at least `gapMin`). Without this a template written for a square leaves a void in a story:
 *  fixed offsets from the top cannot fill a canvas that is nearly twice as tall. */
export function spread(avail, heights, gapMin) {
  const used = heights.reduce((a, b) => a + b, 0);
  const slots = Math.max(1, heights.length - 1);
  return Math.max(gapMin, (avail - used) / slots);
}

/** Greedy wrap to `max` width, at most `lines` lines, last line shortened if it has to be. */
export function wrap(ctx, text, max, lines = 3) {
  const words = String(text ?? "").split(/\s+/).filter(Boolean);
  const out = [];
  let cur = "";
  for (const w of words) {
    const next = cur ? `${cur} ${w}` : w;
    if (ctx.measureText(next).width <= max || !cur) { cur = next; continue; }
    out.push(cur); cur = w;
    if (out.length === lines) break;
  }
  if (out.length < lines && cur) out.push(cur);
  if (out.length === lines && words.length) {
    const used = out.join(" ").split(/\s+/).length;
    if (used < words.length) out[lines - 1] = fit(ctx, `${out[lines - 1]} ${words.slice(used).join(" ")}`, max);
  }
  return out;
}

/** Draws wrapped text and returns the y just under it. */
export function block(ctx, text, x, y, max, { lineHeight, lines = 3, align = "left" } = {}) {
  const ls = wrap(ctx, text, max, lines);
  ctx.textAlign = align;
  ls.forEach((l, i) => ctx.fillText(l, x, y + i * lineHeight));
  return y + ls.length * lineHeight;
}

// ---------------------------------------------------------------- shapes
export function rr(ctx, x, y, w, h, r) {
  ctx.beginPath();
  if (ctx.roundRect) ctx.roundRect(x, y, w, h, r);
  else {                                        // one old Safari still in the wild
    const k = Math.min(r, w / 2, h / 2);
    ctx.moveTo(x + k, y); ctx.arcTo(x + w, y, x + w, y + h, k); ctx.arcTo(x + w, y + h, x, y + h, k);
    ctx.arcTo(x, y + h, x, y, k); ctx.arcTo(x, y, x + w, y, k); ctx.closePath();
  }
}

export function card(ctx, x, y, w, h, r, fill, stroke) {
  rr(ctx, x, y, w, h, r);
  if (fill) { ctx.fillStyle = fill; ctx.fill(); }
  if (stroke) { ctx.strokeStyle = stroke; ctx.lineWidth = 2; ctx.stroke(); }
}

/** A colour mixed toward another by `t` (0..1). The palette has no half-steps, and a surface that
 *  sits between two tokens is better computed than guessed at. */
export function mix(a, b, t) {
  const hex = (c) => [1, 3, 5].map((i) => parseInt(String(c).slice(i, i + 2), 16));
  const [r1, g1, b1] = hex(a), [r2, g2, b2] = hex(b);
  const to = (v) => Math.round(v).toString(16).padStart(2, "0");
  return `#${to(r1 + (r2 - r1) * t)}${to(g1 + (g2 - g1) * t)}${to(b1 + (b2 - b1) * t)}`;
}

export function alpha(c, a) {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(String(c).slice(i, i + 2), 16));
  return `rgba(${r},${g},${b},${a})`;
}

/** The background every template starts from: the base surface, with one soft wash of the accent
 *  behind the top corner so the image is not a flat rectangle. */
export function backdrop(ctx, w, h, p) {
  ctx.fillStyle = p.bg; ctx.fillRect(0, 0, w, h);
  const g = ctx.createRadialGradient(w * 0.82, -h * 0.08, 20, w * 0.82, -h * 0.08, Math.max(w, h) * 0.95);
  g.addColorStop(0, alpha(p.accent, 0.22)); g.addColorStop(0.55, alpha(p.accent, 0.05)); g.addColorStop(1, alpha(p.bg, 0));
  ctx.fillStyle = g; ctx.fillRect(0, 0, w, h);
}

/** A circular chip with an image in it, or the shield fallback the app draws when a crest is missing. */
export function chip(ctx, bmp, cx, cy, d, p) {
  ctx.save();
  ctx.fillStyle = p.surface2; ctx.beginPath(); ctx.arc(cx, cy, d / 2, 0, Math.PI * 2); ctx.fill();
  ctx.strokeStyle = alpha(p.text, 0.1); ctx.lineWidth = 2; ctx.stroke();
  if (bmp) {
    ctx.beginPath(); ctx.arc(cx, cy, d / 2 - 2, 0, Math.PI * 2); ctx.clip();
    const pad = d * 0.16, box = d - pad * 2;
    const r = Math.min(box / bmp.width, box / bmp.height);
    ctx.drawImage(bmp, cx - (bmp.width * r) / 2, cy - (bmp.height * r) / 2, bmp.width * r, bmp.height * r);
  } else {
    ctx.translate(cx - d * 0.3, cy - d * 0.3); ctx.scale((d * 0.6) / 24, (d * 0.6) / 24);
    ctx.strokeStyle = p.text3; ctx.lineWidth = 1.6;
    ctx.stroke(new Path2D("M12 2 4 5v6c0 5 3.4 9.4 8 11 4.6-1.6 8-6 8-11V5l-8-3z"));
  }
  ctx.restore();
}

/** A player photo: same chip, filled rather than fitted, because a head shot should crop not letterbox. */
export function portrait(ctx, bmp, cx, cy, d, p, initials, fam) {
  ctx.save();
  ctx.beginPath(); ctx.arc(cx, cy, d / 2, 0, Math.PI * 2);
  ctx.fillStyle = p.surface2; ctx.fill();
  if (bmp) {
    ctx.clip();
    const r = Math.max(d / bmp.width, d / bmp.height);
    ctx.drawImage(bmp, cx - (bmp.width * r) / 2, cy - (bmp.height * r) / 2, bmp.width * r, bmp.height * r);
  } else {
    ctx.fillStyle = p.text3; ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.font = font(fam, 700, d * 0.34);
    ctx.fillText(initials || "?", cx, cy);
    ctx.textBaseline = "alphabetic";
  }
  ctx.restore();
  ctx.beginPath(); ctx.arc(cx, cy, d / 2, 0, Math.PI * 2);
  ctx.strokeStyle = alpha(p.text, 0.14); ctx.lineWidth = 3; ctx.stroke();
}

// ---------------------------------------------------------------- product marks
/** The tier badge: the word plus one, two or three dots, exactly as Marks.jsx draws it, because
 *  colour never carries the meaning on its own (docs/03). */
export function tier(ctx, name, x, y, p, fam, scale = 1) {
  if (!name) return 0;
  const dots = { Strong: 3, Solid: 2, Watch: 1 }[name] || 0;
  const col = { Strong: p.tierStrong, Solid: p.tierSolid, Watch: p.tierWatch }[name] || p.text3;
  const fs = 26 * scale, pad = 16 * scale, r = 6 * scale, gap = 7 * scale, h = 48 * scale;
  ctx.font = font(fam, 700, fs);
  const tw = ctx.measureText(name).width;
  const w = pad + dots * (r * 2 + gap) + tw + pad;
  card(ctx, x, y, w, h, h / 2, alpha(col, 0.16), alpha(col, 0.5));
  let dx = x + pad + r;
  for (let i = 0; i < 3; i += 1) {
    ctx.beginPath(); ctx.arc(dx, y + h / 2, r, 0, Math.PI * 2);
    if (i < dots) { ctx.fillStyle = col; ctx.fill(); } else { ctx.strokeStyle = alpha(col, 0.45); ctx.lineWidth = 2 * scale; ctx.stroke(); }
    if (i < dots) dx += r * 2 + gap;
  }
  ctx.fillStyle = col; ctx.textAlign = "left"; ctx.textBaseline = "middle";
  ctx.fillText(name, x + pad + dots * (r * 2 + gap), y + h / 2 + 1);
  ctx.textBaseline = "alphabetic";
  return w;
}

/** The run strip: the product's signature graphic (docs/redesign/v2), at poster size.
 *  `games` are {v, m} oldest -> newest and `line` is the threshold, so a bar clears when v > line.
 *  The eleventh column is the forecast itself, dashed, so the history ends at the question. */
export function run(ctx, games, line, shown, x, y, w, h, p, fam, { down, label } = {}) {
  const known = (games || []).filter((g) => g && g.v != null);
  if (known.length < 3) return;
  const cols = known.length + 1;
  const gap = Math.max(6, w * 0.012);
  const bw = (w - gap * (cols - 1)) / cols;
  const vmax = Math.max(1, line + 1, ...known.map((g) => g.v));
  const need = Math.floor(line) + 1;
  const lab = Math.max(22, h * 0.12);
  const top = y, floor = y + h - lab;
  const hit = down ? p.text3 : p.accent;
  known.forEach((g, i) => {
    const bx = x + i * (bw + gap);
    const bh = Math.max(4, ((floor - top) * Math.min(g.v, vmax)) / vmax);
    const cleared = g.v > line;
    card(ctx, bx, floor - bh, bw, bh, Math.min(bw * 0.28, 14), cleared ? hit : alpha(p.text, 0.14));
    ctx.fillStyle = cleared ? p.onAccent : p.text3;
    ctx.font = font(fam, 800, Math.min(bw * 0.52, 30));
    ctx.textAlign = "center";
    if (bh > 36) ctx.fillText(String(g.v), bx + bw / 2, floor - bh + Math.min(bw * 0.52, 30) + 6);
    else { ctx.fillStyle = p.text3; ctx.fillText(String(g.v), bx + bw / 2, floor - bh - 8); }
  });
  // tonight
  const bx = x + known.length * (bw + gap);
  ctx.save();
  ctx.setLineDash([10, 8]); ctx.strokeStyle = p.accent; ctx.lineWidth = 3;
  const nh = (floor - top) * Math.min(need, vmax) / vmax;
  rr(ctx, bx, floor - nh, bw, nh, Math.min(bw * 0.28, 14)); ctx.stroke();
  ctx.restore();
  ctx.fillStyle = p.ink || p.accent; ctx.textAlign = "center";
  ctx.font = font(fam, 800, Math.min(bw * 0.46, 26));
  ctx.fillText(shown || "", bx + bw / 2, floor - nh - 12);
  // the line the strip is about
  const ly = floor - (floor - top) * Math.min(line, vmax) / vmax;
  ctx.save();
  ctx.setLineDash([4, 6]); ctx.strokeStyle = alpha(p.text, 0.35); ctx.lineWidth = 2;
  ctx.beginPath(); ctx.moveTo(x, ly); ctx.lineTo(x + w, ly); ctx.stroke();
  ctx.restore();
  ctx.fillStyle = p.text3; ctx.font = font(fam, 600, Math.max(22, Math.min(h * 0.075, w * 0.026))); ctx.textAlign = "left";
  ctx.fillText(label || `Last ${known.length} and tonight`, x, y + h - 2);
}

/** The likelihood as a measurement on a 0-100 axis: the band is the range, the segment runs from
 *  usual to forecast, the tick is usual. A filled meter would say "this number is big", which is
 *  the one thing the product must not say (ForecastCard.jsx). */
export function meter(ctx, { p: val, lo, hi, usual }, x, y, w, h, p) {
  card(ctx, x, y, w, h, h / 2, alpha(p.text, 0.12));
  if (lo != null && hi != null && hi > lo) {
    card(ctx, x + w * lo, y, Math.max(2, w * (hi - lo)), h, h / 2, alpha(p.text, 0.18));
  }
  const up = usual == null || val >= usual;
  const a = usual == null ? val : Math.min(val, usual);
  const len = usual == null ? 0.012 : Math.max(0.008, Math.abs(val - usual));
  card(ctx, x + w * a, y, Math.max(6, w * len), h, h / 2, up ? p.accent : p.down);
  if (usual != null) {
    ctx.fillStyle = p.text; ctx.fillRect(x + w * usual - 2, y - 6, 4, h + 12);
  }
}

// ---------------------------------------------------------------- the line every ad carries
/** docs/03: the disclaimer goes on anything a visitor sees, and an ad is the most public thing the
 *  product makes. There is no switch to remove it. */
export function footer(ctx, w, h, p, fam, { brand, logo, note, disclaimer }) {
  const pad = w * 0.062;
  const y = h - pad * 0.62;
  ctx.textAlign = "left";
  const bs = Math.max(26, w * 0.028);
  ctx.font = font(fam, 800, bs);
  let brandRight = pad;
  if (logo) {
    const d = Math.max(38, w * 0.045);
    chip(ctx, logo, pad + d / 2, y - d * 0.32, d, p);
    ctx.fillStyle = p.text;
    const bw = Math.min(ctx.measureText(brand || "").width, w * 0.34);
    ctx.fillText(fit(ctx, brand || "", w * 0.34), pad + d + 16, y - d * 0.32 + bs * 0.36);
    brandRight = pad + d + 16 + bw;
  } else {
    ctx.fillStyle = p.text;
    const bw = Math.min(ctx.measureText(brand || "").width, w * 0.4);
    ctx.fillText(fit(ctx, brand || "", w * 0.4), pad, y - 6);
    brandRight = pad + bw;
  }
  // The disclaimer is a fixed sentence and docs/03 requires it, so it is SIZED to fit rather than
  // cut: it was ending "...Not be" on every ad, which is worse than no line at all.
  const room = w - pad - brandRight - 24;
  ctx.textAlign = "right";
  ctx.fillStyle = p.text3;
  const lines = note ? [note, disclaimer] : [disclaimer];
  const step = Math.max(22, w * 0.024);
  lines.forEach((l, i) => {
    shrinkToFit(ctx, l, room, Math.max(17, w * 0.0185), 11, fam, 500);
    ctx.fillText(l, w - pad, y - 8 - (lines.length - 1 - i) * step);
  });
}
