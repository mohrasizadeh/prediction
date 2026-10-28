// You (docs/24 §11 and §13): one feed for everything you follow, saved forecasts with a plain hit or miss,
// notes, and the follow list. Search is the full-screen overlay.
import { useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { del } from "../lib/api";
import { useApi } from "../lib/useApi";
import { useAuth } from "../lib/auth";
import { pct } from "../lib/copy";
import { utc } from "../lib/time";
import { Crest, LeagueMark, PlayerAvatar } from "../components/Media";
import { Tabs, useToast } from "../components/Ui";
import SearchOverlay from "../components/SearchOverlay";
import { ForecastCard } from "../components/ui/ForecastCard";
import { EmptyState, ErrorState, Skeleton, TierBadge } from "../components/ui";
import { useTitle } from "../components/Football";

const Pic = ({ i, size = 32 }) => (i.kind === "player" ? <PlayerAvatar player={i} size={size} /> : i.kind === "team" || i.kind === "match" ? <Crest team={i} size={size} /> : <LeagueMark league={i} size={size} />);
const DAY = 86400000;
const dayKey = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
function dayLabel(t) {
  const diff = Math.round((t - dayKey(new Date())) / DAY);
  return diff === 0 ? "Today" : diff === 1 ? "Tomorrow" : diff === -1 ? "Yesterday" : new Date(t).toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "short" });
}
const hhmm = (s) => utc(s).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
function inTime(s) {
  const m = Math.round((utc(s) - Date.now()) / 60000);
  return m < 0 ? null : m < 60 ? `in ${m} min` : m < 24 * 60 ? `in ${Math.round(m / 60)}h` : null;
}
const subjectOf = (f) => f.player?.name || f.team?.name || "";

function Outcome({ o }) {
  if (!o) return null;
  if (o.player_played === false) return <span className="y-tag" data-testid="outcome-dnp">Did not play</span>;
  return o.reached ? <span className="y-tag y-tag--hit" data-testid="outcome-hit">Hit</span> : <span className="y-tag y-tag--miss" data-testid="outcome-miss">Miss</span>;
}

function FeedItem({ it }) {
  if (it.type === "match") {
    const m = it.m;
    return (
      <Link to={`/match/${m.id}`} className="y-item" data-testid={`feed-match-${m.id}`}>
        <span className="y-item-k">Match · {hhmm(m.kickoff)}{inTime(m.kickoff) && <i>{inTime(m.kickoff)}</i>}</span>
        <span className="y-vs"><Crest team={m.home} size={24} /><b>{m.home?.name} vs {m.away?.name}</b><Crest team={m.away} size={24} /></span>
      </Link>
    );
  }
  if (it.type === "result") {
    const m = it.m;
    return <Link to={`/match/${m.id}`} className="y-item y-item--row" data-testid={`feed-result-${m.id}`}><span className="y-tag">FT</span><span>{m.home?.name} <b>{m.hg}–{m.ag}</b> {m.away?.name}</span></Link>;
  }
  if (it.type === "lineup") {
    const x = it.x;
    return (
      <Link to={`/match/${x.match_id}`} className="y-item y-item--row" data-testid={`feed-lineup-${x.match_id}-${x.player.id}`}>
        <PlayerAvatar player={x.player} size={40} /><span><b>{x.player.name}</b> {x.started ? "starts" : "is not in the starting eleven"}</span><span className={`y-tag${x.started ? " y-tag--hit" : ""}`}>Lineup</span>
      </Link>
    );
  }
  const f = it.f;
  if (it.type === "saved") {
    return (
      <Link to={f.match_id ? `/match/${f.match_id}` : "#"} className="y-item y-item--row" data-testid={`feed-saved-${f.fkey}`}>
        <Outcome o={it.o} /><span>Your saved: <b>{subjectOf(f)} {f.market}</b> ({pct(f.p)}).{it.o?.player_played !== false && it.o?.actual != null ? ` Final count: ${it.o.actual}.` : ""}</span>
      </Link>
    );
  }
  return (
    <Link to={f.match_id ? `/match/${f.match_id}` : "#"} className="y-item y-item--row" data-testid={`feed-forecast-${f.fkey || f.id}`}>
      {f.player ? <PlayerAvatar player={f.player} size={40} /> : <Crest team={f.team} size={36} />}
      <span><b>{subjectOf(f)}</b> · {f.p_prev != null ? <>forecast {f.p > f.p_prev ? "rose" : "fell"} from {pct(f.p_prev)} to <b>{pct(f.p)}</b>: {f.market}</> : <>forecast: {f.market}, <b>{pct(f.p)}</b></>}</span><TierBadge tier={f.tier} testid={`feed-tier-${f.fkey || f.id}`} />
    </Link>
  );
}

function buildFeed(feed, saved) {
  const items = [
    ...feed.matches.map((m) => ({ type: "match", at: m.kickoff, ids: [m.home?.id, m.away?.id], key: `m${m.id}`, m })),
    ...(feed.results || []).map((m) => ({ type: "result", at: m.kickoff, ids: [m.home?.id, m.away?.id], key: `r${m.id}`, m })),
    ...(feed.lineups || []).map((x) => ({ type: "lineup", at: x.kickoff, ids: [x.player.id], key: `l${x.match_id}${x.player.id}`, x })),
    ...feed.forecasts.slice(0, 12).map((f) => ({ type: "forecast", at: f.kickoff, ids: [f.team?.id, f.player?.id], key: `f${f.id}`, f })),
    ...saved.filter((r) => r.outcome && r.forecast).map((r) => ({ type: "saved", at: r.forecast.kickoff, ids: [r.forecast.team?.id, r.forecast.player?.id], key: `s${r.fkey}`, f: r.forecast, o: r.outcome })),
  ];
  const now = Date.now();
  const up = items.filter((i) => utc(i.at) >= now).sort((a, b) => utc(a.at) - utc(b.at));
  const past = items.filter((i) => utc(i.at) < now).sort((a, b) => utc(b.at) - utc(a.at));
  return [...up, ...past];
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
          <span className="book-rank">{f.rank}</span><PlayerAvatar player={f.player} size={36} />
          <span className="book-who"><Link to={`/player/${f.player?.id}`}><b>{f.player?.name}</b></Link><small className="muted">{f.home_iid === f.team_iid ? "v" : "at"} <Link to={`/match/${f.match_id}`}>{f.opp?.name}</Link></small></span>
          <span className="book-p"><b>{Math.round(f.p * 100)}%</b><span className="book-bar"><i style={{ width: `${Math.round(f.p * 100)}%` }} /></span></span>
        </li>
      ))}</ol>
    </section>
  );
}

function Feed({ follows, saved }) {
  const q = useApi("/me/following-feed");
  const [pick, setPick] = useState("all");
  const all = useMemo(() => (q.data ? buildFeed(q.data, saved) : []), [q.data, saved]);
  if (q.loading && !q.data) return <Skeleton shape="row" count={5} testid="feed-loading" />;
  if (q.error) return <ErrorState message="We could not load your feed." onRetry={q.reload} testid="feed-error" />;
  const teamOf = (q.data?.forecasts || []).find((f) => f.player?.id === pick)?.team?.id;
  const rows = pick === "all" ? all : all.filter((i) => i.ids.includes(pick) || (teamOf && i.type !== "forecast" && i.ids.includes(teamOf)));
  let last = null;
  return (
    <>
      {follows.length > 0 && (
        <div className="y-filter" role="toolbar" aria-label="Filter the feed" data-testid="feed-filter">
          <button type="button" className={`y-dot${pick === "all" ? " on" : ""}`} aria-pressed={pick === "all"} onClick={() => setPick("all")} data-testid="feed-filter-all"><span className="y-all">All</span></button>
          {follows.filter((i) => i.kind !== "league" && i.kind !== "match").map((i) => (
            <button key={`${i.kind}-${i.id}`} type="button" className={`y-dot${pick === i.id ? " on" : ""}`} aria-pressed={pick === i.id} aria-label={i.name} title={i.name} onClick={() => setPick(i.id)} data-testid={`feed-filter-${i.id}`}><Pic i={i} size={48} /></button>
          ))}
        </div>
      )}
      <BookingRisk />
      {!rows.length ? <EmptyState icon="calendar" title="Nothing here yet" testid="feed-empty">{follows.length ? "No matches, forecasts or results for this pick in the coming days." : <>Follow a few teams and players and their matches fill this feed. <Link to="/explore">Explore</Link></>}</EmptyState> : (
        <div className="y-feed" data-testid="feed-list">{rows.map((it) => {
          const d = dayKey(utc(it.at));
          const head = d !== last ? <h2 className="k-sec" key={`h${d}`}>{dayLabel(d)}</h2> : null;
          last = d;
          return [head, <FeedItem key={it.key} it={it} />];
        })}</div>
      )}
    </>
  );
}

function Saved({ q }) {
  const toast = useToast();
  const drop = async (fkey) => { try { await del("/me/saved", { fkey }); toast("Removed"); q.reload(); } catch (x) { toast(x.message, "err"); } };
  if (q.loading && !q.data) return <Skeleton shape="card" count={3} testid="saved-loading" />;
  if (q.error) return <ErrorState message="We could not load your saved forecasts." onRetry={q.reload} testid="saved-error" />;
  if (!q.data.items.length) return <EmptyState icon="star" title="No saved forecasts" testid="saved-empty">Press the star on any forecast to keep it here. Once the match is played, it says hit or miss.</EmptyState>;
  return (
    <div className="fgrid" data-testid="saved-list">{q.data.items.map((r) => (
      <div key={r.fkey} className="saved-item">
        {r.outcome && <p className="y-out"><Outcome o={r.outcome} />{r.outcome.player_played !== false && r.outcome.actual != null && <span className="k-faint">Final count: {r.outcome.actual}</span>}</p>}
        {r.forecast ? <ForecastCard f={r.forecast} testid={`saved-card-${r.fkey}`} /> : <p className="card muted">This forecast is finished or replaced.</p>}
        <button type="button" className="btn btn--ghost btn--sm" onClick={() => drop(r.fkey)} data-testid={`unsave-${r.fkey}`}>Remove</button></div>
    ))}</div>
  );
}

function Notes({ q }) {
  if (q.loading && !q.data) return <Skeleton shape="row" count={3} testid="notes-loading" />;
  if (q.error) return <ErrorState message="We could not load your notes." onRetry={q.reload} testid="notes-error" />;
  if (!q.data.items.length) return <EmptyState icon="edit" title="No notes yet" testid="notes-empty">Open a player page and press Add note.</EmptyState>;
  return (
    <ul className="y-notes" data-testid="notes-list">{q.data.items.map((n) => (
      <li key={n.player.id}><Link to={`/player/${n.player.id}`} className="y-item y-item--row" data-testid={`note-${n.player.id}`}><PlayerAvatar player={n.player} size={40} />
        <span><b>{n.player.name}</b><small className="k-faint"> · {utc(n.updated_at).toLocaleDateString(undefined, { day: "numeric", month: "short" })}</small><span className="y-note">{n.text}</span></span></Link></li>
    ))}</ul>
  );
}

function Follows({ q }) {
  const toast = useToast();
  const drop = async (i) => { try { await del("/me/follows", { kind: i.kind, ref_id: i.id }); toast(`Stopped following ${i.name}`); q.reload(); window.dispatchEvent(new Event("follows-change")); } catch (x) { toast(x.message, "err"); } };
  if (q.loading && !q.data) return <Skeleton shape="row" count={3} testid="follows-loading" />;
  if (q.error) return <ErrorState message="We could not load who you follow." onRetry={q.reload} testid="follows-error" />;
  if (!q.data.items.length) return <EmptyState icon="star" title="You follow nobody yet" testid="follows-empty">Open a team or player page and press Follow.</EmptyState>;
  return (
    <ul className="rows" data-testid="follows-list">{q.data.items.map((i) => (
      <li key={`${i.kind}-${i.id}`} className="row-card"><Pic i={i} /><Link to={i.kind === "match" ? `/match/${i.id}` : `/${i.kind}/${i.id}`} className="row-main"><b>{i.name}</b><small className="muted"> {i.kind}</small></Link>
        <button type="button" className="btn btn--ghost btn--sm" onClick={() => drop(i)} data-testid={`unfollow-${i.id}`}>Unfollow</button></li>
    ))}{q.data.limit >= 0 && <li className="muted small">{q.data.items.length} of {q.data.limit} on your plan.</li>}</ul>
  );
}

function You() {
  const [tab, setTab] = useState("feed");
  const follows = useApi("/me/follows");
  const saved = useApi("/me/saved");
  const notes = useApi("/me/notes");
  const n = (q) => (q.data?.items?.length ? ` ${q.data.items.length}` : "");
  return (
    <>
      <Tabs value={tab} onChange={setTab} testid="following-tabs" tabs={[{ id: "feed", label: "Feed" }, { id: "saved", label: `Saved${n(saved)}` }, { id: "notes", label: `Notes${n(notes)}` }, { id: "follows", label: `Follows${n(follows)}` }]} />
      <div className="y-body">
        {tab === "feed" ? <Feed follows={follows.data?.items || []} saved={saved.data?.items || []} /> : tab === "saved" ? <Saved q={saved} /> : tab === "notes" ? <Notes q={notes} /> : <Follows q={follows} />}
      </div>
    </>
  );
}

export function Following() {
  const { user, loading } = useAuth();
  useTitle("You");
  return (
    <section className="y" data-testid="following-page">
      <div className="y-head"><h1>You</h1>{user && <Link to="/account" className="k-link" data-testid="following-account">Account</Link>}</div>
      {loading ? <Skeleton shape="row" count={4} testid="following-loading" /> : !user ? (
        <EmptyState icon="star" title="Your teams and players in one feed" testid="following-signin" action={<div className="btn-row"><Link to="/sign-up" className="btn btn--primary" data-testid="following-signup">Create a free account</Link><Link to="/sign-in?next=/following" className="btn btn--secondary" data-testid="following-signin-link">Sign in</Link></div>}>
          Follow clubs and players, keep forecasts and see how they turned out.
        </EmptyState>
      ) : <You />}
    </section>
  );
}

export function Search() {
  const [sp] = useSearchParams();
  const nav = useNavigate();
  useTitle("Search");
  return <section data-testid="search-page"><SearchOverlay open initial={sp.get("q") || ""} onClose={(going) => { if (!going) nav(window.history.length > 1 ? -1 : "/"); }} /></section>;
}
