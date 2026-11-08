// Turning a template into pixels, and pixels into a file (docs/60).
//
// Two things have to be true before a canvas draws the right thing, and both of them are about the
// page the canvas lives on rather than the canvas itself:
//   1. the site font must be LOADED in this document, because ctx.font falls back silently -- an ad
//      drawn before the face arrives is an ad in the admin panel's typeface;
//   2. the crests must be fetched as bitmaps first, because drawImage cannot wait.
import { bitmap } from "./draw";
import { SIZES, SCALE, palette } from "./sizes";
import { TEMPLATES, needed } from "./templates";
import { zip } from "../../lib/zip";

const FACE_ID = "ads-fonts";

/** Injects the site's own @font-face into the admin document and waits for the faces to arrive.
 *  The admin panel has its own typeface, so without this every ad would be drawn in that one. */
export async function ensureFonts(brand) {
  const faces = (brand?.font?.faces || []).filter((f) => /^\/fonts\/[a-z0-9-]+\.woff2$/.test(f.url || ""));
  let el = document.getElementById(FACE_ID);
  if (!el) { el = document.createElement("style"); el.id = FACE_ID; document.head.appendChild(el); }
  // The family name must be the one the CSS stack asks for. font_faces() reports the font's LABEL,
  // which is "Archivo" while the stack says "Archivo v2", so both names get a face and whichever
  // the stack names is the one that resolves.
  const want = [brand?.font?.body_family, brand?.font?.heading_family].filter(Boolean);
  el.textContent = faces.flatMap((f) => {
    const names = Array.from(new Set([f.family, ...want]));
    return names.map((n) => `@font-face{font-family:'${String(n).replace(/'/g, "")}';src:url(${f.url}) format('woff2');font-weight:100 900;font-display:block;}`);
  }).join("\n");
  const fams = Array.from(new Set(want));
  try {
    await Promise.all(fams.flatMap((f) => [400, 600, 700, 800].map((w) => document.fonts.load(`${w} 64px "${f}"`))));
    await document.fonts.ready;
  } catch { /* a missing face falls back to system-ui, which still draws */ }
}

/** Everything a template reads, assembled once so a preview and an export cannot differ. */
export async function buildData({ design, brand, card, cards, mode }) {
  const logo = (mode === "light" ? brand?.logo_light || brand?.logo_dark : brand?.logo_dark || brand?.logo_light) || "";
  const want = needed(design.template, card, cards, logo);
  const keys = Object.keys(want).filter((k) => k !== "rows");
  const got = await Promise.all(keys.map((k) => bitmap(want[k])));
  const rows = want.rows ? await Promise.all(want.rows.map((u) => bitmap(u))) : undefined;
  const images = Object.fromEntries(keys.map((k, i) => [k, got[i]]));
  if (rows) images.rows = rows;
  return {
    card, cards, brand: brand?.name || "", disclaimer: brand?.disclaimer || "", images,
    text: {
      headline: design.headline || "", subhead: design.subhead || "", kicker: design.kicker || "",
      cta: design.cta || "", footnote: design.footnote || "", finder_q: design.finder_q || "",
      stat_value: design.stat_value || "",
    },
  };
}

/** Draws one ad onto `canvas` at the size's real pixel dimensions. */
export function paint(canvas, { design, brand, data, mode, accent }) {
  const size = SIZES[design.size] || SIZES.square;
  canvas.width = size.w; canvas.height = size.h;
  const ctx = canvas.getContext("2d");
  const p = palette(brand?.colors, mode, accent || undefined);
  const t = {
    body: brand?.font?.body_family || "system-ui",
    heading: brand?.font?.heading_family || brand?.font?.body_family || "system-ui",
    s: SCALE[design.size] ?? 1,
  };
  ctx.save();
  ctx.textBaseline = "alphabetic";
  (TEMPLATES[design.template] || TEMPLATES.quote)(ctx, size.w, size.h, p, t, data);
  ctx.restore();
  return canvas;
}

export const blobOf = (canvas) => new Promise((ok) => canvas.toBlob(ok, "image/png"));

export function saveBlob(blob, name) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 8000);
}

/** The share sheet where the browser has one, a download where it does not. Nothing is posted to a
 *  network from here: that was the owner's instruction, and it needs no account. */
export async function shareOrSave(blob, name, title) {
  const file = new File([blob], name, { type: "image/png" });
  if (navigator.canShare?.({ files: [file] })) {
    try { await navigator.share({ files: [file], title }); return "shared"; }
    catch (e) { if (e?.name === "AbortError") return "cancelled"; }
  }
  saveBlob(blob, name);
  return "saved";
}

/** A carousel: every slide rendered, then one zip. */
export async function saveZip(blobs, base) {
  const files = await Promise.all(blobs.map(async (b, i) => ({
    name: `${base}-${String(i + 1).padStart(2, "0")}.png`,
    data: new Uint8Array(await b.arrayBuffer()),
  })));
  saveBlob(zip(files), `${base}.zip`);
}

export const slug = (s) => String(s || "ad").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 48) || "ad";
