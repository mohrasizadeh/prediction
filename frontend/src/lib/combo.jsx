// The open combo (docs/28): lines from ONE match, kept in this browser tab (sessionStorage) until saved or cleared.
// Cards add and remove lines with toggle(card). The bar and the review sheet read the combined chance from
// POST /api/combo/estimate; nothing here does probability maths.
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { DISCLAIMER } from "./copy";

const KEY = "combo.open";
const Ctx = createContext(null);

const load = () => { try { return JSON.parse(sessionStorage.getItem(KEY)) || null; } catch { return null; } };
const store = (v) => { try { v ? sessionStorage.setItem(KEY, JSON.stringify(v)) : sessionStorage.removeItem(KEY); } catch { /* private window: the combo lives in memory */ } };

export const entityOf = (f) => (f.player_iid != null ? `p${f.player_iid}` : f.player?.id ? `p${f.player.id}` : `t${f.team_iid ?? f.team?.id}`);

// What we keep per line: enough to draw the bar and the sheet without another request.
export function lineOf(f) {
  const name = f.player?.name || f.team?.name || "";
  return {
    fkey: f.fkey, id: f.id || null, entity: entityOf(f), stat: f.stat, scope: f.scope, name, market: f.market, p: f.p,
    player: f.player ? { id: f.player.id, name: f.player.name, image: f.player.image } : null,
    team: f.team ? { id: f.team.id, name: f.team.name, image: f.team.image } : null,
    more: [...(f.more_lines || [])].filter((x) => x.fkey).map((x) => ({ fkey: x.fkey, market: x.market, p: x.p })),
  };
}

export function ComboProvider({ children }) {
  const [combo, setCombo] = useState(load);              // {match_iid, match_id, label, lines: [...]} or null
  const [ask, setAsk] = useState(null);                   // a card waiting for "Start a new combo?"
  const [open, setOpen] = useState(false);                // the review sheet
  const [flash, setFlash] = useState(null);               // a short plain message ("A combo holds up to 6 lines.")
  useEffect(() => store(combo), [combo]);
  useEffect(() => {
    const on = (e) => e.key === KEY && setCombo(load());
    window.addEventListener("storage", on);
    return () => window.removeEventListener("storage", on);
  }, []);
  useEffect(() => { if (!flash) return undefined; const t = setTimeout(() => setFlash(null), 3500); return () => clearTimeout(t); }, [flash]);

  const has = useCallback((fkey) => !!combo?.lines.some((l) => l.fkey === fkey), [combo]);

  const start = useCallback((f, meta) => setCombo({ match_iid: f.match_iid, match_id: meta?.match_id || f.match_id || null, label: meta?.label || null, lines: [lineOf(f)] }), []);

  const toggle = useCallback((f, meta, max = 6) => {
    if (!f?.fkey || f.match_iid == null) return;
    setCombo((c) => {
      if (!c || !c.lines.length) return { match_iid: f.match_iid, match_id: meta?.match_id || f.match_id || null, label: meta?.label || null, lines: [lineOf(f)] };
      if (c.match_iid !== f.match_iid) { setAsk({ f, meta }); return c; }
      if (c.lines.some((l) => l.fkey === f.fkey)) {
        const lines = c.lines.filter((l) => l.fkey !== f.fkey);
        return lines.length ? { ...c, lines } : null;
      }
      const ent = entityOf(f);
      const same = c.lines.findIndex((l) => l.entity === ent && l.stat === f.stat);
      if (same >= 0) { const lines = [...c.lines]; lines[same] = lineOf(f); return { ...c, lines }; }      // one line per stat for each player or team
      if (c.lines.length >= max) { setFlash(`A combo holds up to ${max} lines.`); return c; }
      return { ...c, lines: [...c.lines, lineOf(f)], match_id: c.match_id || meta?.match_id || f.match_id || null };
    });
  }, []);

  const swap = useCallback((fromKey, alt) => setCombo((c) => c && ({ ...c, lines: c.lines.map((l) => (l.fkey === fromKey
    ? { ...l, fkey: alt.fkey, market: alt.market, p: alt.p, more: [{ fkey: l.fkey, market: l.market, p: l.p }, ...l.more.filter((x) => x.fkey !== alt.fkey)] } : l)) })), []);

  const clear = useCallback(() => { setCombo(null); setOpen(false); }, []);
  // Replace the whole combo (Build one for me).
  const replace = useCallback((est) => setCombo({
    match_iid: est.match_iid, match_id: est.match_id || null, label: est.label || null,
    lines: est.lines.map((l) => ({ fkey: l.fkey, id: l.id, entity: l.player ? `p${l.player.id}` : `t${l.team?.id}`, stat: l.stat, scope: l.scope,
      name: l.player?.name || l.team?.name || "", market: l.market, p: l.p, player: l.player, team: l.team, more: [] })),
  }), []);
  const confirmAsk = useCallback(() => { if (ask) start(ask.f, ask.meta); setAsk(null); }, [ask, start]);

  const value = useMemo(() => ({ combo, count: combo?.lines.length || 0, has, toggle, swap, clear, replace, ask, setAsk, confirmAsk, open, setOpen, flash }),
    [combo, has, toggle, swap, clear, replace, ask, confirmAsk, open, flash]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export const useCombo = () => useContext(Ctx) || { combo: null, count: 0, has: () => false, toggle: () => {}, swap: () => {}, clear: () => {}, replace: () => {}, setOpen: () => {} };

// ------------------------------------------------------------------ words and pictures (docs/28 §8)
export const comboText = (est, label) => [
  label, ...est.lines.map((l) => `${l.player?.name || l.team?.name} ${l.market}: ${Math.round(l.chance * 100)}%`),
  `All together: ${Math.round(est.combined * 100)}% (${est.plain})`,
  `Forecast${est.state === "pre" ? " before lineups" : ""}. Prediciotn`,
].filter(Boolean).join("\n");

// The share card, drawn on a canvas (no network, no photos): 1080 x auto PNG blob.
export function drawCard(est, label, when) {
  const W = 1080, pad = 64, rowH = 112, H = 360 + est.lines.length * rowH + 220;
  const c = document.createElement("canvas"); c.width = W; c.height = H;
  const g = c.getContext("2d");
  const grad = g.createLinearGradient(0, 0, W, H); grad.addColorStop(0, "#171d36"); grad.addColorStop(1, "#0f1424");
  g.fillStyle = grad; g.fillRect(0, 0, W, H);
  const font = (w, s) => { g.font = `${w} ${s}px Inter, "Plus Jakarta Sans", system-ui, sans-serif`; };
  g.fillStyle = "#7C83FF"; g.beginPath(); g.arc(pad + 22, pad + 22, 22, 0, 7); g.fill();
  g.fillStyle = "#E9EEF7"; font(700, 34); g.textBaseline = "middle"; g.fillText("Prediciotn", pad + 62, pad + 22);
  g.fillStyle = "#A3AFC6"; font(600, 28); g.textAlign = "right"; g.fillText(when || "", W - pad, pad + 22); g.textAlign = "left";
  g.fillStyle = "#E9EEF7"; font(800, 68); g.fillText(label || "Your combo", pad, 190);
  g.fillStyle = "#A3AFC6"; font(500, 30); g.fillText(`${est.lines.length} lines · forecast${est.state === "pre" ? " before lineups" : ""}`, pad, 250);
  let y = 320;
  est.lines.forEach((l) => {
    g.strokeStyle = "rgba(255,255,255,.1)"; g.beginPath(); g.moveTo(pad, y); g.lineTo(W - pad, y); g.stroke();
    g.fillStyle = "#E9EEF7"; font(700, 38); g.textAlign = "left"; g.fillText(`${l.player?.name || l.team?.name} · ${l.market}`, pad, y + rowH / 2);
    font(700, 44); g.textAlign = "right"; g.fillText(`${Math.round(l.chance * 100)}%`, W - pad, y + rowH / 2); g.textAlign = "left";
    y += rowH;
  });
  g.strokeStyle = "rgba(255,255,255,.18)"; g.beginPath(); g.moveTo(pad, y + 8); g.lineTo(W - pad, y + 8); g.stroke();
  g.fillStyle = "#A3AFC6"; font(700, 26); g.fillText("ALL TOGETHER", pad, y + 56);
  g.fillStyle = "#E9EEF7"; font(800, 120); g.fillText(`${Math.round(est.combined * 100)}%`, pad, y + 140);
  g.textAlign = "right"; font(700, 40); g.fillText(est.plain, W - pad, y + 130); g.textAlign = "left";
  g.fillStyle = "#8A96AE"; font(500, 24); g.fillText(DISCLAIMER, pad, H - 48);
  return new Promise((res) => c.toBlob(res, "image/png"));
}
