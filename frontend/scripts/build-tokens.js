// Turns docs/design_tokens.json into src/styles/tokens.css. Run: yarn tokens (after changing the JSON).
// Site Studio (docs/16) overrides these at run time with the published site config.
const fs = require("fs");
const path = require("path");
const t = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "..", "docs", "design_tokens.json"), "utf8"));
const kebab = (s) => s.replace(/[A-Z]/g, (m) => "-" + m.toLowerCase());
const vars = (o) => Object.entries(o).map(([k, v]) => `  --c-${kebab(k)}: ${v};`).join("\n");
const fonts = Object.entries(t.font.scale_px).map(([k, v]) => `  --fs-${k}: ${v}px;`).join("\n");
const radius = Object.entries(t.radius_px).map(([k, v]) => `  --r-${k}: ${v}px;`).join("\n");
const space = t.space_px.map((v, i) => `  --s-${i}: ${v}px;`).join("\n");
const css = `/* Generated from docs/design_tokens.json by scripts/build-tokens.js. Do not edit by hand. */
:root {
${vars(t.color.dark)}
  --shadow-card: ${t.elevation.dark.card};
  --font: ${t.font.family};
  --font-features: ${t.font.features};
${fonts}
${radius}
${space}
  --motion-fast: ${t.motion_ms.fast}ms;
  --motion-base: ${t.motion_ms.base}ms;
  --ease: ${t.easing};
  --max-width: ${t.layout.maxWidth_px}px;
  --header-h: ${t.layout.headerHeight_px}px;
  --bottom-tab-h: ${t.layout.bottomTabHeight_px}px;
}
:root[data-theme="light"] {
${vars(t.color.light)}
  --shadow-card: ${t.elevation.light.card};
}
@media (prefers-color-scheme: light) {
  :root:not([data-theme="dark"]) {
${vars(t.color.light).replace(/^/gm, "  ")}
    --shadow-card: ${t.elevation.light.card};
  }
}
`;
fs.writeFileSync(path.join(__dirname, "..", "src", "styles", "tokens.css"), css);
console.log("tokens.css written");
