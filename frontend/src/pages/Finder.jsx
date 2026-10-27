// Screen 4, Forecast Finder (docs/01 §5): pick league(s), stat, line, mode Likelihood / Form / Run; filters live in the URL.
import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { get } from "../lib/api";
import { useApi } from "../lib/useApi";
import { useAuth } from "../lib/auth";
import { pct } from "../lib/copy";
import { Crest, PlayerAvatar } from "../components/Media";
import { Empty, ErrorBox, Loading } from "../components/States";
import { FormError } from "../components/Ui";
import { ForecastCard, STATS, Seg, Select, TEAM_STATS, kickoff, useTitle } from "../components/Football";

const DEF = { mode: "likelihood", stat: "shots", n: "2", scope: "player", last_n: "10", venue: "", started: "", positions: "", leagues: "" };
const POS = ["GK", "DEF", "MID", "FWD"];

function Result({ r, mode, f }) {
  const who = r.player || r.team;
  const nx = r.next_match;
  return (
    <article className="fcard" data-testid={`finder-row-${r.id}`}>
      <header className="fcard-head">
        {r.player ? <PlayerAvatar player={r.player} size={40} /> : <Crest team={r.team} size={40} />}
        <div className="fcard-who">{r.player ? <Link to={`/player/${r.player.id}`}><b>{who?.name}</b></Link> : <Link to={`/team/${r.team?.id}`}><b>{who?.name}</b></Link>}
          <span className="muted small">{r.player ? `${r.team?.name || ""} · ` : ""}{nx ? `next ${nx.home?.name} v ${nx.away?.name}, ${kickoff(nx.kickoff)}` : ""}</span></div>
      </header>
      <p className="fcard-market">{mode === "form" ? `${f.n} or more in ${r.reached} of ${r.games} games` : `${r.run} games in a row with ${f.n} or more`}</p>
      {r.forecast && <p className="muted small">Next-match likelihood {pct(r.forecast.p)}</p>}
    </article>
  );
}

export default function Finder() {
  const { entitlements, me, refresh } = useAuth();
  const [sp, setSp] = useSearchParams();
  const f = { ...DEF, ...Object.fromEntries(sp.entries()) };
  const set = (k) => (v) => {
    const n = { ...f, [k]: v };
    if ((k === "scope" || k === "mode") && !(n.scope === "team" ? TEAM_STATS : STATS).some((s) => s.id === n.stat && (n.mode !== "likelihood" || s.core))) n.stat = "shots";
    setRes({ rows: null, err: null, busy: false });
    setSp(Object.fromEntries(Object.entries(n).filter(([kk, vv]) => vv !== "" && DEF[kk] !== vv)));
  };
  const lg = useApi("/leagues");
  const leagues = useMemo(() => (lg.data?.countries || []).flatMap((c) => c.leagues), [lg.data]);
  const [res, setRes] = useState({ rows: null, err: null, busy: false });
  const max = entitlements?.finder_leagues ?? 1;
  const picked = f.leagues ? f.leagues.split(",") : [];
  const toggleLeague = (id) => {
    const on = picked.includes(id);
    const next = on ? picked.filter((x) => x !== id) : max >= 0 && picked.length >= max ? [...picked.slice(1), id] : [...picked, id];
    set("leagues")(next.join(","));
  };
  const togglePos = (p) => { const cur = f.positions ? f.positions.split(",") : []; set("positions")((cur.includes(p) ? cur.filter((x) => x !== p) : [...cur, p]).join(",")); };
  useTitle("Forecast Finder");
  const run = async (e) => {
    e.preventDefault();
    setRes({ rows: null, err: null, busy: true });
    try {
      const rows = await get("/finder", { mode: f.mode, stat: f.stat, threshold: Number(f.n), scope: f.scope, last_n: f.last_n, leagues: f.leagues,
        venue: f.venue || undefined, started: f.started || undefined, positions: f.scope === "player" ? f.positions : "", min_reached: f.mode === "form" ? 0.5 : undefined });
      setRes({ rows, err: null, busy: false });
      if (me?.user) refresh();
    } catch (x) { setRes({ rows: null, err: x, busy: false }); if (me?.user) refresh(); }
  };
  const cap = me?.user ? entitlements?.finder_searches_per_day : me?.limits?.anonymous_finder_searches_per_day;
  const used = me?.usage?.finder_today;
  return (
    <section data-testid="finder-page">
      <h1>Forecast Finder</h1>
      <p className="muted lead">Find the players and teams that meet your line.</p>
      {cap != null && cap >= 0 && (
        <p className={"finder-usage" + (used != null && used >= cap ? " is-out" : "")} data-testid="finder-usage">
          {used != null ? `${Math.min(used, cap)} of ${cap} searches today` : `Up to ${cap} searches a day without an account`}
          {used != null && used >= cap ? <> · <Link to="/pricing" data-testid="finder-usage-upgrade">Unlimited with Pro</Link></> : !me?.user ? <> · <Link to="/sign-up">Sign up for more</Link></> : null}
        </p>
      )}
      <form className="card finder" onSubmit={run} data-testid="finder-form">
        <div className="finder-block"><span className="flabel">Leagues {max >= 0 ? `(up to ${max})` : ""}</span>
          {lg.loading && !lg.data ? <Loading rows={1} /> : lg.error ? <ErrorBox error={lg.error} onRetry={lg.reload} /> : (
            <div className="chips">{leagues.map((l) => <button type="button" key={l.id} className={"chip chip--sm" + (picked.includes(l.id) ? " chip-on" : "")} aria-pressed={picked.includes(l.id)} onClick={() => toggleLeague(l.id)} data-testid={`finder-league-${l.id}`}>{l.name}</button>)}</div>)}
        </div>
        <div className="filters">
          <Seg label="Mode" value={f.mode} onChange={set("mode")} options={[{ id: "likelihood", label: "Likelihood" }, { id: "form", label: "Form" }, { id: "run", label: "Run" }]} testid="finder-mode" />
          <Seg label="Scope" value={f.scope} onChange={set("scope")} options={[{ id: "player", label: "Players" }, { id: "team", label: "Teams" }]} testid="finder-scope" />
        </div>
        <div className="filters">
          <Select label="Stat" value={f.stat} onChange={set("stat")} options={(f.scope === "team" ? TEAM_STATS : STATS.filter((s) => s.id !== "minutes")).filter((s) => f.mode !== "likelihood" || s.core)} testid="finder-stat" />
          <Select label="Line" value={f.n} onChange={set("n")} options={[1, 2, 3, 4, 5].map((n) => ({ id: String(n), label: `${n} or more` }))} testid="finder-n" />
          {f.mode !== "likelihood" && <Select label="Window" value={f.last_n} onChange={set("last_n")} options={["5", "10", "20"].map((n) => ({ id: n, label: `Last ${n}` }))} testid="finder-window" />}
          {f.mode !== "likelihood" && <Seg label="Venue" value={f.venue} onChange={set("venue")} options={[{ id: "", label: "All" }, { id: "home", label: "Home" }, { id: "away", label: "Away" }]} testid="finder-venue" />}
        </div>
        {f.scope === "player" && <div className="chips" aria-label="Positions">{POS.map((p) => <button type="button" key={p} className={"chip chip--sm" + (f.positions.split(",").includes(p) ? " chip-on" : "")} onClick={() => togglePos(p)} data-testid={`finder-pos-${p}`}>{p}</button>)}
          {f.mode !== "likelihood" && <label className="check-inline"><input type="checkbox" checked={!!f.started} onChange={(e) => set("started")(e.target.checked ? "true" : "")} data-testid="finder-started" /> Started only</label>}</div>}
        <div className="btn-row"><button className="btn btn--primary" disabled={res.busy || !picked.length} data-testid="finder-run">{res.busy ? "Searching…" : picked.length ? "Search" : "Pick a league first"}</button>
          <button type="button" className="btn btn--ghost" onClick={() => { setSp({}); setRes({ rows: null, err: null, busy: false }); }} data-testid="finder-reset">Reset</button></div>
      </form>
      <FormError error={res.err} />
      {res.busy && <Loading rows={3} />}
      {res.rows && (!res.rows.length ? <Empty icon="search">Nothing meets that line. Try a lower line or another league.</Empty> : (
        <div className="fgrid" data-testid="finder-results">{res.rows.map((r) => (f.mode === "likelihood" ? <ForecastCard key={r.id} f={r} showMatch /> : <Result key={r.id} r={r} mode={f.mode} f={f} />))}</div>
      ))}
    </section>
  );
}
