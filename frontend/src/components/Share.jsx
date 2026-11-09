// Match share card: drawn in the browser on a canvas (crests from our own /api/media), then shared or saved as PNG.
//
// The colours used to be six hex literals taken from the Midnight palette, and this card went on
// drawing Midnight for two redesigns after it stopped being the brand -- a hex literal cannot go
// stale loudly. They come from the live palette now (lib/theme.js), so the card follows Site Studio
// and the reader's light or dark mode, exactly as the ad builder does (docs/60).
import { useState } from "react";
import { getBlob } from "../lib/api";
import { pct } from "../lib/copy";
import { useSite } from "../lib/site";
import { tokens } from "../lib/theme";
import { useToast } from "./Ui";
import Icon from "./Icon";
import { kickoff } from "./Football";

const W = 1200, H = 630;

async function bitmap(image) {
  if (!image) return null;
  try { return await createImageBitmap(await getBlob(image)); } catch { return null; }
}

function shield(ctx, x, y, s, col) {
  ctx.save(); ctx.translate(x, y); ctx.scale(s / 24, s / 24); ctx.strokeStyle = col; ctx.lineWidth = 1.4;
  ctx.stroke(new Path2D("M12 2 4 5v6c0 5 3.4 9.4 8 11 4.6-1.6 8-6 8-11V5l-8-3z")); ctx.restore();
}

// A token mixed toward another, for the one surface this card needs that the palette has no name for.
function mix(a, b, t) {
  const h = (c) => [1, 3, 5].map((i) => parseInt(String(c).slice(i, i + 2), 16));
  const [r1, g1, b1] = h(a), [r2, g2, b2] = h(b);
  const p = (v) => Math.round(v).toString(16).padStart(2, "0");
  return `#${p(r1 + (r2 - r1) * t)}${p(g1 + (g2 - g1) * t)}${p(b1 + (b2 - b1) * t)}`;
}

function fit(ctx, text, max) {
  let t = text;
  while (ctx.measureText(t).width > max && t.length > 3) t = t.slice(0, -2);
  return t === text ? t : t.trimEnd() + "…";
}

async function draw(d, brand) {
  const t = tokens();
  const c = document.createElement("canvas"); c.width = W; c.height = H;
  const ctx = c.getContext("2d");
  const g = ctx.createRadialGradient(W / 2, 0, 50, W / 2, 0, 900);
  g.addColorStop(0, mix(t.bg, t.brand, 0.22)); g.addColorStop(1, t.bg);
  ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
  const font = (w, s) => `${w} ${s}px system-ui, -apple-system, "Segoe UI", sans-serif`;
  const [hc, ac] = await Promise.all([bitmap(d.home.image), bitmap(d.away.image)]);
  [[hc, 300], [ac, 900]].forEach(([b, x]) => {
    ctx.fillStyle = t.surface1; ctx.beginPath(); ctx.arc(x, 200, 96, 0, Math.PI * 2); ctx.fill();
    if (b) { const r = Math.min(140 / b.width, 140 / b.height); ctx.drawImage(b, x - (b.width * r) / 2, 200 - (b.height * r) / 2, b.width * r, b.height * r); }
    else shield(ctx, x - 50, 150, 100, t.text3);
  });
  ctx.textAlign = "center"; ctx.fillStyle = t.text; ctx.font = font(800, 40);
  ctx.fillText(fit(ctx, d.home.name, 360), 300, 350); ctx.fillText(fit(ctx, d.away.name, 360), 900, 350);
  ctx.fillStyle = t.text2; ctx.font = font(600, 26);
  const m = d.match;
  ctx.fillText(m.status === "final" && m.hg != null ? `${m.hg} – ${m.ag}` : "v", 600, 210);
  ctx.font = font(500, 24); ctx.fillText(kickoff(m.kickoff), 600, 250);
  if (d.probs) {
    const parts = [[d.probs.p_home, t.brand], [d.probs.p_draw, t.text3], [d.probs.p_away, t.accent]];
    let x = 150;
    parts.forEach(([p, col]) => { const w = 900 * p; ctx.fillStyle = col; ctx.fillRect(x, 392, w, 34); ctx.fillStyle = t.bg; ctx.font = font(700, 20); if (w > 50) ctx.fillText(pct(p), x + w / 2, 416); x += w; });
  }
  const top = [...d.forecasts].sort((a, b) => b.p - a.p)[0];
  if (top) {
    const who = top.player?.name || (top.team_iid === m.home_iid ? d.home.name : d.away.name);
    ctx.fillStyle = t.surface2; ctx.beginPath(); ctx.roundRect(150, 456, 900, 96, 20); ctx.fill();
    ctx.textAlign = "left"; ctx.fillStyle = t.text2; ctx.font = font(600, 20); ctx.fillText("Top forecast", 182, 492);
    ctx.fillStyle = t.text; ctx.font = font(800, 30); ctx.fillText(fit(ctx, `${who} · ${top.market}`, 680), 182, 532);
    ctx.textAlign = "right"; ctx.fillStyle = t.accent; ctx.font = font(800, 44); ctx.fillText(pct(top.p), 1018, 528);
  }
  ctx.textAlign = "left"; ctx.fillStyle = t.text; ctx.font = font(800, 24); ctx.fillText(brand?.name || "Forecast Zone", 40, 600);
  if (brand?.site) { ctx.fillStyle = t.text3; ctx.font = font(600, 18); ctx.fillText(brand.site, 40, 626); }
  ctx.textAlign = "right"; ctx.fillStyle = t.text3; ctx.font = font(500, 18); ctx.fillText("Statistical analysis for information and entertainment.", W - 40, 600);
  return new Promise((ok) => c.toBlob(ok, "image/png"));
}

export function ShareCard({ d }) {
  const { cfg } = useSite();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const go = async () => {
    setBusy(true);
    try {
      const blob = await draw(d, cfg?.brand);
      const name = `${d.home.name}-v-${d.away.name}.png`.replace(/\s+/g, "-");
      const file = new File([blob], name, { type: "image/png" });
      if (navigator.canShare?.({ files: [file] })) {
        await navigator.share({ files: [file], title: `${d.home.name} v ${d.away.name}`, url: window.location.href });
      } else {
        const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = name; a.click();
        setTimeout(() => URL.revokeObjectURL(a.href), 4000);
        toast("Share card saved as an image");
      }
    } catch (x) { if (x?.name !== "AbortError") toast("Could not make the share card", "err"); } finally { setBusy(false); }
  };
  return <button type="button" className="btn btn--secondary btn--sm share-btn" onClick={go} disabled={busy} data-testid="match-share"><Icon name="send" size={16} />{busy ? "Making card…" : "Share card"}</button>;
}
