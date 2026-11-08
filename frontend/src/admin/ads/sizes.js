// The sizes an ad exports at, and the palette shape every template reads (docs/60).
// These mirror backend/ads.py SIZES; the screen gets the list from the API, and these are the
// numbers the renderer lays out in, so a template never carries a pixel size of its own.
export const SIZES = {
  square: { w: 1080, h: 1080 },
  portrait: { w: 1080, h: 1350 },
  story: { w: 1080, h: 1920 },
  landscape: { w: 1200, h: 630 },
  wide: { w: 1600, h: 900 },
};

// Tokens a template may read. Taken straight off the Site Studio palette for the chosen mode, with
// `accent` falling back to brand so a palette with no accent still draws.
export function palette(colors, mode, accentOverride) {
  const c = (colors && colors[mode]) || {};
  const p = {
    bg: c.bg || "#101114", surface1: c.surface1 || "#18191C", surface2: c.surface2 || "#212224", surface3: c.surface3 || "#2B2C2F",
    border: c.border || "#313235", text: c.text || "#FFFFFF", text2: c.text2 || "#C6CBD2", text3: c.text3 || "#8E97A2",
    brand: c.brand || "#6079EE", onBrand: c.onBrand || "#101114",
    accent: accentOverride || c.accent || c.brand || "#C6F04A", onAccent: c.onAccent || c.bg || "#101114",
    tierStrong: c.tierStrong || c.accent || "#C6F04A", tierSolid: c.tierSolid || c.brand || "#6079EE", tierWatch: c.tierWatch || c.text3 || "#8E97A2",
    up: c.up || c.accent || "#C6F04A", down: c.down || "#F2555F",
  };
  return p;
}

// One scale knob per size, so a template written at square proportions reads correctly in a
// letterbox without a second layout. Landscape and wide are short, so their type comes down.
export const SCALE = { square: 1, portrait: 1, story: 1.04, landscape: 0.82, wide: 0.9 };
