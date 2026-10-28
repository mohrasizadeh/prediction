// Forecast detail sheet (docs/24): every line, the top 3 reasons, chance he plays, lineup status, last 10 games,
// our record on this tier (only once the track record is ready), Save and Share. Reads our own API only.
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { get } from "../../lib/api";
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
    if (f.player?.id && f.scope === "player") {
      get(`/players/${f.player.id}/history`, { last: 10 })
        .then((r) => { if (!stop) setD((x) => ({ ...x, hits: (r.games || []).filter((g) => g[f.stat] != null).map((g) => g[f.stat] > f.thr).reverse() })); })
        .catch(() => {});
    }
    get("/track-record").then((r) => { if (!stop) setD((x) => ({ ...x, record: r })); }).catch(() => {});
    return () => { stop = true; };
  }, [open, f]);
  return d;
}

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
      footer={<>{f.fkey && <SaveButton fkey={f.fkey} />}<button type="button" className="btn btn--secondary" onClick={share} data-testid={`${testid}-share`}>Share</button></>}>
      <div className="k-fs-head" style={{ "--tone": f.tier ? `var(--tier-${f.tier.toLowerCase()})` : "var(--text3)" }}>
        {f.player ? <PlayerAvatar player={f.player} size={52} /> : <Crest team={fx.team} size={52} />}
        <span className="k-fc-who"><small>{fx.text}{f.kickoff ? ` · ${timeOf(f.kickoff)}` : ""}</small></span>
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
      {lines.length > 1 && <section><h3 className="k-sec">All lines</h3><ul className="k-fc-lines">{lines.map((x) => <li key={x.fkey} style={{ "--tone": x.tier ? `var(--tier-${x.tier.toLowerCase()})` : "var(--text3)" }}><span>{x.market}</span><b>{pct(x.p)}</b></li>)}</ul></section>}
      {tier && <p className="k-fs-record" data-testid={`${testid}-record`}>Our record on {f.tier} forecasts: <b>{Math.round(tier.actual * 100)} of 100</b> came true. <Link to="/track-record">Track record</Link></p>}
      <p className="k-faint k-small">{DISCLAIMER}</p>
    </BottomSheet>
  );
}
