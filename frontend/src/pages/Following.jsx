// Screens 10 and 13: Following (follows, saved forecasts, upcoming fixtures for followed teams) and Search.
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { del, get } from "../lib/api";
import { useApi } from "../lib/useApi";
import { useAuth } from "../lib/auth";
import { Crest, LeagueMark, PlayerAvatar } from "../components/Media";
import { Empty, ErrorBox, Loading } from "../components/States";
import { Tabs, useToast } from "../components/Ui";
import { ForecastCard, MatchRow, posLabel, useTitle } from "../components/Football";

const PATH = { team: "team", player: "player", league: "league" };
const Pic = ({ i, size = 32 }) => (i.kind === "player" ? <PlayerAvatar player={i} size={size} /> : i.kind === "team" ? <Crest team={i} size={size} /> : <LeagueMark league={i} size={size} />);

function Follows() {
  const q = useApi("/me/follows");
  const toast = useToast();
  const drop = async (i) => { try { await del("/me/follows", { kind: i.kind, ref_id: i.id }); toast(`Stopped following ${i.name}`); q.reload(); } catch (x) { toast(x.message, "err"); } };
  if (q.loading && !q.data) return <Loading />;
  if (q.error) return <ErrorBox error={q.error} onRetry={q.reload} />;
  if (!q.data.items.length) return <Empty icon="star">You follow nobody yet. Open a team or player page and press Follow.</Empty>;
  return (
    <ul className="rows" data-testid="follows-list">{q.data.items.map((i) => (
      <li key={`${i.kind}-${i.id}`} className="row-card"><Pic i={i} /><Link to={`/${PATH[i.kind]}/${i.id}`} className="row-main"><b>{i.name}</b><small className="muted"> {i.kind}</small></Link>
        <button type="button" className="btn btn--ghost btn--sm" onClick={() => drop(i)} data-testid={`unfollow-${i.id}`}>Unfollow</button></li>
    ))}{q.data.limit >= 0 && <li className="muted small">{q.data.items.length} of {q.data.limit} on your plan.</li>}</ul>
  );
}

function BookingRisk() {
  const q = useApi("/me/booking-risk");
  if (!q.data?.rows?.length) return null;
  return (
    <section className="card book-alert" data-testid="following-booking-risk">
      <h2 className="h3">May be booked this round</h2>
      <p className="muted small">Players you follow who are in their league's top 10 for a yellow card. We e-mail you once per match unless you turn off alert e-mails in your account.</p>
      <ol className="book-list">{q.data.rows.map((f) => (
        <li key={f.id} className="book-row" data-testid={`following-booking-${f.player_iid}`}>
          <span className="book-rank">{f.rank}</span>
          <PlayerAvatar player={f.player} size={36} />
          <span className="book-who"><Link to={`/player/${f.player?.id}`}><b>{f.player?.name}</b></Link><small className="muted">{f.home_iid === f.team_iid ? "v" : "at"} <Link to={`/match/${f.match_id}`}>{f.opp?.name}</Link></small></span>
          <span className="book-p"><b>{Math.round(f.p * 100)}%</b><span className="book-bar"><i style={{ width: `${Math.round(f.p * 100)}%` }} /></span></span>
        </li>
      ))}</ol>
    </section>
  );
}

function Feed() {
  const q = useApi("/me/following-feed");
  if (q.loading && !q.data) return <Loading />;
  if (q.error) return <ErrorBox error={q.error} onRetry={q.reload} />;
  const { matches, forecasts } = q.data;
  if (!matches.length) return <Empty icon="calendar">No upcoming matches for what you follow.</Empty>;
  return (
    <>
      <BookingRisk />
      <ul className="mlist card" data-testid="feed-matches">{matches.map((m) => <MatchRow key={m.id} m={m} />)}</ul>
      {forecasts.length > 0 && <><h2 className="h3">Forecasts</h2><div className="fgrid">{forecasts.slice(0, 24).map((f) => <ForecastCard key={f.id} f={f} showMatch />)}</div></>}
    </>
  );
}

function Saved() {
  const q = useApi("/me/saved");
  const toast = useToast();
  const drop = async (fkey) => { try { await del("/me/saved", { fkey }); toast("Removed"); q.reload(); } catch (x) { toast(x.message, "err"); } };
  if (q.loading && !q.data) return <Loading />;
  if (q.error) return <ErrorBox error={q.error} onRetry={q.reload} />;
  if (!q.data.items.length) return <Empty icon="star">No saved forecasts. Press the star on any forecast to keep it here.</Empty>;
  return (
    <div className="fgrid" data-testid="saved-list">{q.data.items.map((r) => (
      <div key={r.fkey} className="saved-item">{r.forecast ? <ForecastCard f={r.forecast} showMatch /> : <p className="card muted">This forecast is finished or replaced.</p>}
        <button type="button" className="btn btn--ghost btn--sm" onClick={() => drop(r.fkey)} data-testid={`unsave-${r.fkey}`}>Remove</button></div>
    ))}</div>
  );
}

export function Following() {
  const { user, loading } = useAuth();
  const [tab, setTab] = useState("feed");
  useTitle("Following");
  if (loading) return <Loading />;
  if (!user) return <section data-testid="following-page"><h1>Following</h1><Empty icon="star" testid="following-signin">Sign in to follow teams and players and keep forecasts. <Link to="/sign-in?next=/following">Sign in</Link></Empty></section>;
  return (
    <section data-testid="following-page">
      <h1>Following</h1>
      <Tabs value={tab} onChange={setTab} testid="following-tabs" tabs={[{ id: "feed", label: "Upcoming" }, { id: "follows", label: "Follows" }, { id: "saved", label: "Saved" }]} />
      {tab === "feed" ? <Feed /> : tab === "follows" ? <Follows /> : <Saved />}
    </section>
  );
}

export function Search() {
  const [q, setQ] = useState("");
  const [st, setSt] = useState({ data: null, error: null, loading: false });
  useTitle("Search");
  useEffect(() => {
    const t = q.trim();
    if (t.length < 2) { setSt({ data: null, error: null, loading: false }); return undefined; }
    const ac = new AbortController();
    const h = setTimeout(() => {
      setSt((s) => ({ ...s, loading: true }));
      get("/search", { q: t }, { signal: ac.signal }).then((data) => setSt({ data, error: null, loading: false })).catch((error) => error.name !== "AbortError" && setSt({ data: null, error, loading: false }));
    }, 200);
    return () => { clearTimeout(h); ac.abort(); };
  }, [q]);
  const d = st.data;
  return (
    <section data-testid="search-page">
      <h1>Search</h1>
      <input className="search-in" type="search" autoFocus placeholder="Team or player" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search teams and players" data-testid="search-input" />
      {q.trim().length < 2 ? <p className="muted">Type at least 2 letters.</p> : st.loading && !d ? <Loading rows={2} /> : st.error ? <ErrorBox error={st.error} /> : d && !d.teams.length && !d.players.length ? <Empty icon="search">No team or player matches “{q}”.</Empty> : d && (
        <div className="split2">
          {d.teams.length > 0 && <div className="card"><h2 className="h3">Teams</h2><ul className="llist" data-testid="search-teams">{d.teams.map((t) => <li key={t.id}><Link to={`/team/${t.id}`} className="lrow"><Crest team={t} size={28} /><b>{t.name}</b></Link></li>)}</ul></div>}
          {d.players.length > 0 && <div className="card"><h2 className="h3">Players</h2><ul className="llist" data-testid="search-players">{d.players.map((p) => <li key={p.id}><Link to={`/player/${p.id}`} className="lrow"><PlayerAvatar player={p} size={28} /><span><b>{p.name}</b><small className="muted">{posLabel(p.pos)}</small></span></Link></li>)}</ul></div>}
        </div>
      )}
    </section>
  );
}
