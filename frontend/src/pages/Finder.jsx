// Forecast Finder as a sentence builder (docs/24 §5). Every underlined part opens a small picker; the query
// stays in the URL. Results update live for unlimited plans; on capped plans "Update results" spends a search.
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { get, put } from "../lib/api";
import { favFirst, useFavLeagues } from "../lib/prefs";
import { useApi } from "../lib/useApi";
import { useAuth } from "../lib/auth";
import { useCombo } from "../lib/combo";
import { pct } from "../lib/copy";
import { Crest, PlayerAvatar } from "../components/Media";
import Icon from "../components/Icon";
import { MATCH_STATS, STATS, TEAM_STATS, kickoff, useTitle } from "../components/Football";
import { ChipsRow, DateScroller, EmptyState, ErrorState, ForecastCard, GameStrip, HitStrip, ProLock, RangeSlider, Segmented, Skeleton, isoDay } from "../components/ui";
import { FINDER_STARTS, startChips } from "../lib/finderStarts";

const DEF = { mode: "form", stat: "shots", n: "2", scope: "player", last_n: "10", min: "6", venue: "", positions: "", leagues: "", day: "", gt: "" };
// How much of the match counts. `min_minutes` and `started` have been parameters of this search
// since it was written and no browser could ever send either: they were not merely missing from
// the sentence, the request builder never carried them. They are one question, not two -- "did he
// play enough for this to mean anything?" -- so they are one control.
// These labels finish the window phrase -- "6 of the last 10 GAMES OF 60+ MINUTES" -- because the
// filter changes which games are counted, not just which players qualify. His last ten games of
// 60+ minutes reach further back than his last ten games, so a stricter setting can surface
// players the plain search missed. Said plainly, that is what a reader wants; left ambiguous it
// looks like a bug.
const GAMETIME = [
  { id: "", label: "games", hint: "Every appearance counts, however short." },
  { id: "45", label: "games of 45+ minutes", hint: "Drops late cameos." },
  { id: "60", label: "games of 60+ minutes", hint: "Roughly a full shift." },
  { id: "75", label: "games of 75+ minutes", hint: "Nearly the whole match." },
  { id: "started", label: "games he started", hint: "Named in the eleven, however long he lasted." },
];
const POS = ["GK", "DEF", "MID", "FWD"];
const PRESETS = "finder-presets";

function dayLabel(day) {
  if (!day) return "today";
  const d = new Date(`${day}T12:00:00`), t = new Date(); t.setDate(t.getDate() + 1);
  return day === isoDay(t) ? "tomorrow" : `on ${d.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" })}`;
}

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

function RowAdd({ f }) {
  const { has, toggle } = useCombo();
  const on = has(f.fkey);
  const name = f.player?.name || f.team?.name || "";
  return (
    <button type="button" className={"cb-add cb-add--row" + (on ? " on" : "")} aria-pressed={on} aria-label={`${on ? "Remove" : "Add"} ${name} ${f.market} ${on ? "from" : "to"} your combo`} onClick={() => toggle(f)} data-testid={`finder-add-${f.fkey}`}>
      <Icon name={on ? "check" : "plus"} size={20} />
    </button>
  );
}

function Row({ r, f, canLine, statLabel }) {
  const nx = r.next_match;
  return (
    <li className="fs-row" data-testid={`finder-row-${r.id}`}>
      {/* One size for both, as the forecast card's own Who does. A 44px portrait on one row and a
          40px crest on the next sized this column differently per row, so the name, the strip and
          the percentage after it all started at a different x depending on whether the row was
          about a person or a club. */}
      {r.player ? <PlayerAvatar player={r.player} size={44} /> : <Crest team={r.team} size={44} />}
      <span className="fs-who"><Link to={r.player ? `/player/${r.player.id}` : `/team/${r.team?.id}`}><b>{(r.player || r.team)?.name}</b></Link>
        <small>{[r.player && r.team ? r.team.name : null, nx ? `next v ${(nx.home?.id === r.team?.id ? nx.away : nx.home)?.name}, ${kickoff(nx.kickoff)}` : null].filter(Boolean).join(" · ")}</small></span>
      {/* Ten filled-or-empty squares could not tell a quiet game from a busy one, or say who it
          was against. These are the games themselves -- minutes above, the figure, the opponent's
          crest below -- which is the same component the player page and the sheet already draw. */}
      {f.mode === "run" ? <b data-testid={`finder-run-${r.id}`}>{r.run} in a row</b>
        : r.gs?.length ? <GameStrip games={r.gs} stat={f.stat} line={Number(f.n)} label={f.stat} note={false} count={false} testid={`finder-strip-${r.id}`} />
        : r.hits ? <HitStrip hits={[...r.hits].reverse()} label={`${f.n}+ ${f.stat}`} testid={`finder-strip-${r.id}`} /> : <b>{`${r.reached}/${r.games}`}</b>}
      {/* This was `<span />`. A blank where every other row carries a percentage reads as the row
          being broken, or the player being missing -- which is exactly how it was reported. It is
          neither: either we hold no forecast for this fixture, or the line itself is not a rung on
          this market's ladder. Say which. We never fall to a neighbouring rung and print its
          number here: that would attach one line's evidence to another line's percentage. */}
      {r.forecast ? <span className="fs-next" style={{ "--tone": r.forecast.tier ? `var(--tier-${r.forecast.tier.toLowerCase()})` : "var(--brand)" }} data-testid={`finder-next-${r.id}`}>
            <b>{r.forecast.p_display || pct(r.forecast.p)}</b><small>Next game</small></span>
        : <small className="fs-nonext muted" data-testid={`finder-nonext-${r.id}`}>
            {canLine && !canLine.includes(Number(f.n)) ? `We do not forecast ${f.n}+ ${statLabel}` : "No forecast for this match"}
          </small>}
      {/* The add control's slot is drawn on every row, empty where the line cannot be added.
          Rendered only when present it was a fifth grid child on some rows and a fourth on
          others, so those rows laid out on a different set of tracks and nothing lined up down
          the list. An empty cell is how a column keeps its place. */}
      {r.forecast?.fkey && r.forecast.addable !== false
        ? <RowAdd f={{ ...r.forecast, player: r.player || r.forecast.player, team: r.team || r.forecast.team }} />
        : <span className="fs-addslot" aria-hidden="true" />}
      {r.forecast?.from_ladder && <small className="muted fs-ladder" data-testid={`finder-ladder-${r.id}`}>Open the match to add this line.</small>}
    </li>
  );
}

// The screen a reader lands on. It used to be one line of instruction; it is now the eight
// questions this tool can answer, each with the search it runs printed underneath it.
function Starts({ onPick, statOf }) {
  return (
    <section className="fs-starts" data-testid="finder-starts">
      <h2 className="h3">Start with a question</h2>
      <p className="muted small">Eight searches worth running. Tap one to load it, then change any underlined word.</p>
      <ul className="fs-starts-grid">
        {FINDER_STARTS.map((t) => (
          <li key={t.id}>
            <button type="button" className="fs-start" onClick={() => onPick(t)} data-testid={`finder-start-${t.id}`}>
              <b>{t.name}</b>
              <span className="fs-start-why">{t.why}</span>
              <span className="fs-start-chips">{startChips(t.q, statOf(t.q)).map((c) => <i key={c}>{c}</i>)}</span>
            </button>
          </li>
        ))}
      </ul>
    </section>
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
    if (!me?.user?.id) return;
    get("/me/presets").then((r) => {
      const local = JSON.parse(localStorage.getItem(PRESETS) || "[]");
      const merged = [...r.items, ...local.filter((p) => !r.items.some((x) => x.name === p.name))].slice(0, 8);
      setPresets(merged);
      if (local.length) put("/me/presets", { items: merged }).then(() => localStorage.removeItem(PRESETS)).catch(() => {});
    }).catch(() => {});
  }, [me?.user?.id]);
  const lg = useApi("/leagues");
  const leagues = useMemo(() => favFirst((lg.data?.countries || []).flatMap((c) => c.leagues), fav, (l) => l.id), [lg.data, fav]);
  const max = entitlements?.finder_leagues ?? 1;
  const picked = f.leagues ? f.leagues.split(",") : [];
  const cap = me?.user ? entitlements?.finder_searches_per_day : me?.limits?.anonymous_finder_searches_per_day;
  const unlimited = cap != null && cap < 0;
  const visitor = !me?.user;
  const used = visitor ? (anonUsed ?? me?.usage?.finder_today) : me?.usage?.finder_today;
  const out = wall || (cap != null && cap >= 0 && used != null && used >= cap);
  // "Our forecast" used to offer whatever carried a `core` flag in the browser -- Goals, Assists
  // and Minutes for a player, Tackles for a club -- none of which the engine makes a market for.
  // Picking one returned "Nothing meets that line", which reads as "nobody qualifies" rather than
  // "we do not forecast that". The list now comes from the forecasts we actually hold.
  const fm = useApi("/forecast-markets");
  const have = fm.data?.markets?.[f.scope] || null;
  // Which lines the forecast can actually answer for this stat. Not every ladder starts at 1:
  // tackles starts at "2+", so "1+ tackles" is a question the engine has no rung for, for anyone.
  const fmLines = fm.data?.lines || null;
  const canLine = fmLines?.[f.scope]?.[f.stat] || null;
  const lineMin = canLine ? canLine[0] : 1;
  // A club and a player do not count the same things to the same numbers. The player shots ladder
  // runs 1..6; the TEAM shots ladder runs 7..23, because a side takes a dozen shots in a match and
  // "2+ shots, 99%" is not a forecast. The ceiling here was a hard `Math.min(6, lineMax)` written
  // when only players had markets, and it did not merely trim the team range -- it inverted it.
  // For team shots nLo became 7 and nHi 6, so the stepper's floor sat ABOVE its ceiling and the
  // market could not be asked for at all. Team corners and shots on target were cut off at 6 the
  // same way. The ladder the scope actually has is the only thing that should bound this.
  const lineMax = canLine ? canLine[canLine.length - 1] : (f.scope === "team" ? 25 : 6);
  // Only forecast mode is constrained to rungs. "1+ tackle in 6 of his last 10" is a perfectly
  // good question about history, and clamping it would take away an answer we do have -- but the
  // ceiling still has to clear what a club does, or the same cut-off returns through the back door.
  const nLo = f.mode === "likelihood" ? lineMin : 1;
  const nHi = f.mode === "likelihood" ? lineMax : Math.max(6, lineMax);
  const all = f.scope === "team" ? [...TEAM_STATS, ...(f.mode === "likelihood" ? MATCH_STATS : [])] : STATS.filter((s) => s.id !== "minutes");
  const pool = f.mode !== "likelihood" ? all : have ? all.filter((s) => have.includes(s.id)) : all.filter((s) => s.core);
  // And when the reader's stat is not one of them, say so instead of swapping it for shots behind
  // their back, which is what `pool[0]` quietly did.
  const noFc = f.mode === "likelihood" && have && !have.includes(f.stat);
  // When we cannot forecast their choice, the sentence keeps saying THEIR choice. Falling back to
  // shots here left the sentence reading "2+ shots" beside a notice about fouls committed, which
  // is the silent swap again wearing an explanation. `run` refuses to search while noFc, so this
  // never reaches the request.
  const chosen = all.find((x) => x.id === f.stat);
  const stat = (noFc && chosen) || pool.find((x) => x.id === f.stat) || pool[0] || all[0];
  const set = (patch) => {
    const n = { ...f, ...patch };
    if (!(n.scope === "team" ? [...TEAM_STATS, ...MATCH_STATS] : STATS).some((s) => s.id === n.stat)) n.stat = "shots";
    // Switching Players -> Teams used to reset the STAT if it did not exist for clubs and leave the
    // NUMBER untouched, so the sentence read "teams with 2+ shots" -- a line every side in the
    // league clears, and one no team ladder holds a rung for. Carry the number into the new
    // subject's ladder instead: keep it where it still makes sense, pull it to the nearest rung
    // where it does not. Forecast mode only, for the reason given at nLo above.
    const lad = n.mode === "likelihood" ? fmLines?.[n.scope]?.[n.stat] : null;
    if (lad && lad.length) {
      const lo = lad[0], hi = lad[lad.length - 1], cur = Number(n.n);
      if (!Number.isFinite(cur) || cur < lo || cur > hi) n.n = String(Math.min(Math.max(cur || lo, lo), hi));
    }
    setRes({ rows: null, err: null, busy: false });
    setSp(Object.fromEntries(Object.entries(n).filter(([k, v]) => v !== "" && DEF[k] !== v)), { replace: true });
  };
  const run = async () => {
    if (!picked.length || out || noFc) return;
    setRes((r) => ({ ...r, err: null, busy: true }));
    try {
      const today = isoDay(new Date());
      const rows = await get("/finder", { mode: f.mode, stat: stat.id, threshold: Number(f.n), scope: f.scope, last_n: f.last_n, leagues: f.leagues,
        day: f.day || today, tz: -new Date().getTimezoneOffset(),
        venue: f.venue || undefined, positions: f.scope === "player" ? f.positions : "",
        // Both of these have been parameters of the search since it was written and no browser
        // could ever send them.
        min_minutes: f.scope === "player" && /^\d+$/.test(f.gt) ? Number(f.gt) : undefined,
        started: f.scope === "player" && f.gt === "started" ? true : undefined,
        min_reached: f.mode === "form" ? Number(f.min) / Number(f.last_n) : undefined }, { quiet: true });
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
  // A start sets everything except the leagues, which stay as the reader left them: their plan
  // decides how many they may search and we have no business guessing which.
  const pickStart = (t) => {
    const q = new URLSearchParams(t.q);
    if (f.leagues) q.set("leagues", f.leagues);
    if (f.day) q.set("day", f.day);
    setRes({ rows: null, err: null, busy: false });
    setSp(q, { replace: true });
  };
  const statOf = (q) => {
    const sp2 = new URLSearchParams(q);
    const pool = sp2.get("scope") === "team" ? TEAM_STATS : STATS;
    return (pool.find((x) => x.id === sp2.get("stat")) || { label: sp2.get("stat") }).label;
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
          <span className="fs-step"><button type="button" className="k-icon-btn" onClick={() => set({ n: String(Math.max(nLo, Number(f.n) - 1)) })} aria-label="Fewer" data-testid="finder-n-down">−</button><b>{f.n}+</b>
            <button type="button" className="k-icon-btn" onClick={() => set({ n: String(Math.min(nHi, Number(f.n) + 1)) })} aria-label="More" data-testid="finder-n-up">+</button></span></Part>{" "}
        <Part id="stat" label={stat.label.toLowerCase()} open={open} setOpen={setOpen}>
          <span className="fs-list">{pool.map((s) => <button key={s.id} type="button" className={`k-chip${s.id === stat.id ? " on" : ""}`} onClick={() => { set({ stat: s.id }); setOpen(null); }} data-testid={`finder-stat-${s.id}`}>{s.label}</button>)}</span></Part>
        {f.mode !== "likelihood" && <>{" in "}<Part id="window" label={f.mode === "run" ? `a row, last ${f.last_n}` : `${f.min} of the last ${f.last_n}`} open={open} setOpen={setOpen}>
          <span className="fs-sliders"><small>Games</small><RangeSlider min={5} max={20} value={Number(f.last_n)} onChange={(v) => set({ last_n: String(v), min: String(Math.min(Number(f.min), v)) })} label="Games window" format={(v) => `${v} games`} testid="finder-window" />
            {f.mode === "form" && <><small>Reached in at least</small><RangeSlider min={1} max={Number(f.last_n)} value={Number(f.min)} onChange={(v) => set({ min: String(v) })} label="How often" format={(v) => `${v} of ${f.last_n}`} testid="finder-min" /></>}</span></Part>{" "}
          {f.scope === "player"
            ? <Part id="gt" label={(GAMETIME.find((g) => g.id === f.gt) || GAMETIME[0]).label} open={open} setOpen={setOpen}>
                <span className="fs-list fs-list--rows">{GAMETIME.map((g) => (
                  <button key={g.id || "any"} type="button" className={`k-chip fs-gt${g.id === f.gt ? " on" : ""}`} aria-pressed={g.id === f.gt}
                          onClick={() => { set({ gt: g.id }); setOpen(null); }} data-testid={`finder-gt-${g.id || "any"}`}>
                    <b>{g.label}</b><small>{g.hint}</small>
                  </button>))}</span></Part>
            : "games"}</>}
        {f.mode !== "likelihood" && <>{", "}<Part id="venue" label={f.venue ? `at ${f.venue}` : "home or away"} open={open} setOpen={setOpen}>
          <Segmented label="Venue" value={f.venue} onChange={(v) => set({ venue: v })} options={[{ id: "", label: "All" }, { id: "home", label: "Home" }, { id: "away", label: "Away" }]} testid="finder-venue" /></Part></>}
        {f.scope === "player" && <>{", "}<Part id="pos" label={f.positions ? f.positions.split(",").join("/") : "any position"} open={open} setOpen={setOpen}>
          <ChipsRow multi label="Position" value={f.positions ? f.positions.split(",") : []} onChange={(v) => set({ positions: v.join(",") })} options={POS.map((p) => ({ id: p, label: p }))} testid="finder-pos" /></Part></>}
        {" in "}<Part id="leagues" label={lgLabel} open={open} setOpen={setOpen}>
          <span className="fs-list">{max >= 0 && <small className="k-faint">Up to {max} on your plan <ProLock label="More with Pro" testid="finder-leagues-pro" /></small>}{leagues.map((l) => {
            const on = picked.includes(l.id);
            return <button key={l.id} type="button" className={`k-chip${on ? " on" : ""}`} aria-pressed={on} onClick={() => set({ leagues: (on ? picked.filter((x) => x !== l.id) : max >= 0 && picked.length >= max ? [...picked.slice(1), l.id] : [...picked, l.id]).join(",") })} data-testid={`finder-league-${l.id}`}>{l.name}</button>;
          })}</span></Part>
        {" playing "}<Part id="day" label={dayLabel(f.day)} open={open} setOpen={setOpen}>
          <span className="fs-days"><DateScroller value={f.day || isoDay(new Date())} onChange={(v) => { set({ day: v === isoDay(new Date()) ? "" : v }); setOpen(null); }} from={0} count={7} testid="finder-day" /></span></Part>
      </p>
      <div className="fs-actions">
        {!unlimited && <button type="button" className="btn btn--primary" disabled={res.busy || !picked.length || out} onClick={run} data-testid="finder-run">{res.busy ? "Searching…" : !picked.length ? "Pick a league first" : out ? "No searches left today" : "Update results"}</button>}
        {/* A saved question is the SETTINGS, not the answer. This was gated on `res.rows`, so it
            appeared only after a search had returned -- which reads as "mobile has it and desktop
            does not" to anyone who runs a search on one and not the other. savePreset only ever
            serialised the query string, so it never needed results at all. */}
        {!!picked.length && !noFc && <button type="button" className="btn btn--secondary" onClick={savePreset} data-testid="finder-save-preset">Save this search</button>}
        <button type="button" className="k-link" onClick={() => { setSp({}); setRes({ rows: null, err: null, busy: false }); }} data-testid="finder-reset">Reset</button>
        {cap != null && cap >= 0 && <Meter used={used} cap={cap} visitor={visitor} />}
      </div>
      {noFc && <p className="a-notice fs-nofc" data-testid="finder-no-forecast">
        <Icon name="info" size={16} />
        <span>We do not forecast {(all.find((s) => s.id === f.stat) || { label: f.stat }).label.toLowerCase()} yet, so this mode cannot answer it.
          {" "}<button type="button" className="k-link" onClick={() => set({ mode: "form" })} data-testid="finder-nofc-count">Count it instead</button>, or pick a line we do forecast.</span>
      </p>}
      {out && <Wall visitor={visitor} cap={cap} freeCap={entitlements?.finder_searches_per_day} next={`/finder${sp.toString() ? `?${sp}` : ""}`} />}
      {res.busy && !res.rows ? <Skeleton shape="row" count={5} testid="finder-loading" />
        : res.err ? <ErrorState message={res.err.message || "The search did not work."} onRetry={run} testid="finder-error" />
        : !res.rows ? <Starts onPick={pickStart} statOf={statOf} />
        : !res.rows.length ? <EmptyState icon="search" title="Nothing meets that line" testid="finder-empty">Try a lower line, a longer window or another league.</EmptyState>
        : f.mode === "likelihood" ? <div className="fgrid" data-testid="finder-results">{res.rows.map((r) => <ForecastCard key={r.id} f={r} testid={`finder-fc-${r.id}`} />)}</div>
        : <><ul className="fs-results card" data-testid="finder-results">{res.rows.map((r) => <Row key={r.id} r={r} f={f} canLine={canLine} statLabel={stat.label.toLowerCase()} />)}</ul>
            <p className="fs-count muted small" data-testid="finder-count">
              {res.rows.length >= 100 ? "The first 100. Narrow the search -- a longer window or a higher line -- to see fewer and better."
                : `${res.rows.length} ${res.rows.length === 1 ? "match" : "matches"}, all of them.`}
            </p></>}
    </section>
  );
}
