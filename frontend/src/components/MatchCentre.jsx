// Match centre parts (docs/24 §3): the hero and first tab change with the match state, Preview, Forecasts with
// a minimum-likelihood slider and By team / By market, and team Stats as split bars.
import { useEffect, useState } from "react";
import { tierLabel } from "../lib/copy";
import { Link } from "react-router-dom";
import { useApi } from "../lib/useApi";
import { utc } from "../lib/time";
import { Crest } from "./Media";
import { FollowButton } from "./Actions";
import LiveStatus from "./LiveStatus";
import TeamRadar from "./TeamRadar";
import { ShareCard } from "./Share";
import { num1 } from "./Football";
import BuildForMe from "./BuildForMe";
import { ChipsRow, EmptyState, ErrorState, ForecastList, RangeSlider, Segmented, Skeleton, WdlBar } from "./ui";
import { fxState, mLive } from "../lib/live";

const cardsOf = (d) => d.cards || d.forecasts;
export function matchState(d) {
  const m = d.match;
  if (m.status === "postponed" || m.status === "cancelled") return "off";
  if (m.status === "final" && m.hg != null) return "final";
  if (mLive(m)) return "live";
  return (d.starters || []).length && d.starters.every((s) => s.confirmed) ? "lineups" : "before";
}

function useCountdown(ko) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 30000); return () => clearInterval(t); }, []);
  const min = Math.round((utc(ko).getTime() - now) / 60000);
  if (min <= 0) return null;
  const dd = Math.floor(min / 1440), h = Math.floor((min % 1440) / 60), mm = min % 60;
  return dd ? `${dd}d ${h}h` : h ? `${h}h ${mm}m` : `${mm} min`;
}

// What each side has left to play for. This used to live in a `Situation` component that the
// redesign stopped rendering, so the chips vanished from the product while the engine kept
// computing them. They lead each club's "Worth knowing" lines in the side column (MatchSide), which
// make the same kind of claim; the referee has a card of its own there.
const SITUATION = { rel: "Relegation fight", race: "In the race at the top", dead: "Nothing left to play for" };
export const situationChips = (d) => [[d.home, d.match.home_iid], [d.away, d.match.away_iid]]
  .flatMap(([t, iid]) => Object.entries(d.context?.[iid]?.situation || {}).filter(([, v]) => v).map(([k]) => `${t.name}: ${SITUATION[k] || k}`));

// Goals per side, for the hero (docs/24 §3 Live / Finished). Two sources, two shapes, read only as
// the backend sends them: the stored match events (queries.match_detail, type "goal" with
// own_goal/penalty flags) once the match is in our database, and the live feed
// (sportapi.events_for, type goal / own_goal / penalty) while it is on. An own goal is listed with
// the side it COUNTS for -- the rule the stored events follow (side is the scorer's club; see
// tests/test_phase5_extras). A live row with no side says nothing we can place, so it is left out.
const LIVE_GOAL = { goal: "", penalty: "pen", own_goal: "" };   // an own goal says "(OG)" by the name
const minOf = (m, extra) => (m == null ? "" : `${String(m).replace(/'$/, "")}${extra && /^\d+$/.test(String(extra)) ? `+${extra}` : ""}'`);
function scorers(d) {
  const ev = (d.events || []).filter((e) => e.type === "goal");
  const rows = ev.length
    ? ev.map((e) => ({ side: e.side, og: !!e.own_goal, tag: e.own_goal ? "" : e.penalty ? "pen" : "", name: e.player?.name || e.player_name, min: minOf(e.minute, e.added) }))
    : (d.live_events || []).filter((e) => String(e.type).toLowerCase() in LIVE_GOAL && (e.side === "home" || e.side === "away"))
      .map((e) => { const t = String(e.type).toLowerCase(); return { side: e.side, og: t === "own_goal", tag: LIVE_GOAL[t], name: e.player_name, min: minOf(e.minute) }; });
  const out = { home: [], away: [] };
  rows.forEach((r) => {
    const side = r.og ? (r.side === "home" ? "away" : "home") : r.side;
    if (!out[side] || !r.name) return;
    const had = out[side].find((x) => x.name === r.name && x.og === r.og);
    const m = `${r.min}${r.tag ? ` ${r.tag}` : ""}`;
    if (had) had.mins.push(m); else out[side].push({ name: r.name, og: r.og, mins: [m] });
  });
  return out;
}

function Side({ team, align, children }) {
  return (
    <div className={`mc-side mc-side--${align}`}>
      <Link to={`/team/${team.id}`} className={`mc-team mc-team--${align}`} data-testid={`match-team-${align}`}><Crest team={team} size={64} eager /><b>{team.name}</b></Link>
      {children}
    </div>
  );
}

// Last five results under each club before kick-off (docs/24 §3, mockup match_preview_phone). The
// match payload carries no form, so it comes from the club's own page data (/teams/{id} `form`),
// newest first, the same pills the club page draws. Letters as well as colour, so it reads in
// greyscale and to a screen reader.
const RES = { W: "won", D: "drew", L: "lost" };
function FormRow({ form, testid }) {
  if (!form?.length) return null;
  const xs = form.slice(0, 5);
  return (
    <ol className="mc-form5" aria-label={`Last ${xs.length} results, newest first: ${xs.map((g) => RES[g.result] || g.result).join(", ")}`} data-testid={testid}>
      {xs.map((g) => <li key={g.match_iid} className={`fp fp--${g.result}`} aria-hidden="true" title={`${g.home ? "Home" : "Away"} v ${g.opp?.name || "opponent"}: ${g.gf}–${g.ga}`}>{g.result}</li>)}
    </ol>
  );
}

function Scorers({ list, align }) {
  if (!list.length) return null;
  return (
    <ul className={`mc-scorers mc-scorers--${align}`} aria-label="Goals" data-testid={`match-scorers-${align}`}>
      {list.map((g) => <li key={g.name + g.og}><span className="mc-scorer">{g.name}{g.og ? " (OG)" : ""}</span> <span className="mc-scorer-min">{g.mins.join(", ")}</span></li>)}
    </ul>
  );
}

// "Head to head, last 3 meetings: Team 0 2 wins · 1 draw". A zero is left out rather than printed
// as "Team 2 0", which read as a score.
const plural = (n, w) => `${n} ${w}${n === 1 ? "" : "s"}`;
function h2hLine(d) {
  const h = d.h2h, n = h.matches.length;
  const parts = [h.a_wins ? `${d.home.name} ${plural(h.a_wins, "win")}` : null, h.draws ? plural(h.draws, "draw") : null, h.b_wins ? `${d.away.name} ${plural(h.b_wins, "win")}` : null].filter(Boolean);
  return `Head to head, last ${plural(n, "meeting")}: ${parts.join(" · ")}`;
}

const koTime = (ko) => utc(ko).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
const koDay = (ko) => utc(ko).toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" });

export function Hero({ d, teams }) {
  const m = d.match, st = matchState(d), lv = m.live;
  const pre = st === "before" || st === "lineups";
  const cd = useCountdown(m.kickoff);
  // Competition and both clubs' form are not in the match payload; the club endpoint has both. The
  // match page already asks for both clubs (its side column needs their next matches) and passes
  // them in as `teams`, so the hero only asks itself when used without them.
  const thq = useApi(teams ? null : `/teams/${d.home.id}`);
  const taq = useApi(!teams && pre ? `/teams/${d.away.id}` : null);
  const th = teams ? teams[0] : thq, ta = teams ? teams[1] : taq;
  const league = th.data?.league;
  const last = (d.live_events || []).filter((e) => e.type !== "substitution").slice(-1)[0];
  const goals = st === "live" || st === "final" ? scorers(d) : { home: [], away: [] };
  const h = d.h2h;
  return (
    <section className={`mc-hero card mc-hero--${st}`} data-testid="match-hero" aria-label="Match summary">
      <p className="mc-when" data-testid="match-when">
        {st === "live" && <span className="k-livedot" aria-hidden="true" />}
        <span>
          {league && <><Link to={`/league/${league.id}`} className="mc-comp" data-testid="match-league">{league.name}</Link>{m.round != null && ` · Round ${m.round}`}{" · "}</>}
          <time dateTime={m.kickoff}>{pre ? koDay(m.kickoff) : `${koDay(m.kickoff)}, ${koTime(m.kickoff)}`}</time>
        </span>
      </p>
      <div className="mc-row">
        <Side team={d.home} align="home">{pre ? <FormRow form={th.data?.form} testid="match-form-home" /> : <Scorers list={goals.home} align="home" />}</Side>
        <div className="mc-mid">
          {st === "final" ? <><strong className="mc-score" data-testid="match-score" aria-label={`Final score ${m.hg}–${m.ag}`}>{m.hg} – {m.ag}</strong><span className="status-chip">Full time</span>
              {d.recap?.ht && <small className="mc-sub" data-testid="match-ht">Half-time {d.recap.ht[0]} – {d.recap.ht[1]}</small>}</>
            : st === "live" ? <><strong className="mc-score" data-testid="match-live-score">{lv.hs} – {lv.as}</strong><LiveStatus status={lv.status} state={lv.state} live={lv.playing} minute={lv.minute} testid="match-live-status" />
              {last && <small className="mc-last" data-testid="match-last-event">{String(last.type).replace(/_/g, " ")}{last.player_name ? `, ${last.player_name}` : ""} {last.minute}</small>}</>
            : st === "off" ? <><span className="mc-v" aria-hidden="true">v</span><span className="status-chip status-chip--off" data-testid="match-off">{m.status === "postponed" ? "Postponed" : "Cancelled"}</span>
              <small className="mc-sub">{m.status === "postponed" ? "New date to be confirmed" : "This match will not be played"}</small></>
            : <><strong className="mc-ko" data-testid="match-ko"><span className="sr-only">Kick-off </span>{koTime(m.kickoff)}</strong>
              {cd ? <span className="mc-cd" data-testid="match-countdown">in {cd}</span> : <small className="mc-sub">Kick-off time passed</small>}</>}
          {st === "lineups" && <span className="k-tag k-tag--up" data-testid="match-lineups-confirmed">Lineups confirmed</span>}
        </div>
        <Side team={d.away} align="away">{pre ? <FormRow form={ta.data?.form} testid="match-form-away" /> : <Scorers list={goals.away} align="away" />}</Side>
      </div>
      {pre && d.probs && <WdlBar home={d.probs.p_home} draw={d.probs.p_draw} away={d.probs.p_away} homeName={d.home.name} awayName={d.away.name} showDraw testid="match-wdl" />}
      {st === "final" && d.recap?.scored > 0 && <p className="mc-hero-recap" data-testid="match-recap">How our forecasts did: <b>{d.recap.hit} of {d.recap.scored}</b> Strong and Solid forecasts came true
        {["Strong", "Solid"].filter((t) => d.recap.by_tier[t][1]).map((t) => ` · ${tierLabel(t)} ${d.recap.by_tier[t][0]}/${d.recap.by_tier[t][1]}`).join("")}</p>}
      <div className="mc-foot">
        <div className="mc-meta">
          {/* After kick-off these are still our numbers from BEFORE it, and "expected goals" beside a
              real score reads as the match's own. A postponed match has no expected anything. */}
          {d.probs && st !== "off" && <small className="mc-sub" data-testid="match-xg">{pre ? "Expected goals" : "Our pre-match expected goals"} {num1(d.probs.xg_home)} – {num1(d.probs.xg_away)}</small>}
          {pre && h?.matches?.length > 0 && <small className="mc-sub" data-testid="match-h2h-line">{h2hLine(d)}</small>}
          {(m.referee || m.stadium) && <small className="mc-sub" data-testid="match-meta">{m.stadium}{m.referee && m.stadium ? " · " : ""}{m.referee && <>Referee <Link to={`/referee/${encodeURIComponent(m.referee)}`} data-testid="match-referee-link">{m.referee}</Link></>}</small>}
        </div>
        <div className="mc-actions">{st !== "final" && st !== "off" && <FollowButton kind="match" refId={m.id} name={`${d.home?.name} v ${d.away?.name}`} />}<ShareCard d={d} /></div>
      </div>
    </section>
  );
}

// The compact bar that takes the hero's place once it has scrolled away (crest, score or kick-off,
// crest), so the score and the minute stay in view on a long Forecasts list. It repeats what the
// hero already said, so it is hidden from assistive tech; nothing in it is a control.
export function MiniBar({ d, shown }) {
  const m = d.match, st = matchState(d), lv = m.live;
  const mid = st === "final" ? `${m.hg} – ${m.ag}` : st === "live" ? `${lv.hs} – ${lv.as}` : st === "off" ? (m.status === "postponed" ? "Postponed" : "Cancelled") : koTime(m.kickoff);
  const sub = st === "final" ? "FT" : st === "live" ? (lv.minute === "HT" || lv.status === "HT" ? "HT" : lv.minute != null ? `${String(lv.minute).replace(/'$/, "")}'` : "Live") : st === "off" ? "" : koDay(m.kickoff);
  return (
    <div className={`mc-mini mc-mini--${st}${shown ? " is-shown" : ""}`} aria-hidden="true" data-testid="match-minibar">
      <span className="mc-mini-t"><span className="mc-mini-n">{d.home.name}</span><Crest team={d.home} size={24} /></span>
      <span className="mc-mini-mid"><b>{mid}</b>{sub && <small>{st === "live" && <span className="k-livedot" />}{sub}</small>}</span>
      <span className="mc-mini-t mc-mini-t--a"><Crest team={d.away} size={24} /><span className="mc-mini-n">{d.away.name}</span></span>
    </div>
  );
}

function useCompare(d) {
  return useApi("/teams/compare", { a: d.home.id, b: d.away.id, as_fixture: true });
}

// A By market heading is the market's name, not one rung of it: "1+ shot" became "shot · 2", lower
// case and singular above a list of 2+ and 3+ lines. "Shots · 2".
const marketHead = (m) => {
  const w = (m || "").replace(/^\s*\d+\+\s*/, "").replace(/^(\S*[^s\s])(?=\s|$)/, "$1s");
  return w ? w[0].toUpperCase() + w.slice(1) : "";
};

export function Forecasts({ d, matchId }) {
  // Without this the row cannot name the opponent or draw either crest: a match page's forecasts
  // carry team_iid/opp_iid, not the clubs themselves. ForecastCard resolved them from here, and
  // removing the card made this look unused rather than unwired.
  const fxTeams = { [d.match.home_iid]: d.home, [d.match.away_iid]: d.away };
  const live = !!d.match.live && fxState(d.match.live) !== "later" && d.match.status !== "postponed";
  // While the match is on, ask every 30 s which lines have happened. This used to stop at half time (docs/42).
  const lt = useApi(live && matchId ? `/matches/${matchId}/live-forecasts` : null, undefined, { every: mLive(d.match) ? 30000 : 0 });
  const track = lt.data?.active ? lt.data.items : null;
  const all = track ? cardsOf(d).flatMap((f) => [f, ...(f.more_lines || [])]) : [];
  const tracked = all.filter((x) => track[x.fkey] && track[x.fkey].state !== "unknown").length;
  const hits = all.filter((x) => track[x.fkey]?.state === "hit").length;
  const [min, setMin] = useState(50);
  const [by, setBy] = useState("team");
  // The slider answers "how likely", and the tier answers a different question -- how much is
  // behind the number -- so filtering by one could not stand in for the other. A reader who wants
  // the lines this product is prepared to stand behind had to read twenty-three cards and sort
  // them by badge in their head. Empty means every tier, so the tab opens showing everything.
  const [tiers, setTiers] = useState([]);
  const atMin = cardsOf(d).filter((f) => f.p * 100 >= min);
  // A match-total line ("Both teams", over 2.5 goals and friends) is created with tier: None by
  // design -- it is not graded against a player's usual because it is not about a player. The
  // filter did not know that, so selecting ANY tier chip silently removed the whole Both teams
  // group: the one market the code itself calls the one a stranger understands without being
  // taught, and which was buried once already. A filter that can hide a category it never offers
  // is not a filter, it is a trapdoor. Ungraded lines get a chip of their own.
  const rows = tiers.length
    ? atMin.filter((f) => (f.tier ? tiers.includes(f.tier) : tiers.includes("None")))
    : atMin;
  // Counted after the slider, so a chip's number is what tapping it would actually show.
  const TIERS = ["Strong", "Solid", "Watch"];
  const nUngraded = atMin.filter((f) => !f.tier).length;
  const tierOpts = [
    ...TIERS.map((t) => ({ id: t, label: tierLabel(t), count: atMin.filter((f) => f.tier === t).length })),
    ...(nUngraded ? [{ id: "None", label: "Match totals", count: nUngraded }] : []),
  ];
  const groups = by === "team"
    // "Both teams" holds the match lines -- total goals, total cards. It is the one market a
    // stranger understands without being taught, it is the only one that needs no statistics feed,
    // and it was rendered third, about 5,600px below the fold, behind twenty-two player cards.
    // Each group carries the club it is about, so the heading can wear its crest: this page named
    // both clubs and drew neither, which is the one identifier a reader recognises before reading.
    ? [["Both teams", rows.filter((f) => f.stat?.startsWith("match_")), null],
       [d.home.name, rows.filter((f) => f.team_iid === d.match.home_iid && !f.stat?.startsWith("match_")), d.home],
       [d.away.name, rows.filter((f) => f.team_iid === d.match.away_iid && !f.stat?.startsWith("match_")), d.away]]
    : [...new Set(rows.map((f) => f.stat))].map((s) => [marketHead(rows.find((f) => f.stat === s)?.market) || s, rows.filter((f) => f.stat === s), null]);
  return (
    <div className="mc-fc" data-testid="match-forecasts">
      {/* A postponed or cancelled match keeps its forecasts on file, but none of them can come true
          on this date, and the page said nothing about it. */}
      {(d.match.status === "postponed" || d.match.status === "cancelled") && cardsOf(d).length > 0 && <p className="mc-fc-note" data-testid="fc-off-note">{d.match.status === "postponed" ? "This match was postponed. These forecasts were made for the original date and will be worked out again for the new one." : "This match was cancelled, so none of these forecasts will be settled."}</p>}
      {track && <p className="lv-sum" data-testid="match-live-sum"><span className="k-livedot" aria-hidden="true" />{tracked ? <span><b>{hits} of {tracked}</b> lines we can follow have happened{lt.data.final ? "." : ". Updates every 30 seconds."}</span> : <span>Lines tick green here as cards and match numbers come in.</span>}</p>}
      {/* UX_AUDIT section 4, again: on a phone the controls were five stacked rows -- Build, the
          grouping, a slider wearing a floating value tag, a rule, the tier chips -- about 330px
          before the first forecast. Now one panel: grouping and Build on one line, then the floor
          (its value printed beside it, not floating over it) and the tier chips on one line that
          scrolls sideways on a phone instead of wrapping. Hidden altogether when there is nothing
          to filter. */}
      {cardsOf(d).length > 0 && <div className="mc-fc-ctl" data-testid="fc-controls">
        <div className="mc-fc-bar">
          <Segmented options={[{ id: "team", label: "By team" }, { id: "market", label: "By market" }]} value={by} onChange={setBy} label="Group forecasts" testid="fc-group" />
          {matchId && d.match.status === "scheduled" && <span className="mc-fc-build"><small className="mc-fc-hint">Tap + on a line to start a combo, or</small><BuildForMe matchId={matchId} /></span>}
        </div>
        <div className="mc-fc-filters">
          <div className="mc-fc-min"><span className="mc-fc-minval" aria-hidden="true">At least <b>{min}%</b></span><RangeSlider min={50} max={95} step={5} value={min} onChange={setMin} label="Minimum likelihood" format={(v) => `${v}% or more`} testid="fc-min" /></div>
          <div className="mc-fc-tiers">
            <ChipsRow options={tierOpts} value={tiers} onChange={setTiers} multi label="Tier" testid="fc-tier" />
            {tiers.length > 0 && <button type="button" className="k-link" onClick={() => setTiers([])} data-testid="fc-tier-all">All tiers</button>}
          </div>
        </div>
      </div>}
      {!cardsOf(d).length ? <EmptyState icon="target" title="No forecasts yet" testid="fc-empty">They appear once the engine has run for this match.</EmptyState>
        : !rows.length ? <EmptyState icon="target" title={tiers.length ? `Nothing in ${tiers.join(" or ")} at ${min}% or more` : `Nothing at ${min}% or more`} testid="fc-none" action={<button type="button" className="btn btn--secondary btn--sm" onClick={() => { setMin(50); setTiers([]); }} data-testid="fc-reset">Show all</button>}>{tiers.length ? "Widen the tier, or lower the minimum likelihood." : "Lower the minimum likelihood."}</EmptyState>
        : groups.filter(([, xs]) => xs.length).map(([title, xs, club]) => (
          <section key={title} className="mc-fc-group"><header className="v2-sec-head"><h2 className="k-sec v2-sec">{club && <Crest team={club} size={22} />}{title} · {xs.length}</h2></header>
            {/* The same row Most likely draws, from the shared kit. A grid of cards and this row
                were two presentations of one object, and the card was on ten surfaces only because
                the agreed one had never been extracted from that page. */}
            {/* Through ForecastList, not a bare <table>: the list carries the colgroup that gives the
                fixed-layout table its column widths. Without it all eight columns came out equal
                (135px each at 1366px), so the run strip sat on top of the line stepper and the
                market shrank to "s". It also brings the column headings Most likely has. */}
            <ForecastList rows={xs} teams={fxTeams} homeIid={d.match.home_iid} track={track} testid={`match-fc-${title}`} /></section>
        ))}
    </div>
  );
}

export function Form({ d }) {
  const c = useCompare(d);
  if (c.loading && !c.data) return <Skeleton shape="row" count={5} testid="match-stats-loading" />;
  if (c.error) return <ErrorState message="We could not load the team numbers." onRetry={c.reload} testid="match-stats-error" />;
  const e = (c.data?.edges || []).filter((x) => ["shots", "sot", "corners", "poss", "xg", "goals"].includes(x.key));
  if (!e.length && !c.data?.radar?.length) return <EmptyState icon="bar-chart" title="No team numbers yet" testid="match-stats-empty">They appear after each club's first finished match this season.</EmptyState>;
  return (
    <div className="mc-form" data-testid="match-stats">
      {e.length > 0 && <div className="card mc-stats">
        <header className="v2-sec-head"><h2 className="k-sec v2-sec">Per game this season</h2></header>
        <p className="k-faint k-small">{d.home.name} at home, {d.away.name} away. Numbers from before kick-off.</p>
        <ul className="cp-edges">{e.map((x) => { const t = (x.a || 0) + (x.b || 0) || 1; return (
          <li key={x.key} className={`lean-${x.lean || "none"}`}><b>{num1(x.a)}</b><span className="cp-edge-mid"><small>{x.label}</small><span className="cp-edge-bar" aria-hidden="true"><i className="ea" style={{ width: `${(x.a / t) * 100}%` }} /><i className="eb" style={{ width: `${(x.b / t) * 100}%` }} /></span></span><b>{num1(x.b)}</b></li>); })}</ul>
      </div>}
      {c.data?.radar?.length > 0 && <div className="card mc-radar"><header className="v2-sec-head"><h2 className="k-sec v2-sec">Style shape</h2></header><TeamRadar axes={c.data.radar} aName={d.home.name} bName={d.away.name} games={c.data.radar_games} testid="match-radar" /></div>}
    </div>
  );
}
