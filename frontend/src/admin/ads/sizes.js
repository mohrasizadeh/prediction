// Sizes, safe areas and the palette an ad is drawn with (docs/60 section 3).
// Mirrors backend/ad_plan.SIZES; the batch only ever uses the three the owner posts.
export const SIZES = {
  square: { w: 1080, h: 1080 },
  portrait: { w: 1080, h: 1350 },
  story: { w: 1080, h: 1920 },
  landscape: { w: 1200, h: 630 },
  wide: { w: 1600, h: 900 },
};

// Where the platform's own interface sits on top of the image.
//
// A story and a reel are the same 1080x1920 file, and the reel is the harsher of the two: the
// profile row and the close button take the top, and the caption, the audio strip and the row of
// buttons take far more of the bottom than a story does. Anything drawn there is covered. So the
// story layout is given 260 at the top and 420 at the bottom and lays itself out in what is left --
// the background still fills the whole frame, only the CONTENT is inset.
//
// A feed post has nothing over it, so square and portrait keep a plain margin.
export const SAFE = {
  square: { top: 0, right: 0, bottom: 0, left: 0 },
  portrait: { top: 0, right: 0, bottom: 0, left: 0 },
  story: { top: 260, right: 0, bottom: 420, left: 0 },
  landscape: { top: 0, right: 0, bottom: 0, left: 0 },
  wide: { top: 0, right: 0, bottom: 0, left: 0 },
};

export const inner = (size) => {
  const s = SIZES[size] || SIZES.square;
  const k = SAFE[size] || SAFE.square;
  return { x: k.left, y: k.top, w: s.w - k.left - k.right, h: s.h - k.top - k.bottom };
};

// ---------------------------------------------------------------- contrast
// An ad is read at arm's length on a phone, and the light palette has a colour in it that cannot
// carry text: Sprout #A9FF9B on Chalk #F4F7F3 is about 1.3:1, so "72%" in the accent was a pale
// smear on white. The fix is not to abandon the brand colour -- it is to pick, from the brand's own
// colours, the one that passes against this background, and to darken it only if none of them do.
const chan = (c) => [1, 3, 5].map((i) => parseInt(String(c).slice(i, i + 2), 16));
const lin = (v) => { const s = v / 255; return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4; };
export function lum(c) { const [r, g, b] = chan(c); return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b); }
export function contrast(a, b) {
  const [x, y] = [lum(a), lum(b)].sort((m, n) => n - m);
  return (x + 0.05) / (y + 0.05);
}
const toHex = (n) => Math.max(0, Math.min(255, Math.round(n))).toString(16).padStart(2, "0");
const blend = (a, b, t) => {
  const [r1, g1, b1] = chan(a), [r2, g2, b2] = chan(b);
  return `#${toHex(r1 + (r2 - r1) * t)}${toHex(g1 + (g2 - g1) * t)}${toHex(b1 + (b2 - b1) * t)}`;
};

/** `c` moved toward black or white -- whichever direction the background is not -- until it clears
 *  `min` against `bg`. Keeps the hue; only the lightness gives. */
export function ensure(c, bg, min) {
  if (contrast(c, bg) >= min) return c;
  const target = lum(bg) > 0.4 ? "#000000" : "#FFFFFF";
  for (let t = 0.08; t <= 1.0001; t += 0.08) {
    const out = blend(c, target, t);
    if (contrast(out, bg) >= min) return out;
  }
  return target;
}

/** The best of the brand's own colours for this background, then forced to clear `min`. */
function brandish(cands, bg, min) {
  const have = cands.filter(Boolean);
  const pass = have.filter((c) => contrast(c, bg) >= min);
  if (pass.length) return pass.sort((a, b) => contrast(b, bg) - contrast(a, bg))[0];
  const best = have.sort((a, b) => contrast(b, bg) - contrast(a, bg))[0];
  return ensure(best || "#000000", bg, min);
}

// WCAG 1.4.3 and 1.4.11: 4.5 for body text, 3.0 for large text and for a graphic that carries
// meaning -- which the run bars do, so they are held to 3.0 and not merely to "looks fine".
const TEXT_MIN = 4.5;
const GRAPHIC_MIN = 3.0;

export function palette(colors, mode, accentOverride) {
  const c = (colors && colors[mode]) || {};
  const bg = c.bg || (mode === "light" ? "#F4F7F3" : "#101114");
  const text = c.text || (mode === "light" ? "#22281E" : "#FFFFFF");
  const surface1 = c.surface1 || (mode === "light" ? "#FFFFFF" : "#18191C");
  // The candidates, in the order we would rather use them. An override is the owner's choice, so it
  // leads -- but it is still held to the contrast bar, because an unreadable ad is not a brand.
  const cands = [accentOverride, c.accent, c.brand, c.tierStrong, c.tierSolid].filter(Boolean);
  const fill = brandish(cands, bg, GRAPHIC_MIN);        // bars, buttons, the meter segment
  const ink = brandish(cands, bg, TEXT_MIN);            // anything accent-coloured that is WORDS
  const text3 = ensure(c.text3 || (mode === "light" ? "#62685F" : "#8E97A2"), bg, TEXT_MIN);
  return {
    bg, surface1, surface2: c.surface2 || surface1, surface3: c.surface3 || surface1,
    border: c.border || (mode === "light" ? "#D3D7D2" : "#313235"),
    text, text2: ensure(c.text2 || text, bg, TEXT_MIN), text3,
    brand: c.brand || fill, onBrand: c.onBrand || bg,
    accent: fill, ink,
    // What goes ON the accent fill: the palette's own answer if it is legible, otherwise forced.
    onAccent: ensure(c.onAccent || bg, fill, TEXT_MIN),
    tierStrong: ensure(c.tierStrong || fill, bg, GRAPHIC_MIN),
    tierSolid: ensure(c.tierSolid || fill, bg, GRAPHIC_MIN),
    tierWatch: ensure(c.tierWatch || text3, bg, GRAPHIC_MIN),
    up: fill, down: ensure(c.down || "#F2555F", bg, GRAPHIC_MIN),
    // Sprout behind dark text is the one place the light palette's brightest colour belongs.
    wash: c.accent || fill,
    mode,
  };
}

export const SCALE = { square: 1, portrait: 1, story: 1.04, landscape: 0.82, wide: 0.9 };
