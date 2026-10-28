// Forecast detail sheet (docs/24): every line, the top 3 reasons, chance he plays, lineup status, last 10 games,
// our record on this tier (only once the track record is ready), Save and Share. Reads our own API only.
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { get, put } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { DISCLAIMER, pct } from "../../lib/copy";
import { PlayerAvatar, Crest } from "../Media";
import { SaveButton } from "../Actions";
import { BottomSheet } from "./BottomSheet";
import { HitStrip } from "./Marks";
import { timeOf } from "./ForecastCard";

function useSheetData(open, f) {
  const [d, setD] = useState({ hits: null, record: null });
  useEffect(() => {
    if (!open) return undefined;
    let stop = false;
    const strip = (r) => { if (!stop) setD((x) => ({ ...x, hits: (r.games || []).filter((g) => g[f.stat] != null).map((g) => g[f.stat] > f.thr).reverse() })); };
    if (f.player?.id && f.scope === "player") get(`/players/${f.player.id}/history`, { last: 10 }).then(strip).catch(() => {});
    else if (f.scope === "team" && f.team?.id) get(`/teams/${f.team.id}/history`, { stat: f.stat, last: 10 }).then(strip).catch(() => {});
    get("/track-record", { scope: f.scope, stat: f.stat }).then((r) => { if (!stop) setD((x) => ({ ...x, record: r })); }).catch(() => {});
    return () => { stop = true; };
  }, [open, f]);
  return d;
}

function NoteBox({ player, testid }) {
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [msg, setMsg] = useState("");
  useEffect(() => {
    if (!open || !user) return;
    get(`/me/notes/${player.id}`).then((r) => setText(r.text || "")).catch(() => {});
  }, [open, user, player.id]);
  if (!user) return <Link to="/sign-in" className="btn btn--ghost" data-testid={`${testid}-note-signin`}>Note</Link>;
  const save = async () => { try { await put(`/me/notes/${player.id}`, { text }); setMsg("Saved"); } catch (x) { setMsg(x.message || "Could not save"); } };
  return open ? (
    <div className="k-fs-note" data-testid={`${testid}-note`}>
      <label className="sr-only" htmlFor={`${testid}-note-text`}>Your note on {player.name}</label>
      <textarea id={`${testid}-note-text`} rows={3} maxLength={2000} value={text} onChange={(e) => { setText(e.target.value); setMsg(""); }} placeholder={`Your note on ${player.name}`} data-testid={`${testid}-note-text`} />
      <span><button type="button" className="btn btn--primary btn--sm" onClick={save} data-testid={`${testid}-note-save`}>Save note</button>{msg && <small className="k-faint" role="status">{msg}</small>}</span>
    </div>
  ) : <button type="button" className="btn btn--ghost" onClick={() => setOpen(true)} data-testid={`${testid}-note-open`}>Note</button>;
}

const STAT_WORD = { shots: "shots", sot: "on-target", tackles: "tackles", corners: "corners", yellow_cards: "card", match_yellow_cards: "match card" };

export function ForecastSheet({ open, onClose, f, fx, testid = "ui-fsheet" }) {
  const d = useSheetData(open, f);
  const tier = d.record?.ready && f.tier ? d.record.tiers?.[f.tier] : null;
  const share = async () => {
    const url = f.match_id ? `${window.location.origin}/match/${f.match_id}` : window.location.href;
    const text = `${f.player?.name || fx.team?.name || ""}: ${f.market}, ${pct(f.p)}`;
    try { if (navigator.share) await navigator.share({ title: text, text, url }); else await navigator.clipboard.writeText(`${text} ${url}`); } catch { /* closed */ }
  };
  const lines = [{ fkey: f.fkey, market: f.market, p: f.p, tier: f.tier }, ...(f.more_lines || [])];
  const title = `${f.player?.name || fx.team?.name || "Forecast"} · ${f.market}`;
  return (
    <BottomSheet open={open} onClose={onClose} title={title} testid={testid}
      footer={<>{f.fkey && <SaveButton fkey={f.fkey} />}{f.scope === "player" && f.player?.id && <NoteBox player={f.player} testid={testid} />}<button type="button" className="btn btn--secondary" onClick={share} data-testid={`${testid}-share`}>Share</button></>}>
      <div className="k-fs-head" style={{ "--tone": f.tier ? `var(--tier-${f.tier.toLowerCase()})` : "var(--text3)" }}>
        {f.player ? <PlayerAvatar player={f.player} size={52} /> : <Crest team={fx.team} size={52} />}
        <span className="k-fc-who"><small>{[fx.text, f.kickoff ? timeOf(f.kickoff) : null].filter(Boolean).join(" · ")}</small></span>
        <b className="k-fc-p">{pct(f.p)}</b>
      </div>
      {(f.reasons || []).length > 0 && <section><h3 className="k-sec">Why</h3><ul className="k-fs-why">{f.reasons.slice(0, 3).map((r) => <li key={r}>{r}</li>)}</ul></section>}
      {f.scope === "player" && (
        <div className="k-fs-tiles">
          {f.p_play != null && <div className="k-fs-tile"><small>Chance he plays</small><b data-testid={`${testid}-pplay`}>{pct(f.p_play)}</b></div>}
          <div className="k-fs-tile"><small>Lineup</small><b className={f.lineup_confirmed ? "k-up" : "k-watch"}>{f.lineup_confirmed ? "Confirmed" : "Not out yet"}</b></div>
        </div>
      )}
      {d.hits?.length > 0 && <section><h3 className="k-sec">Last {d.hits.length} games · {f.market}</h3><HitStrip hits={d.hits} label={f.market} testid={`${testid}-hits`} /></section>}
      {f.usual_p != null && <p className="k-faint" data-testid={`${testid}-usual`}>Usual: {pct(f.usual_p)} of the last {f.usual_n} games got past this line.</p>}
      {lines.length > 1 && <section><h3 className="k-sec">All lines</h3><ul className="k-fc-lines">{lines.map((x) => <li key={x.fkey} style={{ "--tone": x.tier ? `var(--tier-${x.tier.toLowerCase()})` : "var(--text3)" }}><span>{x.market}</span><b>{pct(x.p)}</b></li>)}</ul></section>}
      {tier && tier.n > 0 && <p className="k-fs-record" data-testid={`${testid}-record`}>Our record on {f.tier} {f.scope} {STAT_WORD[f.stat] || f.stat} forecasts: <b>{tier.n >= 100 ? `${Math.round(tier.actual * 100)} of 100` : `${Math.round(tier.actual * tier.n)} of ${tier.n}`}</b> came true{tier.n < 100 ? " so far" : ""}. <Link to={`/track-record?stat=${f.stat}`}>Track record</Link></p>}
      <p className="k-faint k-small">{DISCLAIMER} <Link to="/learn/forecast-card" aria-label="How to read a forecast card" data-testid={`${testid}-learn`}>How to read this card (?)</Link></p>
    </BottomSheet>
  );
}
