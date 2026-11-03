// Insights: strongest forecasts across leagues (docs/24 §4).
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useApi } from "../lib/useApi";
import { pct } from "../lib/copy";
import { useAuth } from "../lib/auth";
import { utc } from "../lib/time";
import { favFirst, useDayLeagues, useFavLeagues, useGameDays } from "../lib/prefs";
import { useStored, useTitle } from "../components/Football";
import Icon from "../components/Icon";
import { ChipsRow, DateScroller, EmptyState, ErrorState, FilterGroup, FilterSheet, ForecastCard, ProLock, RangeSlider, Segmented, Skeleton, TierBadge, isoDay } from "../components/ui";

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
  // One card per player per market means more cards than before, so the list is paged rather than endless.
  const [per, setPer] = useStored("ins-per-page", 25);
  const [page, setPage] = useState(1);
  const pages = Math.max(1, Math.ceil(rows.length / per));
  const shown = rows.slice((Math.min(page, pages) - 1) * per, Math.min(page, pages) * per);
  useEffect(() => { setPage(1); }, [day, mk, tier, lg, more, sort, per, who, club]);
  const sortWord = { edge: "biggest change first", likely: "most likely first", kickoff: "by kick-off" }[sort];
  const cap = entitlements?.insights_per_day;
  return (
    <section className="ins" data-testid="insights-page">
      <h1>Insights</h1>
      {q.data && <p className="ins-answer" data-testid="ins-answer"><b>{rows.length} forecast{rows.length === 1 ? "" : "s"}</b> · {sortWord}</p>}
      <div className="ins-days"><button type="button" className={`k-chip${!day ? " on" : ""}`} onClick={() => setDay("")} aria-pressed={!day} data-testid="ins-any-day">Any day</button>
        <DateScroller value={day} onChange={setDay} from={0} count={7} gameDays={gameDays} dayLeagues={dayLeagues} testid="ins-dates" /></div>
      <section className="ins-filters card" aria-label="Filters" data-testid="ins-filters-panel">
        <div className="ins-f ins-f--min"><span className="ins-f-label">At least <b data-testid="ins-min-value">{more.min}%</b> likely</span>
          <RangeSlider min={0} max={95} step={5} value={more.min} onChange={(v) => setMore({ ...more, min: v })} label="Minimum likelihood" format={(v) => `${v}%`} testid="ins-min" /></div>
        <div className="ins-f"><span className="ins-f-label">Tier</span>
          <ChipsRow multi value={tier} onChange={setTier} label="Tier" testid="ins-tier" options={TIERS.map((t) => ({ id: t, label: t }))} /></div>
        <div className="ins-f"><span className="ins-f-label">Market</span>
          <ChipsRow value={mk || "all"} onChange={(v) => setMk(v === "all" || v === mk ? "" : v)} label="Market" testid="ins-market" options={[{ id: "all", label: "All" }, ...MARKETS.map(({ id, label }) => ({ id, label }))]} /></div>
        <div className="ins-f"><span className="ins-f-label">Player</span>
          <select className="ins-pick" value={who} onChange={(e) => setWho(e.target.value)} aria-label="Player" data-testid="ins-player">
            <option value="">Every player</option>
            {players.map(([id, name]) => <option key={id} value={id}>{name}</option>)}
          </select></div>
        <div className="ins-f"><span className="ins-f-label">Club</span>
          <select className="ins-pick" value={club} onChange={(e) => setClub(e.target.value)} aria-label="Club" data-testid="ins-team">
            <option value="">Every club</option>
            {clubs.map(([id, name]) => <option key={id} value={id}>{name}</option>)}
          </select></div>
        <div className="ins-f-foot">
          <button type="button" className={`k-chip${nMore ? " br" : ""}`} onClick={() => setSheet(true)} data-testid="ins-more-more"><Icon name="settings" size={16} />League and more{nMore ? <span className="k-count">{nMore}</span> : null}</button>
          {nAll > 0 && <button type="button" className="k-link" onClick={clearAll} data-testid="ins-clear-top">Clear filters</button>}
        </div>
      </section>
      <div className="ins-bar">
        <Segmented label="Sort" value={sort} onChange={setSort} testid="ins-sort" options={[{ id: "edge", label: "Different from usual" }, { id: "likely", label: "Most likely" }, { id: "kickoff", label: "Kick-off" }]} />
        <Segmented label="View" value={view} onChange={setView} testid="ins-view" options={[{ id: "cards", label: "Cards" }, { id: "list", label: "List" }]} />
      </div>
      {q.loading && !q.data ? <Skeleton shape="card" count={6} testid="ins-loading" /> : q.error && !q.data ? <ErrorState message="We could not load the insights." onRetry={q.reload} testid="ins-error" />
        : !rows.length ? <EmptyState icon="sparkles" title="No forecasts match" testid="ins-empty" action={<button type="button" className="btn btn--secondary btn--sm" onClick={clearAll} data-testid="ins-clear">Clear all filters</button>}>Try another day, market or tier.</EmptyState>
        : view === "list" ? <Compact rows={shown} /> : <div className="fgrid ins-grid">{shown.map((f) => <ForecastCard key={f.id} f={f} testid={`ins-card-${f.id}`} />)}</div>}
      {rows.length > 0 && (
        <nav className="ins-pager" aria-label="Pages" data-testid="ins-pager">
          <label className="ins-per">Per page
            <select value={per} onChange={(e) => setPer(Number(e.target.value))} aria-label="Cards per page" data-testid="ins-per-page">
              {[10, 25, 50, 100].map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </label>
          <span className="k-faint k-small" data-testid="ins-pager-count">
            {(Math.min(page, pages) - 1) * per + 1}–{Math.min(rows.length, Math.min(page, pages) * per)} of {rows.length}
          </span>
          {pages > 1 && (
            <span className="ins-pager-btns">
              <button type="button" className="btn btn--secondary btn--sm" disabled={page <= 1} onClick={() => setPage((n) => Math.max(1, n - 1))} data-testid="ins-prev">Previous</button>
              <span className="k-faint k-small">Page {Math.min(page, pages)} of {pages}</span>
              <button type="button" className="btn btn--secondary btn--sm" disabled={page >= pages} onClick={() => setPage((n) => Math.min(pages, n + 1))} data-testid="ins-next">Next</button>
            </span>
          )}
        </nav>
      )}
      {cap >= 0 && data.length >= cap && <p className="notice small" data-testid="ins-capped">Your plan shows {cap} insights a day. <ProLock label="Unlimited with Pro" testid="ins-capped-pro" /></p>}
      <FilterSheet open={sheet} onClose={() => setSheet(false)} onReset={() => { setMore({ ...NOF, min: more.min }); setLg([]); }} count={rows.length} title="League and more" testid="ins-filters">
        {leagues.length > 1 && <FilterGroup label="League"><ChipsRow multi value={lg} onChange={setLg} label="League" testid="ins-league" options={leagues.map(([id, name]) => ({ id, label: name }))} /></FilterGroup>}
        <FilterGroup label="Position"><ChipsRow multi value={more.pos} onChange={(v) => setMore({ ...more, pos: v })} label="Position" options={POS} testid="ins-pos" /></FilterGroup>
        <FilterGroup label="Venue"><Segmented value={more.venue} onChange={(v) => setMore({ ...more, venue: v })} label="Venue" options={[{ id: "all", label: "All" }, { id: "home", label: "Home" }, { id: "away", label: "Away" }]} testid="ins-venue" /></FilterGroup>
        <label className="ins-switch"><input type="checkbox" checked={more.confirmed} onChange={(e) => setMore({ ...more, confirmed: e.target.checked })} data-testid="ins-confirmed" /><span>Lineup confirmed only</span></label>
      </FilterSheet>
    </section>
  );
}
