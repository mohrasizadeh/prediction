// Insights: strongest forecasts across leagues (docs/24 §4).
import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useApi } from "../lib/useApi";
import { pct } from "../lib/copy";
import { useAuth } from "../lib/auth";
import { utc } from "../lib/time";
import { favFirst, useFavLeagues, useGameDays } from "../lib/prefs";
import { useTitle } from "../components/Football";
import { ChipsRow, DateScroller, EmptyState, ErrorState, FilterGroup, FilterSheet, ForecastCard, ProLock, RangeSlider, Segmented, Skeleton, TierBadge, isoDay } from "../components/ui";

const MARKETS = [{ id: "shots", label: "Shots", test: (f) => f.stat === "shots" && f.scope === "player" }, { id: "sot", label: "On target", test: (f) => f.stat === "sot" },
  { id: "tackles", label: "Tackles", test: (f) => f.stat === "tackles" }, { id: "corners", label: "Corners", test: (f) => f.stat === "corners" },
  { id: "team_shots", label: "Team shots", test: (f) => f.stat === "shots" && f.scope === "team" }, { id: "cards", label: "Cards", test: (f) => /yellow/.test(f.stat || "") }];
const TIERS = ["Strong", "Solid", "Watch"];
const POS = [{ id: "G", label: "GK" }, { id: "D", label: "DEF" }, { id: "M", label: "MID" }, { id: "F", label: "FWD" }];
const NOF = { min: 50, pos: [], venue: "all", confirmed: false };
const rise = (f) => (f.usual_p != null ? f.p - f.usual_p : -1);
const SORTS = { likely: (a, b) => b.p - a.p, rise: (a, b) => rise(b) - rise(a), time: (a, b) => utc(a.kickoff) - utc(b.kickoff) };

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
  const q = useApi("/insights", { limit: 200 });
  const [day, setDay] = useState(sp.get("day") || "");
  const [lg, setLg] = useState([]);
  const [mk, setMk] = useState([]);
  const [tier, setTier] = useState([]);
  const [more, setMore] = useState(NOF);
  const [sheet, setSheet] = useState(false);
  const [sort, setSort] = useState("likely");
  const [view, setView] = useState("cards");
  useTitle("Insights");
  const data = useMemo(() => q.data || [], [q.data]);
  const fav = useFavLeagues();
  const gameDays = useGameDays(0, 7);
  const leagues = useMemo(() => { const idOf = Object.fromEntries(data.map((f) => [f.league_iid, f.league_id])); return favFirst([...new Map(data.map((f) => [f.league_iid, f.league_name || f.league?.name])).entries()], fav, ([iid]) => idOf[iid]); }, [data, fav]);
  const pos = (f) => (f.pos || f.player?.pos || "")[0];
  const rows = data.filter((f) => (!day || isoDay(utc(f.kickoff)) === day) && (!lg.length || lg.includes(f.league_iid))
    && (!mk.length || MARKETS.some((m) => mk.includes(m.id) && m.test(f))) && (!tier.length || tier.includes(f.tier)) && f.p * 100 >= more.min
    && (!more.pos.length || more.pos.includes(pos(f))) && (more.venue === "all" || (f.team_iid === f.home_iid) === (more.venue === "home"))
    && (!more.confirmed || f.lineup_confirmed)).sort(SORTS[sort]);
  const nMore = (more.min > 50) + more.pos.length + (more.venue !== "all") + more.confirmed;
  const cap = entitlements?.insights_per_day;
  return (
    <section className="ins" data-testid="insights-page">
      <h1>Insights</h1>
      <div className="ins-days"><button type="button" className={`k-chip${!day ? " on" : ""}`} onClick={() => setDay("")} aria-pressed={!day} data-testid="ins-any-day">Any day</button>
        <DateScroller value={day} onChange={setDay} from={0} count={7} gameDays={gameDays} testid="ins-dates" /></div>
      <div className="ins-chips">
        <ChipsRow multi value={tier} onChange={setTier} label="Tier" testid="ins-tier" options={TIERS.map((t) => ({ id: t, label: t }))} />
        <ChipsRow multi value={mk} onChange={setMk} label="Market" testid="ins-market" options={MARKETS.map(({ id, label }) => ({ id, label }))} />
        {leagues.filter(([, n]) => n).length > 1 && <ChipsRow multi value={lg} onChange={setLg} label="League" testid="ins-league" options={leagues.filter(([, n]) => n).map(([id, name]) => ({ id, label: name }))} />}
        <ChipsRow label="More" testid="ins-more" options={[{ id: "more", label: "More filters", count: nMore || null, accent: true, onClick: () => setSheet(true) }]} />
      </div>
      <div className="ins-bar">
        <Segmented label="Sort" value={sort} onChange={setSort} testid="ins-sort" options={[{ id: "likely", label: "Most likely" }, { id: "rise", label: "Rise vs usual" }, { id: "time", label: "Kick-off" }]} />
        <Segmented label="View" value={view} onChange={setView} testid="ins-view" options={[{ id: "cards", label: "Cards" }, { id: "list", label: "List" }]} />
      </div>
      {q.loading && !q.data ? <Skeleton shape="card" count={6} testid="ins-loading" /> : q.error && !q.data ? <ErrorState message="We could not load the insights." onRetry={q.reload} testid="ins-error" />
        : !rows.length ? <EmptyState icon="sparkles" title="No forecasts match" testid="ins-empty" action={<button type="button" className="btn btn--secondary btn--sm" onClick={() => { setDay(""); setLg([]); setMk([]); setTier([]); setMore(NOF); }} data-testid="ins-clear">Clear all filters</button>}>Try another day, market or tier.</EmptyState>
        : view === "list" ? <Compact rows={rows} /> : <div className="fgrid ins-grid">{rows.map((f) => <ForecastCard key={f.id} f={f} testid={`ins-card-${f.id}`} />)}</div>}
      {cap >= 0 && data.length >= cap && <p className="notice small" data-testid="ins-capped">Your plan shows {cap} insights a day. <ProLock label="Unlimited with Pro" testid="ins-capped-pro" /></p>}
      <FilterSheet open={sheet} onClose={() => setSheet(false)} onReset={() => setMore(NOF)} count={rows.length} testid="ins-filters">
        <FilterGroup label="Minimum likelihood"><RangeSlider min={50} max={95} step={5} value={more.min} onChange={(v) => setMore({ ...more, min: v })} label="Minimum likelihood" format={(v) => `${v}%`} testid="ins-min" /></FilterGroup>
        <FilterGroup label="Position"><ChipsRow multi value={more.pos} onChange={(v) => setMore({ ...more, pos: v })} label="Position" options={POS} testid="ins-pos" /></FilterGroup>
        <FilterGroup label="Venue"><Segmented value={more.venue} onChange={(v) => setMore({ ...more, venue: v })} label="Venue" options={[{ id: "all", label: "All" }, { id: "home", label: "Home" }, { id: "away", label: "Away" }]} testid="ins-venue" /></FilterGroup>
        <label className="ins-switch"><input type="checkbox" checked={more.confirmed} onChange={(e) => setMore({ ...more, confirmed: e.target.checked })} data-testid="ins-confirmed" /><span>Lineup confirmed only</span></label>
      </FilterSheet>
    </section>
  );
}
