// Today (docs/24 §1): day scroller, Top 3 for the day, live strip, filter chips, fixtures by league with a
// win/draw/loss bar and an insight chip. Data: GET /api/fixtures (the same call as before) and GET /api/insights.
import { useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useApi } from "../lib/useApi";
import { useAuth } from "../lib/auth";
import { pct } from "../lib/copy";
import { utc } from "../lib/time";
import { Crest, LeagueMark, PlayerAvatar } from "../components/Media";
import { favFirst, useDayLeagues, useFavLeagues, useGameDays } from "../lib/prefs";
import Icon from "../components/Icon";
import { useTitle } from "../components/Football";
import { ChipsRow, DateScroller, EmptyState, ErrorState, ForecastList, Hl, Skeleton, WdlBar, isoDay, useSessionDay } from "../components/ui";
import { atHalfTime, isLiveNow as isLive, useLiveLines } from "../lib/live";

const isOff = (m) => m.status === "postponed" || m.status === "cancelled";
const localDay = (s) => isoDay(utc(s));
const shift = (day, n) => { const d = new Date(`${day}T12:00:00`); d.setDate(d.getDate() + n); return isoDay(d); };
function until(s) {
  const min = Math.round((utc(s).getTime() - Date.now()) / 60000);
  if (min <= 0 || min > 24 * 60) return null;
  return min < 60 ? `in ${min} min` : `in ${Math.floor(min / 60)}h ${min % 60}m`;
}

// Top 3 are the day's most informative lines, at most two per match. Nothing below Solid.
//
// This used to sort by tier and then by the whole chance, which is the likeliest line rather than
// the one with the most to say -- and after docs/44 the likeliest line a player owns is always his
// dullest. Measured on the live feed, that ranking put up departures of +1.5, +1.0 and +1.9 points
// over the players' own usual, one of them a 9+ shots line whose span is 1.8 points: the exact card
// docs/56 was written to keep off the front page. Ranked by departure the same feed offers +10.0,
// +9.4 and +7.4.
//
// The API already sorts by `edge` (engine.feed_sort), so the fix is mostly to stop undoing it: keep
// the order the server sent, apply the tier floor, and drop rungs that would read the same against
// every opponent in the league.
const RANK = { Strong: 2, Solid: 1 };
export const MIN_SPAN = 0.05;                 // docs/56: below this a rung cannot move with the opponent
// A span of null means "we could not measure it", which must never be read as "it is small".
const canMove = (f) => f.span == null || Math.abs(f.span) >= MIN_SPAN;
export function topRated(rows, n = 3) {
  const tiered = rows.filter((x) => RANK[x.tier]);
  const pool = tiered.filter(canMove).length ? tiered.filter(canMove) : tiered;
  const per = {};
  const out = pool.filter((x) => (per[x.match_iid] = (per[x.match_iid] || 0) + 1) <= 2);
  return out.slice(0, n);
}

function Top3({ day }) {
  const q = useApi("/insights", { limit: 200 });
  const track = useLiveLines();            // lines tick green here now, not only on the match page
  const rows = (q.data || []).filter((x) => localDay(x.kickoff) === day);
  if (q.loading && !q.data) return <Skeleton shape="card" count={3} testid="today-top3-loading" />;
  const best = topRated(rows);
  if (!best.length) return null;
  return (
    <section className="td-top" aria-label="Top 3 for this day" data-testid="today-top3">
      <div className="td-sec-head"><h2 className="k-sec v2-sec">Furthest from usual <Hl>{day === isoDay(new Date()) ? "today" : utc(`${day}T12:00:00Z`).toLocaleDateString(undefined, { weekday: "long" })}</Hl></h2>
        <Link to={`/insights?day=${day}`} className="k-link" data-testid="today-see-all">See all {rows.length}</Link></div>
      {/* UX_AUDIT decision 9: this was a horizontal carousel inside a page that scrolls down, with the
          second card visibly clipped and nothing else to say more existed. Three items do not need a
          carousel; they need three rows, and then none of them is hidden. */}
      <ForecastList rows={best} track={track} testid="today-top" />
    </section>
  );
}

function StatusCell({ m, live }) {
  if (live) return <span className="td-min" data-testid={`today-live-status-${m.id}`} aria-label={atHalfTime(m.live.status, m.live.minute) ? "Live, half-time" : `Live, minute ${m.live.minute || ""}`}><span className="k-livedot" aria-hidden="true" />{atHalfTime(m.live.status, m.live.minute) ? "HT" : m.live.minute}</span>;
  if (m.status === "final") return <span className="td-ft" data-testid={`today-ft-${m.id}`}>FT</span>;
  if (isOff(m)) return <span className="td-off" data-testid={`today-off-${m.id}`}>{m.status === "postponed" ? "Postponed" : "Cancelled"}</span>;
  const soon = until(m.kickoff);
  return <><b>{utc(m.kickoff).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}</b>{soon && <small>{soon}</small>}</>;
}

function Row({ m }) {
  const live = isLive(m);
  const off = isOff(m);
  const started = !off && (m.status === "final" || (m.live && m.live.status !== "Scheduled" && m.live.hs != null));
  const hs = m.status === "final" && m.hg != null ? m.hg : m.live?.hs, as = m.status === "final" && m.ag != null ? m.ag : m.live?.as;
  const p = m.probs;
  const fin = m.status === "final" && hs != null && as != null;
  const lead = (mine, other) => ((fin || live) && mine > other ? " is-win" : fin && mine < other ? " is-lose" : "");
  // Three once the answers are known, one while the row is still a forecast and the reader is only
  // choosing which match to open.
  const all = m.best_lines?.length ? m.best_lines : (m.best_line ? [m.best_line] : []);
  const lines = (fin ? all.slice(0, 3) : all.slice(0, 1)).filter((b) => b?.market);
  return (
    <li>
      <Link to={`/match/${m.id}`} className={`td-row${live ? " is-live" : ""}${off ? " is-off" : ""}`} data-testid={`today-row-${m.id}`}>
        <span className="td-time"><StatusCell m={m} live={live} /></span>
        {/* Home, crest, score, crest, away -- the shape every score service uses, and the one a
            reader already knows how to read. It replaces two stacked lines with the score in a
            column of its own: that arrangement made the row twice as tall as it needed to be and
            left the two numbers reading as a column of singles rather than as "2-3".
            The alignment rule from the grid below still holds, and is in fact stronger here --
            the centre three cells are FIXED, so the score sits at the same x on every row and the
            two names share whatever is left. */}
        <span className="td-teams" aria-label={started ? `${m.home?.name} ${hs}, ${m.away?.name} ${as}` : `${m.home?.name} against ${m.away?.name}`}>
          <span className={"td-side td-side--h" + lead(hs, as)}>
            <span className="td-name">{m.home?.name}</span><Crest team={m.home} size={22} />
          </span>
          {started ? (
            <span className="td-scores" data-testid={`today-score-${m.id}`}>
              <b className="td-sc" data-testid={`today-live-${m.id}`}>{hs}</b>
              <span className="td-dash" aria-hidden="true">&ndash;</span>
              <b className="td-sc" data-testid={`today-away-score-${m.id}`}>{as}</b>
            </span>
          ) : <span className="td-scores td-scores--pre" aria-hidden="true">v</span>}
          <span className={"td-side td-side--a" + lead(as, hs)}>
            <Crest team={m.away} size={22} /><span className="td-name">{m.away?.name}</span>
          </span>
        </span>
        <span className="td-bar">{p && !fin && !off ? <WdlBar home={p.p_home} draw={p.p_draw} away={p.p_away} homeName={m.home?.name} awayName={m.away?.name} testid={`today-wdl-${m.id}`} /> : !p && !fin && !off ? <small className="k-faint">No forecast yet</small> : null}</span>
        {/* CRITIQUE section 1: this said "14 insights", and a count is not a value -- every fixture
            has a similar number, so the chip never helped a reader choose which match to open. It
            now names the lines most worth reading in that match, which is what the reader is
            actually deciding between.

            A finished row is a different object from an upcoming one. Upcoming, one line is right:
            the reader wants ONE reason to open this match rather than the next. Finished, the
            answers are known, and showing one of twenty we were right or wrong about throws away
            the product's whole argument at the moment it can be made -- so a result carries up to
            three, each saying whether it happened. The marks are a tick and a dash as well as a
            colour, because colour never carries the meaning on its own (docs/03). */}
        {lines.length && !off ? (
          <span className={"td-ins-set" + (fin ? " is-done" : "")} data-testid={`today-insights-${m.id}`}>
            {lines.map((b, i) => (
              <span key={i} className={"td-ins" + (b.reached === true ? " is-hit" : b.reached === false ? " is-miss" : "")}
                    data-testid={`today-ins-${m.id}-${i}`}>
                {b.reached != null && <Icon name={b.reached ? "check" : "minus"} size={13} />}
                {/* The face of whoever the claim is about. Most likely and the combo builder have
                    always drawn it from this very lookup; the fixture row was the one surface that
                    named a player it could not show, because _best_lines kept the name and dropped
                    the picture. A club line wears its crest, a player line a round portrait --
                    both fall back to a shield or initials on their own. */}
                <span className="td-ins-face">
                  {b.who_kind === "player"
                    ? <PlayerAvatar player={{ id: b.who_id, name: b.who, image: b.who_image }} size={18} />
                    : <Crest team={{ name: b.who, image: b.who_image }} size={18} />}
                </span>
                <span className="td-ins-claim"><b>{b.who}</b><i>{b.market}</i></span>
                {/* The likelihood NEVER disappears. It used to be replaced by the verdict the
                    moment the match ended, which deleted the claim at exactly the point it became
                    checkable: a reader saw "did not" with no denominator and scored it 0 out of 1.
                    Keeping the number and adding the measurement makes a hit and a miss the same
                    kind of object -- "71% - got 3" and "38% - got 3" -- so a column of graded
                    lines reads as a results table rather than as a verdict column. That is more
                    honest than what it replaces, not less: nothing is hidden, a number is
                    restored. */}
                <em>{pct(b.p)}{b.actual != null && <span className="td-got"> · got {Math.round(b.actual * 10) / 10}</span>}</em>
              </span>
            ))}
          </span>
        ) : m.insight_count > 0 && !off ? (
          <span className="td-ins" data-testid={`today-insights-${m.id}`}>{m.insight_count} line{m.insight_count === 1 ? "" : "s"}</span>
        ) : <span className="td-ins td-ins--none" aria-hidden="true" />}
      </Link>
    </li>
  );
}

function Group({ league, rows }) {
  const [open, setOpen] = useState(true);
  const nl = rows.filter(isLive).length;
  return (
    <section className="td-group card" data-testid={`today-league-${league?.id || "other"}`}>
      <button type="button" className="td-ghead" aria-expanded={open} onClick={() => setOpen(!open)} data-testid={`today-league-toggle-${league?.id || "other"}`}>
        <LeagueMark league={league} size={24} /><b>{league?.name || "Other"}</b>{nl > 0 && <span className="td-livebadge"><span className="k-livedot" aria-hidden="true" />{nl} live</span>}
        <small>{rows.length} match{rows.length === 1 ? "" : "es"}</small><Icon name="chevron-down" size={18} />
      </button>
      {open && <ul className="td-list">{rows.map((m) => <Row key={m.id} m={m} />)}</ul>}
    </section>
  );
}

export default function Today() {
  useTitle("Today");
  const [day, setDay] = useSessionDay("today-day");
  const [chip, setChip] = useState("all");
  const { user } = useAuth();
  const tz = -new Date().getTimezoneOffset();
  const isToday = day === isoDay(new Date());
  const fx = useApi("/fixtures", { date: day, tz }, { every: isToday ? 30000 : 0 });
  const fol = useApi(user ? "/me/follows" : null);
  const touch = useRef(null);
  const followed = useMemo(() => new Set((fol.data?.items || []).filter((x) => x.kind === "team" || x.kind === "league").map((x) => x.id)), [fol.data]);
  const all = fx.data || [];
  const isFol = (m) => followed.has(m.home?.id) || followed.has(m.away?.id) || followed.has(m.league?.id);
  const pick = { all: () => true, following: isFol, live: isLive, insights: (m) => m.insight_count > 0 }[chip];
  const fav = useFavLeagues();
  const gameDays = useGameDays(-1, 7);
  const dayLeagues = useDayLeagues(-1, 7);
  const groups = useMemo(() => {
    const g = new Map();
    all.filter(pick).forEach((m) => { const k = m.league?.id || "other"; if (!g.has(k)) g.set(k, { league: m.league, rows: [], fol: false }); g.get(k).rows.push(m); if (isFol(m)) g.get(k).fol = true; });
    g.forEach((v) => v.rows.sort((a, b) => Number(isLive(b)) - Number(isLive(a)) || utc(a.kickoff) - utc(b.kickoff)));
    return favFirst([...g.values()].sort((a, b) => Number(b.rows.some(isLive)) - Number(a.rows.some(isLive)) || Number(b.fol) - Number(a.fol)), fav, (x) => x.league?.id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [all, chip, followed, fav]);
  const live = all.filter(isLive);
  const chips = [{ id: "all", label: "All", count: all.length }, ...(user ? [{ id: "following", label: "Following", count: all.filter(isFol).length }] : []),
    { id: "live", label: "Live now", count: live.length }, { id: "insights", label: "With insights", count: all.filter((m) => m.insight_count > 0).length }];
  const swipe = { onTouchStart: (e) => { touch.current = e.touches[0].clientX; }, onTouchEnd: (e) => { const dx = e.changedTouches[0].clientX - (touch.current ?? 0); if (Math.abs(dx) > 70) setDay(shift(day, dx < 0 ? 1 : -1)); } };
  return (
    <section className="td" data-testid="today-page">
      <h1 className="sr-only">Today</h1>
      <DateScroller value={day} onChange={setDay} gameDays={gameDays} dayLeagues={dayLeagues} testid="today-dates" />
      <Top3 day={day} />
      {live.length > 0 && <div className="td-livestrip" aria-label="Live now" data-testid="today-livestrip">{live.map((m) => (
        <Link key={m.id} to={`/match/${m.id}`} className="td-livechip" data-testid={`today-livechip-${m.id}`}><span className="k-livedot" aria-hidden="true" /><b>{m.live.minute}</b>{m.home?.name} {m.live.hs}–{m.live.as} {m.away?.name}</Link>
      ))}</div>}
      <div className="td-chips"><ChipsRow options={chips} value={chip} onChange={setChip} label="Show" testid="today-filter" /></div>
      <div {...swipe}>
        {fx.loading && !fx.data ? <Skeleton shape="match" count={4} testid="today-loading" />
          : fx.error && !fx.data ? <ErrorState message="We could not load the fixtures." onRetry={fx.reload} testid="today-error" />
          : !groups.length ? (
            <EmptyState title={chip === "all" ? "No games on this day" : "Nothing matches this filter"} testid="today-empty"
              action={chip === "all" ? <button type="button" className="btn btn--secondary btn--sm" onClick={() => setDay(shift(day, 1))} data-testid="today-next-day">See the next day</button>
                : <button type="button" className="btn btn--secondary btn--sm" onClick={() => setChip("all")} data-testid="today-show-all">Show all matches</button>}>
              {chip === "all" ? "There are no matches in the leagues we cover on this day." : "Try All to see every match on this day."}
            </EmptyState>
          ) : groups.map((g) => <Group key={g.league?.id || "other"} league={g.league} rows={g.rows} />)}
        {/* The win/draw/loss legend lived here. It explained a bar that is no longer on the
            fixture list (section 42.5), it sat below all 35 matches where nobody reading a row
            could reach it, and it was never true of the percentages it sat under -- those are
            line likelihoods, not match outcomes. */}
      </div>
    </section>
  );
}
