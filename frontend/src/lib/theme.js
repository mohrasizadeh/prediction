// The live palette, read back off the document (docs/60).
//
// GET /api/site/config carries the COMPILED CSS, not the token values, so anything that has to draw
// with the brand colours -- a canvas, which cannot use a CSS variable -- has to read them from the
// style the site injected. That is also why this is only for the public app: the admin panel has its
// own palette on `.admin`, so an admin screen that needs the SITE colours asks the API for them
// (routes_ads.brand_kit) rather than reading the document it is drawn in.
//
// The hazard this exists to remove: ShareCard hardcoded six hex values and went on drawing the
// palette those values came from for two redesigns after it was replaced, because a hex literal
// cannot go stale loudly.
const FALLBACK = {
  bg: "#22281E", surface1: "#2A3026", surface2: "#32382F", border: "#3C4238",
  text: "#F4F7F3", text2: "#DDE0DB", text3: "#979C94",
  brand: "#38D996", onBrand: "#22281E", accent: "#A9FF9B", onAccent: "#22281E",
  tierStrong: "#A9FF9B", tierSolid: "#38D996", tierWatch: "#979C94",
  up: "#38D996", down: "#FF8A7A",
};
// token name -> the CSS custom property compile_css() emits for it
const VAR = {
  bg: "--bg", surface1: "--surface1", surface2: "--surface2", border: "--border",
  text: "--text", text2: "--text2", text3: "--text3",
  brand: "--brand", onBrand: "--on-brand", accent: "--accent", onAccent: "--on-accent",
  tierStrong: "--tier-strong", tierSolid: "--tier-solid", tierWatch: "--tier-watch",
  up: "--up", down: "--down",
};

/** The site's own type stack, for a canvas (which cannot use a CSS variable). */
export function fontStack(which = "heading") {
  try {
    const v = getComputedStyle(document.documentElement).getPropertyValue(`--font-${which}`).trim();
    if (v) return v;
  } catch { /* no document */ }
  return "system-ui, sans-serif";
}

/** The palette in use right now, in the mode the reader is actually looking at. */
export function tokens(el) {
  const out = { ...FALLBACK };
  try {
    const cs = getComputedStyle(el || document.documentElement);
    Object.entries(VAR).forEach(([k, v]) => {
      const raw = cs.getPropertyValue(v).trim();
      // Only a plain hex is usable on a canvas: a color-mix() would have to be resolved first, and
      // every token compile_css() writes is a hex.
      if (/^#[0-9A-Fa-f]{6}$/.test(raw)) out[k] = raw;
    });
  } catch { /* no document (a test): the fallback is the shipped default palette */ }
  return out;
}
