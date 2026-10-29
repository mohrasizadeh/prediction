// Insights: strongest forecasts across leagues (docs/24 §4).
import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useApi } from "../lib/useApi";
import { pct } from "../lib/copy";
import { useAuth } from "../lib/auth";
import { utc } from "../lib/time";
import { favFirst, useFavLeagues, useGameDays } from "../lib/prefs";
import { useTitle } from "../components/Football";
import Icon from "../components/Icon";
import { ChipsRow, DateScroller, EmptyState, ErrorState, FilterGroup, FilterSheet, ForecastCard, ProLock, RangeSlider, Segmented, Skeleton, TierBadge, isoDay } from "../components/ui";

const MARKETS = [{ id: "shots", label: "Shots", q: { stat: "shots", scope: "player" } }, { id: "sot", label: "On target", q: { stat: "sot" } },
  { id: "tackles", label: "Tackles", q: { stat: "tackles" } }, { id: "corners", label: "Corners", q: { stat: "corners" } },
  { id: "team_shots", label: "Team shots", q: { stat: "shots", scope: "team" } }, { id: "cards", label: "Cards", q: { stat: "yellow_cards" } }];
const TIERS = ["Strong", "Solid", "Watch"];
const POS = [{ id: "G", label: "GK" }, { id: "D", label: "DEF" }, { id: "M", label: "MID" }, { id: "F", label: "FWD" }];
const NOF = { min: 50, pos: [], venue: "all", confirmed: false };

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
  const [day, setDay] = useState(sp.get("day") || "");
  const [view, setView] = useState("cards");
  useTitle("Insights");
  const data = useMemo(() => q.data || [], [q.data]);
  const fav = useFavLeagues();
  const gameDays = useGameDays(0, 7);
  const lq = useApi("/leagues");
  const leagues = useMemo(() => favFirst((lq.data?.countries || []).flatMap((c) => c.leagues).map((l) => [l.id, l.name]), fav, ([id]) => id), [lq.data, fav]);
  const pos = (f) => (f.pos || f.player?.pos || "")[0];
  const rows = data.filter((f) => (!day || isoDay(utc(f.kickoff)) === day) && f.p * 100 >= more.min
    && (!more.pos.length || more.pos.includes(pos(f))) && (more.venue === "all" || (f.team_iid === f.home_iid) === (more.venue === "home"))
    && (!more.confirmed || f.lineup_confirmed));
  const nMore = more.pos.length + (more.venue !== "all") + more.confirmed + (lg.length > 0);
  const nAll = nMore + (more.min > 50) + tier.length + (mk ? 1 : 0);
  const clearAll = () => { setDay(""); setLg([]); setMk(""); setTier([]); setMore(NOF); };
  const sortWord = { edge: "biggest change first", likely: "most likely first", kickoff: "by kick-off" }[sort];
  const cap = entitlements?.insights_per_day;
  return (
    <section className="ins" data-testid="insights-page">
      <h1>Insights</h1>
      {q.data && <p className="ins-answer" data-testid="ins-answer"><b>{rows.length} forecast{rows.length === 1 ? "" : "s"}</b> · {sortWord}</p>}
      <div className="ins-days"><button type="button" className={`k-chip${!day ? " on" : ""}`} onClick={() => setDay("")} aria-pressed={!day} data-testid="ins-any-day">Any day</button>
        <DateScroller value={day} onChange={setDay} from={0} count={7} gameDays={gameDays} testid="ins-dates" /></div>
      <section className="ins-filters card" aria-label="Filters" data-testid="ins-filters-panel">
        <div className="ins-f ins-f--min"><span className="ins-f-label">At least <b data-testid="ins-min-value">{more.min}%</b> likely</span>
          <RangeSlider min={50} max={95} step={5} value={more.min} onChange={(v) => setMore({ ...more, min: v })} label="Minimum likelihood" format={(v) => `${v}%`} testid="ins-min" /></div>
        <div className="ins-f"><span className="ins-f-label">Tier</span>
          <ChipsRow multi value={tier} onChange={setTier} label="Tier" testid="ins-tier" options={TIERS.map((t) => ({ id: t, label: t }))} /></div>
        <div className="ins-f"><span className="ins-f-label">Market</span>
          <ChipsRow value={mk || "all"} onChange={(v) => setMk(v === "all" || v === mk ? "" : v)} label="Market" testid="ins-market" options={[{ id: "all", label: "All" }, ...MARKETS.map(({ id, label }) => ({ id, label }))]} /></div>
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
        : view === "list" ? <Compact rows={rows} /> : <div className="fgrid ins-grid">{rows.map((f) => <ForecastCard key={f.id} f={f} testid={`ins-card-${f.id}`} />)}</div>}
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
