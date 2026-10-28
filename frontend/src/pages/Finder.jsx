// Forecast Finder as a sentence builder (docs/24 §5). Every underlined part opens a small picker; the query
// stays in the URL. Results update live for unlimited plans; on capped plans "Update results" spends a search.
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { get, put } from "../lib/api";
import { favFirst, useFavLeagues } from "../lib/prefs";
import { useApi } from "../lib/useApi";
import { useAuth } from "../lib/auth";
import { pct } from "../lib/copy";
import { Crest, PlayerAvatar } from "../components/Media";
import Icon from "../components/Icon";
import { MATCH_STATS, STATS, TEAM_STATS, kickoff, useTitle } from "../components/Football";
import { ChipsRow, EmptyState, ErrorState, ForecastCard, HitStrip, ProLock, RangeSlider, Segmented, Skeleton } from "../components/ui";

const DEF = { mode: "form", stat: "shots", n: "2", scope: "player", last_n: "10", min: "6", venue: "", positions: "", leagues: "" };
const POS = ["GK", "DEF", "MID", "FWD"];
const PRESETS = "finder-presets";

function Part({ id, label, open, setOpen, children }) {
  const ref = useRef(null);
  useEffect(() => {
    if (open !== id) return undefined;
    const out = (e) => { if (ref.current && !ref.current.contains(e.target) && !e.target.closest?.(".k-scrim")) setOpen(null); };
    const esc = (e) => { if (e.key === "Escape") setOpen(null); };
    document.addEventListener("mousedown", out); document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", out); document.removeEventListener("keydown", esc); };
  }, [open, id, setOpen]);
  return (
    <span className="fs-part" ref={ref}>
      <button type="button" className="fs-word" aria-expanded={open === id} onClick={() => setOpen(open === id ? null : id)} data-testid={`finder-part-${id}`}>{label}</button>
      {open === id && <span className="fs-pop" role="dialog" aria-label={`Change ${id}`} data-testid={`finder-pop-${id}`}>{children}</span>}
    </span>
  );
}

function Row({ r, f }) {
  const nx = r.next_match;
  return (
    <li className="fs-row" data-testid={`finder-row-${r.id}`}>
      {r.player ? <PlayerAvatar player={r.player} size={44} /> : <Crest team={r.team} size={40} />}
      <span className="fs-who"><Link to={r.player ? `/player/${r.player.id}` : `/team/${r.team?.id}`}><b>{(r.player || r.team)?.name}</b></Link>
        <small>{[r.player && r.team ? r.team.name : null, nx ? `next v ${(nx.home?.id === r.team?.id ? nx.away : nx.home)?.name}, ${kickoff(nx.kickoff)}` : null].filter(Boolean).join(" · ")}</small></span>
      {f.mode === "run" ? <b data-testid={`finder-run-${r.id}`}>{r.run} in a row</b> : r.hits ? <HitStrip hits={[...r.hits].reverse()} label={`${f.n}+ ${f.stat}`} testid={`finder-strip-${r.id}`} /> : <b>{`${r.reached}/${r.games}`}</b>}
      {r.forecast ? <b className="fs-next" data-testid={`finder-next-${r.id}`}>Next {pct(r.forecast.p)}</b> : <span />}
    </li>
  );
}

function Meter({ used, cap, visitor }) {
  const left = Math.max(0, cap - (used || 0));
  return (
    <span className="fs-meter" data-testid="finder-usage">
      {cap <= 10 && <span className="fs-meter-dots" aria-hidden="true">{[...Array(cap)].map((_, i) => <i key={i} className={i < left ? "on" : ""} />)}</span>}
      <span data-testid="finder-usage-left">{left} of {cap} {visitor ? "free searches" : "searches"} left today</span>
    </span>
  );
}

function useReset() {
  const [now, setNow] = useState(Date.now());
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 60000); return () => clearInterval(t); }, []);
  const r = new Date(now); r.setUTCHours(24, 0, 0, 0);
  const mins = Math.max(1, Math.round((r - now) / 60000));
  return { time: r.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }), left: mins >= 60 ? `${Math.floor(mins / 60)} h ${mins % 60} min` : `${mins} min` };
}

function Reminder() {
  const r = useReset();
  return <p className="fs-reset" data-testid="finder-reset-time"><Icon name="clock" size={14} />Your searches come back at {r.time}, in about {r.left}.</p>;
}

function Wall({ visitor, cap, freeCap, next }) {
  return (
    <div className="fs-wall card" role="status" data-testid="finder-wall">
      <h2 className="h3">{visitor ? `That's today's ${cap} free searches` : `You've used today's ${cap} searches`}</h2>
      {visitor ? (
        <>
          <p className="k-faint">A free account gives you {freeCap} searches a day, plus follows and saved forecasts. It takes a minute.</p>
          <div className="btn-row"><Link to={`/sign-up?next=${encodeURIComponent(next)}`} className="btn btn--primary" data-testid="finder-wall-signup">Create a free account</Link>
            <Link to={`/sign-in?next=${encodeURIComponent(next)}`} className="btn btn--secondary" data-testid="finder-wall-signin">Sign in</Link></div>
        </>
      ) : <p className="k-faint"><ProLock label="Unlimited with Pro" testid="finder-wall-pro" /></p>}
      <Reminder />
    </div>
  );
}

export default function Finder() {
  const { entitlements, me, refresh } = useAuth();
  const [sp, setSp] = useSearchParams();
  const f = { ...DEF, ...Object.fromEntries(sp.entries()) };
  const [open, setOpen] = useState(null);
  const [res, setRes] = useState({ rows: null, err: null, busy: false });
  const [anonUsed, setAnonUsed] = useState(null);
  const [wall, setWall] = useState(false);
  const [presets, setPresets] = useState(() => { try { return JSON.parse(localStorage.getItem(PRESETS)) || []; } catch { return []; } });
  const fav = useFavLeagues();
  useEffect(() => {
    if (!me?.user) return;
    get("/me/presets").then((r) => {
      const local = JSON.parse(localStorage.getItem(PRESETS) || "[]");
      const merged = [...r.items, ...local.filter((p) => !r.items.some((x) => x.name === p.name))].slice(0, 8);
      setPresets(merged);
      if (local.length) put("/me/presets", { items: merged }).then(() => localStorage.removeItem(PRESETS)).catch(() => {});
    }).catch(() => {});
  }, [me?.user]);
  const lg = useApi("/leagues");
  const leagues = useMemo(() => favFirst((lg.data?.countries || []).flatMap((c) => c.leagues), fav, (l) => l.id), [lg.data, fav]);
  const max = entitlements?.finder_leagues ?? 1;
  const picked = f.leagues ? f.leagues.split(",") : [];
  const cap = me?.user ? entitlements?.finder_searches_per_day : me?.limits?.anonymous_finder_searches_per_day;
  const unlimited = cap != null && cap < 0;
  const visitor = !me?.user;
  const used = visitor ? (anonUsed ?? me?.usage?.finder_today) : me?.usage?.finder_today;
  const out = wall || (cap != null && cap >= 0 && used != null && used >= cap);
  const pool = (f.scope === "team" ? [...TEAM_STATS, ...(f.mode === "likelihood" ? MATCH_STATS : [])] : STATS.filter((s) => s.id !== "minutes")).filter((s) => f.mode !== "likelihood" || s.core);
  const stat = pool.find((s) => s.id === f.stat) || pool[0];
  const set = (patch) => {
    const n = { ...f, ...patch };
    if (!(n.scope === "team" ? [...TEAM_STATS, ...MATCH_STATS] : STATS).some((s) => s.id === n.stat)) n.stat = "shots";
    setRes({ rows: null, err: null, busy: false });
    setSp(Object.fromEntries(Object.entries(n).filter(([k, v]) => v !== "" && DEF[k] !== v)), { replace: true });
  };
  const run = async () => {
    if (!picked.length || out) return;
    setRes((r) => ({ ...r, err: null, busy: true }));
    try {
      const rows = await get("/finder", { mode: f.mode, stat: stat.id, threshold: Number(f.n), scope: f.scope, last_n: f.last_n, leagues: f.leagues,
        venue: f.venue || undefined, positions: f.scope === "player" ? f.positions : "", min_reached: f.mode === "form" ? Number(f.min) / Number(f.last_n) : undefined }, { quiet: true });
      setRes({ rows, err: null, busy: false });
      if (visitor) setAnonUsed((used || 0) + 1);
    } catch (x) {
      if (x.code === "SIGN_IN_REQUIRED" || x.status === 402) { setWall(true); if (visitor) setAnonUsed(cap); setRes((r) => ({ ...r, busy: false })); }
      else setRes({ rows: null, err: x, busy: false });
    }
    if (me?.user) refresh();
  };
  const key = JSON.stringify(f);
  useEffect(() => {
    if (!unlimited || !picked.length) return undefined;
    const t = setTimeout(run, 500);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, unlimited]);
  const savePreset = () => {
    const name = window.prompt("Name this search", `${f.n}+ ${stat.label}`);
    if (!name) return;
    const next = [{ name: name.slice(0, 40), q: sp.toString() }, ...presets.filter((p) => p.name !== name)].slice(0, 8);
    setPresets(next);
    if (me?.user) put("/me/presets", { items: next }).catch(() => {}); else localStorage.setItem(PRESETS, JSON.stringify(next));
  };
  const lgLabel = picked.length ? picked.map((id) => leagues.find((l) => l.id === id)?.name || "League").join(", ") : "pick a league";
  useTitle("Forecast Finder");
  return (
    <section className="fs" data-testid="finder-page">
      <h1>Forecast Finder</h1>
      <Segmented label="Mode" value={f.mode} onChange={(v) => set({ mode: v })} testid="finder-mode" options={[{ id: "form", label: "How often" }, { id: "run", label: "Streak" }, { id: "likelihood", label: "Our forecast" }]} />
      {presets.length > 0 && <ChipsRow label="Saved searches" testid="finder-presets" options={presets.map((p, i) => ({ id: String(i), label: p.name, onClick: () => { setRes({ rows: null, err: null, busy: false }); setSp(new URLSearchParams(p.q), { replace: true }); } }))} />}
      <p className="fs-sentence card" data-testid="finder-sentence">
        <Part id="scope" label={f.scope === "team" ? "Teams" : "Players"} open={open} setOpen={setOpen}>
          <Segmented label="Who" value={f.scope} onChange={(v) => set({ scope: v })} options={[{ id: "player", label: "Players" }, { id: "team", label: "Teams" }]} testid="finder-scope" /></Part>{" with "}
        <Part id="n" label={`${f.n}+`} open={open} setOpen={setOpen}>
          <span className="fs-step"><button type="button" className="k-icon-btn" onClick={() => set({ n: String(Math.max(1, Number(f.n) - 1)) })} aria-label="Fewer" data-testid="finder-n-down">−</button><b>{f.n}+</b>
            <button type="button" className="k-icon-btn" onClick={() => set({ n: String(Math.min(6, Number(f.n) + 1)) })} aria-label="More" data-testid="finder-n-up">+</button></span></Part>{" "}
        <Part id="stat" label={stat.label.toLowerCase()} open={open} setOpen={setOpen}>
          <span className="fs-list">{pool.map((s) => <button key={s.id} type="button" className={`k-chip${s.id === stat.id ? " on" : ""}`} onClick={() => { set({ stat: s.id }); setOpen(null); }} data-testid={`finder-stat-${s.id}`}>{s.label}</button>)}</span></Part>
        {f.mode !== "likelihood" && <>{" in "}<Part id="window" label={f.mode === "run" ? `a row, last ${f.last_n}` : `${f.min} of the last ${f.last_n}`} open={open} setOpen={setOpen}>
          <span className="fs-sliders"><small>Games</small><RangeSlider min={5} max={20} value={Number(f.last_n)} onChange={(v) => set({ last_n: String(v), min: String(Math.min(Number(f.min), v)) })} label="Games window" format={(v) => `${v} games`} testid="finder-window" />
            {f.mode === "form" && <><small>Reached in at least</small><RangeSlider min={1} max={Number(f.last_n)} value={Number(f.min)} onChange={(v) => set({ min: String(v) })} label="How often" format={(v) => `${v} of ${f.last_n}`} testid="finder-min" /></>}</span></Part>{" games"}</>}
        {f.mode !== "likelihood" && <>{", "}<Part id="venue" label={f.venue ? `at ${f.venue}` : "home or away"} open={open} setOpen={setOpen}>
          <Segmented label="Venue" value={f.venue} onChange={(v) => set({ venue: v })} options={[{ id: "", label: "All" }, { id: "home", label: "Home" }, { id: "away", label: "Away" }]} testid="finder-venue" /></Part></>}
        {f.scope === "player" && <>{", "}<Part id="pos" label={f.positions ? f.positions.split(",").join("/") : "any position"} open={open} setOpen={setOpen}>
          <ChipsRow multi label="Position" value={f.positions ? f.positions.split(",") : []} onChange={(v) => set({ positions: v.join(",") })} options={POS.map((p) => ({ id: p, label: p }))} testid="finder-pos" /></Part></>}
        {" in "}<Part id="leagues" label={lgLabel} open={open} setOpen={setOpen}>
          <span className="fs-list">{max >= 0 && <small className="k-faint">Up to {max} on your plan <ProLock label="More with Pro" testid="finder-leagues-pro" /></small>}{leagues.map((l) => {
            const on = picked.includes(l.id);
            return <button key={l.id} type="button" className={`k-chip${on ? " on" : ""}`} aria-pressed={on} onClick={() => set({ leagues: (on ? picked.filter((x) => x !== l.id) : max >= 0 && picked.length >= max ? [...picked.slice(1), l.id] : [...picked, l.id]).join(",") })} data-testid={`finder-league-${l.id}`}>{l.name}</button>;
          })}</span></Part>
      </p>
      <div className="fs-actions">
        {!unlimited && <button type="button" className="btn btn--primary" disabled={res.busy || !picked.length || out} onClick={run} data-testid="finder-run">{res.busy ? "Searching…" : !picked.length ? "Pick a league first" : out ? "No searches left today" : "Update results"}</button>}
        {res.rows && <button type="button" className="btn btn--secondary" onClick={savePreset} data-testid="finder-save-preset">Save this search</button>}
        <button type="button" className="k-link" onClick={() => { setSp({}); setRes({ rows: null, err: null, busy: false }); }} data-testid="finder-reset">Reset</button>
        {cap != null && cap >= 0 && <Meter used={used} cap={cap} visitor={visitor} />}
      </div>
      {out && <Wall visitor={visitor} cap={cap} freeCap={entitlements?.finder_searches_per_day} next={`/finder${sp.toString() ? `?${sp}` : ""}`} />}
      {res.busy && !res.rows ? <Skeleton shape="row" count={5} testid="finder-loading" />
        : res.err ? <ErrorState message={res.err.message || "The search did not work."} onRetry={run} testid="finder-error" />
        : !res.rows ? <EmptyState icon="search" title={picked.length ? "Ready when you are" : "Pick a league"} testid="finder-idle">Tap any underlined word to change it.</EmptyState>
        : !res.rows.length ? <EmptyState icon="search" title="Nothing meets that line" testid="finder-empty">Try a lower line, a longer window or another league.</EmptyState>
        : f.mode === "likelihood" ? <div className="fgrid" data-testid="finder-results">{res.rows.map((r) => <ForecastCard key={r.id} f={r} testid={`finder-fc-${r.id}`} />)}</div>
        : <ul className="fs-results card" data-testid="finder-results">{res.rows.map((r) => <Row key={r.id} r={r} f={f} />)}</ul>}
    </section>
  );
}
