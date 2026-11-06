// "Build one for me" (docs/28 §1, board 3): three short combos for this match, from GET /api/matches/{id}/combo-suggest.
import { useEffect, useState } from "react";
import { get } from "../lib/api";
import { useCombo } from "../lib/combo";
import { pct } from "../lib/copy";
import Icon from "./Icon";
import { Crest, PlayerAvatar } from "./Media";
import { BottomSheet } from "./ui";

const MODES = [
  { id: "safer", label: "Safer", sub: "2 lines · each 80% or more" },
  { id: "balanced", label: "Balanced", sub: "3 lines · each 65% or more" },
  { id: "bolder", label: "Bolder", sub: "4 lines · each 55% or more" },
];

export default function BuildForMe({ matchId }) {
  const [show, setShow] = useState(false);
  const [mode, setMode] = useState("balanced");
  const [res, setRes] = useState({});
  const [err, setErr] = useState(null);
  const { replace, setOpen } = useCombo();
  useEffect(() => {
    if (!show) return undefined;
    let live = true;
    setErr(null);
    Promise.all(MODES.map((m) => get(`/matches/${matchId}/combo-suggest`, { mode: m.id }).then((r) => [m.id, r]).catch((e) => [m.id, { error: e.message || "We could not build that one." }])))
      .then((r) => live && setRes(Object.fromEntries(r)));
    return () => { live = false; };
  }, [show, matchId]);
  const cur = res[mode];
  const ready = cur && !cur.error && cur.lines?.length;
  const use = () => { replace(cur); setShow(false); setOpen(true); };
  return (
    <>
      <button type="button" className="btn btn--secondary btn--sm cb-build" onClick={() => setShow(true)} data-testid="combo-build"><Icon name="sparkles" size={16} />Build one for me</button>
      <BottomSheet open={show} onClose={() => setShow(false)} title="Build one for me" testid="combo-build-sheet"
        footer={<div className="cb-actions">
          <button type="button" className="btn btn--primary" disabled={!ready} onClick={use} data-testid="combo-build-use">Use this combo</button>
          <button type="button" className="btn btn--secondary" onClick={() => setShow(false)} data-testid="combo-build-own">Choose lines myself</button>
        </div>}>
        <div className="cb-modes" role="radiogroup" aria-label="How bold">
          {MODES.map((m) => {
            const r = res[m.id];
            return (
              <button key={m.id} type="button" role="radio" aria-checked={mode === m.id} className={"cb-mode" + (mode === m.id ? " on" : "")} onClick={() => setMode(m.id)} data-testid={`combo-mode-${m.id}`}>
                <span className="cb-radio" aria-hidden="true" />
                <span className="cb-mode-t"><b>{m.label}</b><small>{m.sub}</small></span>
                <span className="cb-mode-p">{!r ? "\u2026" : r.lines?.length
                  ? <><b>{pct(r.combined)}</b><small>{r.plain}</small></>
                  /* "None yet" sounded like something was still loading. What it means is that
                     this match does not get there, and the reader is owed the distance. */
                  : <small className="cb-mode-none">{r.best != null ? <>best line {pct(r.best)}</> : "Not available"}</small>}</span>
              </button>
            );
          })}
        </div>
        {err && <p className="cb-err" role="alert">{err}</p>}
        {cur?.error && <p className="cb-err" role="alert">{cur.error}</p>}
        {cur && !cur.error && !cur.lines?.length && <p className="muted" data-testid="combo-build-none">{cur.reason || "Not enough confident lines for this match yet."}</p>}
        {ready && (
          <div data-testid="combo-build-lines">
            <p className="small"><b>{MODES.find((m) => m.id === mode).label} combo</b> <span className="muted">· Chance includes playing</span></p>
            <ul className="cb-lines">{cur.lines.map((l) => (
              <li key={l.fkey} className="cb-line"><div className="cb-line-row"><span className="cb-line-main">
                {l.player ? <PlayerAvatar player={l.player} size={36} /> : <Crest team={l.team} size={36} />}
                <span className="cb-line-t"><b>{l.player?.name || l.team?.name} · {l.market}</b><small>{l.scope === "player" ? `${pct(l.p)} if he plays · ${pct(l.p_play)} to play` : "Team line"}</small></span>
                <b className="cb-line-p">{pct(l.chance)}</b></span></div></li>))}
            </ul>
            <p className="small muted">We never suggest a player we are unsure will play. Before lineups we add a small, tested correction to the combined chance.</p>
          </div>
        )}
      </BottomSheet>
    </>
  );
}
