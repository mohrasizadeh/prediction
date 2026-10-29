// Explore (docs/24 §6): your clubs first, then league tiles that say what is next, then the tools.
// Typing filters the tiles; players and teams open in the full search.
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useApi } from "../lib/useApi";
import { useAuth } from "../lib/auth";
import { utc } from "../lib/time";
import Icon from "../components/Icon";
import { Crest, LeagueMark } from "../components/Media";
import { useTitle } from "../components/Football";
import { EmptyState, ErrorState, Skeleton } from "../components/ui";

const TOOLS = [
  { to: "/compare", icon: "users", label: "Compare two teams" }, { to: "/track-record", icon: "trending-up", label: "Track record" },
  { to: "/learn", icon: "book", label: "Learn" }, { to: "/referees", icon: "flag", label: "Referees" },
  { to: "/live", icon: "clock", label: "Live scores" }, { to: "/pricing", icon: "credit-card", label: "Plans" },
];
const norm = (s) => (s || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();

function nextLabel(l) {
  if (!l.next) return l.current_season || "No fixtures scheduled";
  return l.today ? `${l.today} today` : utc(l.next.kickoff).toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" });
}

function YourTeams() {
  const { user } = useAuth();
  const q = useApi(user ? "/me/follows" : null);
  const teams = (q.data?.items || []).filter((i) => i.kind === "team");
  if (!user) return null;
  return (
    <section className="ex-sec" data-testid="explore-your-teams">
      <h2 className="k-sec">Your teams</h2>
      {q.error ? <ErrorState message="We could not load your teams." onRetry={q.reload} testid="explore-teams-error" /> : (
        <div className="ex-crests">
          {teams.map((t) => <Link key={t.id} to={`/team/${t.id}`} className="ex-crest" data-testid={`explore-team-${t.id}`}><Crest team={t} size={56} /><span>{t.name}</span></Link>)}
          <Link to="/teams" className="ex-crest ex-crest--add" data-testid="explore-team-add"><span className="ex-add"><Icon name="plus" size={22} /></span><span>Add</span></Link>
        </div>
      )}
    </section>
  );
}

export default function Explore() {
  const { user } = useAuth();
  const [q, setQ] = useState("");
  const r = useApi("/leagues");
  useTitle("Explore");
  const fav = user?.prefs?.leagues;
  const leagues = useMemo(() => (r.data?.countries || []).flatMap((c) => c.leagues.map((l) => ({ ...l, country: l.country || c.country })))
    .sort((a, b) => ((fav || []).includes(b.id) - (fav || []).includes(a.id))), [r.data, fav]);
  const shown = leagues.filter((l) => !q.trim() || norm(`${l.name} ${l.country}`).includes(norm(q.trim())));
  return (
    <section className="ex" data-testid="explore-page">
      <h1>Explore</h1>
      <label className="ex-search"><Icon name="search" size={18} /><span className="sr-only">Find a league</span>
        <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Find a league, team or player" data-testid="explore-search" /></label>
      {!q.trim() && <YourTeams />}
      <section className="ex-sec"><h2 className="k-sec">Leagues</h2>
        {r.loading && !r.data ? <Skeleton shape="card" count={4} testid="explore-loading" />
          : r.error ? <ErrorState message="We could not load the leagues." onRetry={r.reload} testid="explore-error" />
          : !shown.length ? <EmptyState icon="trophy" title={`No league matches “${q.trim()}”`} testid="explore-empty">Looking for a club or a player? <Link to={`/search?q=${encodeURIComponent(q.trim())}`} data-testid="explore-search-all">Search everything</Link></EmptyState>
          : <ul className="ex-grid" data-testid="explore-leagues">{shown.map((l) => (
            <li key={l.id}><Link to={`/league/${l.id}`} className="ex-lg" data-testid={`explore-league-${l.id}`}>
              <span className="ex-lg-top"><LeagueMark league={l} size={40} />{l.country && l.country !== "Other" && <small>{l.country}</small>}</span>
              <b>{l.name}</b><small className="k-faint">{nextLabel(l)}</small></Link></li>
          ))}</ul>}
        {q.trim().length >= 2 && shown.length > 0 && <Link to={`/search?q=${encodeURIComponent(q.trim())}`} className="k-link" data-testid="explore-search-more">Search players and teams for “{q.trim()}”</Link>}
      </section>
      <section className="ex-sec"><h2 className="k-sec">Tools</h2>
        <ul className="ex-tools card">{TOOLS.map((t) => (
          <li key={t.to}><Link to={t.to} data-testid={`explore-${t.to.slice(1)}`}><Icon name={t.icon} size={18} /><span>{t.label}</span><Icon name="chevron-right" size={18} /></Link></li>
        ))}</ul>
      </section>
    </section>
  );
}
