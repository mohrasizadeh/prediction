// Insights: strongest forecasts across leagues (docs/24 §4).
import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useApi } from "../lib/useApi";
import { useLiveLines } from "../lib/live";
import { pct, tierLabel } from "../lib/copy";
import { useAuth } from "../lib/auth";
import { utc } from "../lib/time";
import { favFirst, useDayLeagues, useFavLeagues, useGameDays } from "../lib/prefs";
import { useTitle } from "../components/Football";
import { Crest, PlayerAvatar } from "../components/Media";
import { ChipsRow, DateScroller, EmptyState, ErrorState, FilterGroup, FilterSheet, ForecastList, ProLock, RangeSlider, Segmented, Skeleton, TierBadge, isoDay } from "../components/ui";
import { fixtureOf, timeOf } from "../components/ui/ForecastCard";

const MARKETS = [{ id: "shots", label: "Shots", q: { stat: "shots", scope: "player" } }, { id: "sot", label: "On target", q: { stat: "sot" } },
  { id: "tackles", label: "Tackles", q: { stat: "tackles" } }, { id: "corners", label: "Corners", q: { stat: "corners" } },
  { id: "team_shots", label: "Team shots", q: { stat: "shots", scope: "team" } }, { id: "cards", label: "Cards", q: { stat: "yellow_cards" } }];
const TIERS = ["Strong", "Solid", "Watch"];
const POS = [{ id: "G", label: "GK" }, { id: "D", label: "DEF" }, { id: "M", label: "MID" }, { id: "F", label: "FWD" }];
// docs/52: the floor used to be 50% because no line below that existed -- engine.line_band started there.
// With a line for each player and team, a forecast BELOW an entity's usual is as real as one above
// ("likely to fall well short of his normal game"), and a 50% floor silently threw all of them away:
// 20 cards became 8 on the first run. The floor is 0 and the slider reaches it.
const NOF = { min: 0, pos: [], venue: "all", confirmed: false };

// The list edition of the same rows. Four children per row, always four, because the shared grid
// assigns its areas by position (matchday.css .ins-compact li > :nth-child(n)): a row that dropped
// its first child when a line had no tier slid the name into the face's column and the percentage
// out of its own, so one untiered line bent the whole list. The subject wears its face here as it
// does on the card (docs/19 §5), and the tier sits with the percentage it grades (docs/58), not
// beside the name it does not.
function Compact({ rows }) {
  return (
    <ul className="ins-compact" data-testid="ins-compact">{rows.map((f) => (
      <li key={f.id}>
        <span className="ins-row-face">{f.player ? <PlayerAvatar player={f.player} size={32} /> : <Crest team={f.team} size={32} />}</span>
        <span><b>{f.player?.name || f.team?.name}</b> {f.market}</span>
        <small className="k-faint">{f.team?.name} v {f.opp?.name}</small>
        <span className="ins-row-p"><b>{pct(f.p)}</b><TierBadge tier={f.tier} testid={`ins-row-tier-${f.id}`} /></span>
      </li>
    ))}</ul>
  );
}

export function Insights() {
  const { entitlements } = useAuth();
  // The same live tracking the match page has always had. A feed where last night's forecasts
  // visibly went green is the argument this product can make and a counting tool cannot.
  const track = useLiveLines();
  const [sp] = useSearchParams();
  const [lg, setLg] = useState([]);
  const [mk, setMk] = useState("");
  const [tier, setTier] = useState([]);
  const [more, setMore] = useState(NOF);
  const [sheet, setSheet] = useState(false);
  const [sort, setSort] = useState("edge");
  const q = useApi("/insights", { limit: 200, sort, ...(MARKETS.find((m) => m.id === mk)?.q || {}), leagues: lg.join(",") || undefined, tiers: tier.length ? tier.join(",") : undefined });
  const [who, setWho] = useState("");          // one player, by id (docs/52)
  const [club, setClub] = useState("");        // one club, by id
  const [day, setDay] = useState(sp.get("day") || "");
  const [view, setView] = useState("cards");
  useTitle("Insights");
  const data = useMemo(() => q.data || [], [q.data]);
  const fav = useFavLeagues();
  const gameDays = useGameDays(0, 7);
  const dayLeagues = useDayLeagues(0, 7);
  const lq = useApi("/leagues");
  const leagues = useMemo(() => favFirst((lq.data?.countries || []).flatMap((c) => c.leagues).map((l) => [l.id, l.name]), fav, ([id]) => id), [lq.data, fav]);
  const pos = (f) => (f.pos || f.player?.pos || "")[0];
  // docs/52: the pickers offer what this feed actually holds, so choosing one can never empty the list.
  const byId = (list) => [...new Map(list).entries()].sort((a, b) => a[1].localeCompare(b[1]));
  const players = useMemo(() => byId(data.filter((f) => f.player?.id).map((f) => [f.player.id, f.player.name])), [data]);
  const clubs = useMemo(() => byId(data.filter((f) => f.team?.id).map((f) => [f.team.id, f.team.name])), [data]);

  // The history clause. Empty means "do not ask about past games", which is the default so the
  // page still answers before it asks anything.
  const [hThr, setHThr] = useState("2");
  const [hWhen, setHWhen] = useState("");
  const hStat = MARKETS.find((m) => m.id === mk)?.q?.stat || "shots";
  const hq = useApi(hWhen ? "/finder" : null, {
    mode: hWhen === "run" ? "run" : "form", stat: hStat, threshold: Number(hThr) - 0.5,
    scope: "player", last_n: 10, limit: 300,
    ...(hWhen === "run" ? {} : { min_reached: Number(hWhen) / 10 }),
  });
  // The Finder returns internal ids; the feed carries the same ones, so the clause is a filter.
  const hIds = useMemo(() => (hWhen && Array.isArray(hq.data) ? new Set(hq.data.map((r) => r.id)) : null), [hWhen, hq.data]);
  // A card leads with its most telling line, which is rarely its most likely one. "At least N% likely" therefore
  // asks about the best line the card holds (best_p), or nothing a player owns above N% would ever match (docs/46).
  const matched = data.filter((f) => (!day || isoDay(utc(f.kickoff)) === day) && Math.max(f.p, f.best_p ?? 0) * 100 >= more.min
    && (!more.pos.length || more.pos.includes(pos(f))) && (more.venue === "all" || (f.team_iid === f.home_iid) === (more.venue === "home"))
    && (!more.confirmed || f.lineup_confirmed)
    && (!who || f.player?.id === who) && (!club || f.team?.id === club)
    && (!hIds || (f.player_iid != null && hIds.has(f.player_iid))));
  // The plan's daily cap, applied to what survived the reader's filters. The server used to apply
  // it to the pool the filters run over, which is why a player plainly in the data could be missing.
  const capN = entitlements?.insights_per_day;
  const rows = capN >= 0 ? matched.slice(0, capN) : matched;
  const nMore = more.pos.length + (more.venue !== "all") + more.confirmed + (lg.length > 0);
  const nAll = nMore + (more.min > 0) + tier.length + (mk ? 1 : 0) + (who ? 1 : 0) + (club ? 1 : 0) + (hWhen ? 1 : 0);
  const clearAll = () => { setDay(""); setLg([]); setMk(""); setTier([]); setMore(NOF); setWho(""); setClub(""); setHWhen(""); };
  // UX_AUDIT decision 4: a reader thinks in matches and kick-off times, not in a flat list of
  // twenty tiles. The feed groups by fixture so "everything about the 7pm game" is one block
  // instead of a scan of the whole page. Within a group the engine's own order is kept, so the
  // line with the most to say still leads.
  const groups = useMemo(() => {
    const by = new Map();
    for (const f of rows) {
      const k = f.match_iid;
      if (!by.has(k)) by.set(k, { key: k, kickoff: f.kickoff, fx: fixtureOf(f), rows: [] });
      by.get(k).rows.push(f);
    }
    const out = [...by.values()];
    // Kick-off order when that is the sort; otherwise the strongest group first, so the page still
    // opens with the best thing on it.
    if (sort === "kickoff") out.sort((a, b) => String(a.kickoff).localeCompare(String(b.kickoff)));
    return out;
  }, [rows, sort]);
  // UX_AUDIT decision 8: a reader scanning for something interesting wants to keep going. "Per page 25"
  // with page buttons is a table control for administering a result set.
  const STEP = 6;
  const [showN, setShowN] = useState(STEP);
  const shownGroups = groups.slice(0, showN);
  const shown = shownGroups.flatMap((g) => g.rows);
  useEffect(() => { setShowN(STEP); }, [day, mk, tier, lg, more, sort, who, club, hThr, hWhen]);
  const cap = capN;   // same value, named for the notice below
  return (
    <section className="ins" data-testid="insights-page">
      <h1>Insights</h1>
      {/* "20 lines worth reading" is honest and reads as an empty shelf next to a counting tool
          saying "1-30 of 609". The answer is not to inflate the number: it is to say what the
          filters took out, so restraint reads as a decision rather than as a thin feed. */}
      {q.data && <p className="ins-answer" data-testid="ins-answer">
        <b>{rows.length} line{rows.length === 1 ? "" : "s"} worth reading</b> across {groups.length} match{groups.length === 1 ? "" : "es"}.
        {data.length > matched.length && <> <button type="button" className="k-link ins-clearall" onClick={clearAll} data-testid="ins-filtered-out">
          {data.length - matched.length} more hidden by your filters &mdash; show them
        </button></>}
      </p>}
      <div className="ins-days"><button type="button" className={`k-chip${!day ? " on" : ""}`} onClick={() => setDay("")} aria-pressed={!day} data-testid="ins-any-day">Any day</button>
        <DateScroller value={day} onChange={setDay} from={0} count={7} gameDays={gameDays} dayLeagues={dayLeagues} testid="ins-dates" /></div>
      {/* CONSOLIDATION section 2. The Finder answers the same question as this page -- "find me a
          forecast" -- and returns the same cards, through a better control: a sentence in plain
          English where every underlined word is editable. This page stated its query as a number on
          a button ("Filters 3"), so a reader had to open a modal to find out what those three were.
          The sentence states the whole query in place, with no hidden state, and replaces the
          orientation line that used to say how many and in what order but never what they were about. */}
      <div className="v2-sayrow" data-testid="ins-filters-panel">
      <p className="v2-say" data-testid="ins-say">
        Showing{" "}
        <span className="v2-tok">
          <select value={mk} onChange={(e) => setMk(e.target.value)} aria-label="Market" data-testid="ins-market-say">
            <option value="">all markets</option>
            {MARKETS.map(({ id, label }) => <option key={id} value={id}>{label.toLowerCase()}</option>)}
          </select>
        </span>{" "}for{" "}
        <span className="v2-tok">
          <select value={who} onChange={(e) => setWho(e.target.value)} aria-label="Player" data-testid="ins-player">
            <option value="">every player</option>
            {players.map(([id, name]) => <option key={id} value={id}>{name}</option>)}
          </select>
        </span>{" "}at{" "}
        <span className="v2-tok">
          <select value={club} onChange={(e) => setClub(e.target.value)} aria-label="Club" data-testid="ins-team">
            <option value="">every club</option>
            {clubs.map(([id, name]) => <option key={id} value={id}>{name}</option>)}
          </select>
        </span>,{" "}
        <span className="v2-tok">
          <select value={sort} onChange={(e) => setSort(e.target.value)} aria-label="Order" data-testid="ins-sort">
            <option value="edge">biggest change</option>
            <option value="likely">most likely</option>
            <option value="kickoff">kick-off</option>
          </select>
        </span>{" "}first,{" "}
        {/* The Finder's clause, now filtering this page in place rather than sending the reader to
            another one. Its third mode, "Our forecast", was dropped: it ranked upcoming forecasts
            by likelihood, which is what this page already is. The two that remain look at PAST
            games, which this page cannot do from stored forecasts, so they run the Finder's query
            and narrow the feed to whoever comes back. The old labels named the mechanism ("How
            often", "Streak"); these say the thing in English. */}
        {" "}and have had{" "}
        <span className="v2-tok">
          <select value={hThr} onChange={(e) => setHThr(e.target.value)} aria-label="How many" data-testid="ins-h-thr">
            {[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n}+</option>)}
          </select>
        </span>{" "}
        <span className="v2-tok">
          <select value={hWhen} onChange={(e) => setHWhen(e.target.value)} aria-label="In past games" data-testid="ins-history">
            <option value="">in any run of games</option>
            <option value="6">in 6 of their last 10</option>
            <option value="8">in 8 of their last 10</option>
            <option value="10">in all of their last 10</option>
            <option value="run">in every game of a run right now</option>
          </select>
        </span>.{" "}
                <button type="button" className="k-link" onClick={() => setSheet(true)} data-testid="ins-more-more">
          More filters{nAll ? <span className="k-count">{nAll}</span> : null}
        </button>
        {nAll > 0 && <> <button type="button" className="k-link" onClick={clearAll} data-testid="ins-clear-top">Clear</button></>}
      </p>
        <Segmented label="View" value={view} onChange={setView} testid="ins-view" options={[{ id: "cards", label: "Cards" }, { id: "list", label: "List" }]} />
      </div>
      {q.loading && !q.data ? <Skeleton shape="card" count={6} testid="ins-loading" /> : q.error && !q.data ? <ErrorState message="We could not load the insights." onRetry={q.reload} testid="ins-error" />
        : !rows.length ? <EmptyState icon="sparkles" title="No forecasts match" testid="ins-empty" action={<button type="button" className="btn btn--secondary btn--sm" onClick={clearAll} data-testid="ins-clear">Clear all filters</button>}>Try another day, market or tier.</EmptyState>
        : view === "list" ? <Compact rows={shown} />
        : shownGroups.map((g) => (
            <section key={g.key} className="v2-match" data-testid={`ins-match-${g.key}`}>
              <header className="v2-match-head">
                <h2>{g.fx.text || "Match"}</h2>
                <span className="k-faint k-small">{timeOf(g.kickoff)}</span>
                <Link className="k-link" to={`/match/${g.rows[0].match_id || g.rows[0].match_iid}`}>Match page</Link>
              </header>
              {/* One legend for the grid, not one per card (docs/61). The strip's key was printed
                  under every card -- twenty times on this screen -- to explain a graphic that only
                  needs explaining once. And the column of percentages does not descend, because the
                  feed is ordered on how much a line has to say rather than on its size; a reader
                  running down a column of numbers that does not descend concludes the sort is
                  broken, so the screen says what it is sorted by. */}
              <p className="v2-run-key" data-testid={`ins-key-${g.key}`}>
                Ordered by how unlike their usual game this is, not by the biggest number. Under each strip:
                minutes above, opponent below (@ away).
              </p>
              <ForecastList rows={g.rows} track={track} testid={`ins-card-${g.key || "g"}`} />
            </section>
          ))}
      {groups.length > shownGroups.length && (
        <div className="v2-more">
          <button type="button" className="btn btn--secondary" onClick={() => setShowN((n) => n + STEP)} data-testid="ins-show-more">
            Show more matches
          </button>
          <span className="k-faint k-small" data-testid="ins-pager-count">{shownGroups.length} of {groups.length} matches</span>
        </div>
      )}
      {cap >= 0 && matched.length > cap && <p className="notice small" data-testid="ins-capped">Your plan shows {cap} insights a day. <ProLock label="Unlimited with Pro" testid="ins-capped-pro" /></p>}
      <FilterSheet open={sheet} onClose={() => setSheet(false)} onReset={clearAll} count={rows.length} title="Filters" testid="ins-filters">
        <FilterGroup label="Tier"><ChipsRow multi value={tier} onChange={setTier} label="Tier" testid="ins-tier" options={TIERS.map((t) => ({ id: t, label: tierLabel(t) }))} /></FilterGroup>
        {leagues.length > 1 && <FilterGroup label="League"><ChipsRow multi value={lg} onChange={setLg} label="League" testid="ins-league" options={leagues.map(([id, name]) => ({ id, label: name }))} /></FilterGroup>}
        <FilterGroup label="Position"><ChipsRow multi value={more.pos} onChange={(v) => setMore({ ...more, pos: v })} label="Position" options={POS} testid="ins-pos" /></FilterGroup>
        <FilterGroup label="Venue"><ChipsRow value={more.venue} onChange={(v) => setMore({ ...more, venue: v })} label="Venue" testid="ins-venue" options={[{ id: "all", label: "All" }, { id: "home", label: "Home" }, { id: "away", label: "Away" }]} /></FilterGroup>
        {/* The likelihood floor defaults to 0, so on the main surface it was a control that did nothing
            while holding a full row. It is a refinement for someone who has already looked. */}
        <FilterGroup label={<>At least <b data-testid="ins-min-value">{more.min}%</b> likely</>}>
          <RangeSlider min={0} max={95} step={5} value={more.min} onChange={(v) => setMore({ ...more, min: v })} label="Minimum likelihood" format={(v) => `${v}%`} testid="ins-min" />
        </FilterGroup>
        <label className="ins-switch"><input type="checkbox" checked={more.confirmed} onChange={(e) => setMore({ ...more, confirmed: e.target.checked })} data-testid="ins-confirmed" /><span>Lineup confirmed only</span></label>
      </FilterSheet>
    </section>
  );
}
