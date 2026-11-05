// Insights: strongest forecasts across leagues (docs/24 §4).
import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useApi } from "../lib/useApi";
import { pct } from "../lib/copy";
import { useAuth } from "../lib/auth";
import { utc } from "../lib/time";
import { favFirst, useDayLeagues, useFavLeagues, useGameDays } from "../lib/prefs";
import { useTitle } from "../components/Football";
import Icon from "../components/Icon";
import { ChipsRow, DateScroller, EmptyState, ErrorState, FilterGroup, FilterSheet, ForecastCard, ProLock, RangeSlider, Segmented, Skeleton, TierBadge, isoDay } from "../components/ui";
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

function Compact({ rows }) {
  return (
    <ul className="ins-compact" data-testid="ins-compact">{rows.map((f) => (
      <li key={f.id}><TierBadge tier={f.tier} testid={`ins-row-tier-${f.id}`} /><span><b>{f.player?.name || f.team?.name}</b> {f.market}</span><small className="k-faint">{f.team?.name} v {f.opp?.name}</small><b>{pct(f.p)}</b></li>
    ))}</ul>
  );
}

export function Insights() {
  const { entitlements } = useAuth();
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
  // A card leads with its most telling line, which is rarely its most likely one. "At least N% likely" therefore
  // asks about the best line the card holds (best_p), or nothing a player owns above N% would ever match (docs/46).
  const rows = data.filter((f) => (!day || isoDay(utc(f.kickoff)) === day) && Math.max(f.p, f.best_p ?? 0) * 100 >= more.min
    && (!more.pos.length || more.pos.includes(pos(f))) && (more.venue === "all" || (f.team_iid === f.home_iid) === (more.venue === "home"))
    && (!more.confirmed || f.lineup_confirmed)
    && (!who || f.player?.id === who) && (!club || f.team?.id === club));
  const nMore = more.pos.length + (more.venue !== "all") + more.confirmed + (lg.length > 0);
  const nAll = nMore + (more.min > 0) + tier.length + (mk ? 1 : 0) + (who ? 1 : 0) + (club ? 1 : 0);
  const clearAll = () => { setDay(""); setLg([]); setMk(""); setTier([]); setMore(NOF); setWho(""); setClub(""); };
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
  useEffect(() => { setShowN(STEP); }, [day, mk, tier, lg, more, sort, who, club]);
  const sortWord = { edge: "biggest change first", likely: "most likely first", kickoff: "by kick-off" }[sort];
  const cap = entitlements?.insights_per_day;
  return (
    <section className="ins" data-testid="insights-page">
      <h1>Insights</h1>
      {q.data && <p className="ins-answer" data-testid="ins-answer">
        <b>{rows.length} line{rows.length === 1 ? "" : "s"} worth reading</b> across {groups.length} match{groups.length === 1 ? "" : "es"}, {sortWord}.
      </p>}
      <div className="ins-days"><button type="button" className={`k-chip${!day ? " on" : ""}`} onClick={() => setDay("")} aria-pressed={!day} data-testid="ins-any-day">Any day</button>
        <DateScroller value={day} onChange={setDay} from={0} count={7} gameDays={gameDays} dayLeagues={dayLeagues} testid="ins-dates" /></div>
      {/* UX_AUDIT section 2, decisions 1 to 3. This was an open panel of five controls followed by a
          separate sort row: eleven controls above the fold, so on a phone the first forecast began
          about 900px down. A page that promises to tell you what is worth knowing should not open by
          asking you to compose a query. The bar now states the current view in words, and every
          filter lives in the one sheet rather than being split between an open panel and a hidden one. */}
      <div className="ins-bar v2-bar" data-testid="ins-filters-panel">
        <Segmented label="Sort" value={sort} onChange={setSort} testid="ins-sort" options={[{ id: "edge", label: "Biggest change" }, { id: "likely", label: "Most likely" }, { id: "kickoff", label: "Kick-off" }]} />
        <div className="v2-bar-r">
          <button type="button" className={`k-chip${nAll ? " br" : ""}`} onClick={() => setSheet(true)} data-testid="ins-more-more">
            <Icon name="settings" size={16} />Filters{nAll ? <span className="k-count">{nAll}</span> : null}
          </button>
          {nAll > 0 && <button type="button" className="k-link" onClick={clearAll} data-testid="ins-clear-top">Clear</button>}
          <Segmented label="View" value={view} onChange={setView} testid="ins-view" options={[{ id: "cards", label: "Cards" }, { id: "list", label: "List" }]} />
        </div>
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
              <div className="fgrid ins-grid">{g.rows.map((f) => <ForecastCard key={f.id} f={f} showTime={false} testid={`ins-card-${f.id}`} />)}</div>
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
      {cap >= 0 && data.length >= cap && <p className="notice small" data-testid="ins-capped">Your plan shows {cap} insights a day. <ProLock label="Unlimited with Pro" testid="ins-capped-pro" /></p>}
      <FilterSheet open={sheet} onClose={() => setSheet(false)} onReset={clearAll} count={rows.length} title="Filters" testid="ins-filters">
        <FilterGroup label="Market"><ChipsRow value={mk || "all"} onChange={(v) => setMk(v === "all" || v === mk ? "" : v)} label="Market" testid="ins-market" options={[{ id: "all", label: "All" }, ...MARKETS.map(({ id, label }) => ({ id, label }))]} /></FilterGroup>
        <FilterGroup label="Tier"><ChipsRow multi value={tier} onChange={setTier} label="Tier" testid="ins-tier" options={TIERS.map((t) => ({ id: t, label: t }))} /></FilterGroup>
        <FilterGroup label="Player">
          <select className="ins-pick" value={who} onChange={(e) => setWho(e.target.value)} aria-label="Player" data-testid="ins-player">
            <option value="">Every player</option>
            {players.map(([id, name]) => <option key={id} value={id}>{name}</option>)}
          </select>
        </FilterGroup>
        <FilterGroup label="Club">
          <select className="ins-pick" value={club} onChange={(e) => setClub(e.target.value)} aria-label="Club" data-testid="ins-team">
            <option value="">Every club</option>
            {clubs.map(([id, name]) => <option key={id} value={id}>{name}</option>)}
          </select>
        </FilterGroup>
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
