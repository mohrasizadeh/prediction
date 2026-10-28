// Full-screen search (docs/24 §13): recent searches and followed items before typing, then results grouped as
// Players, Teams, Leagues with photos or crests and the matched letters marked. Arrow keys + Enter on desktop.
// Typo-tolerant: when the exact text finds nothing, it retries with the first letters and ranks by closeness.
import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";
import { get } from "../lib/api";
import { useAuth } from "../lib/auth";
import { Crest, LeagueMark, PlayerAvatar } from "./Media";
import { posLabel } from "./Football";
import Icon from "./Icon";
import { EmptyState, ErrorState, Skeleton } from "./ui";
import { favFirst, useFavLeagues } from "../lib/prefs";

const KEY = "recent-searches";
const recent = () => { try { return JSON.parse(localStorage.getItem(KEY)) || []; } catch { return []; } };
const remember = (t) => localStorage.setItem(KEY, JSON.stringify([t, ...recent().filter((x) => x !== t)].slice(0, 6)));
const norm = (s) => (s || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();

function dist(a, b) {
  const m = [...Array(b.length + 1).keys()];
  for (let i = 1; i <= a.length; i++) {
    let prev = m[0]; m[0] = i;
    for (let j = 1; j <= b.length; j++) { const t = m[j]; m[j] = Math.min(m[j] + 1, m[j - 1] + 1, prev + (a[i - 1] === b[j - 1] ? 0 : 1)); prev = t; }
  }
  return m[b.length];
}
const close = (q, name) => Math.min(...norm(name).split(/[\s,.-]+/).map((w) => dist(norm(q), w.slice(0, q.length + 1))));

function Mark({ text, q }) {
  const i = norm(text).indexOf(norm(q));
  if (!q || i < 0) return text;
  return <>{text.slice(0, i)}<mark>{text.slice(i, i + q.length)}</mark>{text.slice(i + q.length)}</>;
}

async function find(q) {
  const [s, l] = await Promise.all([get("/search", { q }), get("/leagues", { q }).catch(() => [])]);
  const leagues = (Array.isArray(l) ? l : l.leagues || l.items || (l.countries || []).flatMap((c) => (c.leagues || []).map((x) => ({ ...x, country: x.country || c.country }))) || []).slice(0, 5);
  let out = { players: s.players || [], teams: s.teams || [], leagues, fuzzy: false };
  if (!out.players.length && !out.teams.length && !leagues.length && q.length >= 4) {
    const s2 = await get("/search", { q: q.slice(0, 3), limit: 30 }).catch(() => ({}));
    const rank = (rows) => (rows || []).map((r) => [close(q, r.name), r]).filter(([d]) => d <= 2).sort((a, b) => a[0] - b[0]).map(([, r]) => r).slice(0, 6);
    out = { players: rank(s2.players), teams: rank(s2.teams), leagues: [], fuzzy: true };
  }
  return out;
}

function useResults(q) {
  const [st, setSt] = useState({ data: null, error: null, loading: false, n: 0 });
  useEffect(() => {
    const t = q.trim();
    if (t.length < 2) { setSt((s) => ({ ...s, data: null, error: null, loading: false })); return undefined; }
    let stop = false;
    setSt((s) => ({ ...s, loading: true }));
    const h = setTimeout(() => find(t).then((data) => { if (!stop) setSt((s) => ({ ...s, data, error: null, loading: false })); })
      .catch((error) => { if (!stop) setSt((s) => ({ ...s, error, loading: false })); }), 180);
    return () => { stop = true; clearTimeout(h); };
  }, [q, st.n]);
  return { ...st, retry: () => setSt((s) => ({ ...s, n: s.n + 1 })) };
}

export default function SearchOverlay({ open, onClose, initial = "" }) {
  const [q, setQ] = useState("");
  const [sel, setSel] = useState(0);
  const [follows, setFollows] = useState([]);
  const { user } = useAuth();
  const fav = useFavLeagues();
  const nav = useNavigate();
  const input = useRef(null);
  const r = useResults(q);
  useEffect(() => {
    if (!open) return undefined;
    setQ(initial); setSel(0);
    setTimeout(() => input.current?.focus(), 30);
    if (user) get("/me/follows").then((x) => setFollows(x.items || [])).catch(() => {});
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = ""; };
  }, [open, user, initial]);
  const flat = useMemo(() => {
    const d = r.data;
    if (!d) return [];
    return [...d.players.map((p) => ({ kind: "player", to: `/player/${p.id}`, x: p })), ...d.teams.map((t) => ({ kind: "team", to: `/team/${t.id}`, x: t })), ...favFirst(d.leagues, fav, (l) => l.id).map((l) => ({ kind: "league", to: `/league/${l.id}`, x: l }))];
  }, [r.data, fav]);
  if (!open) return null;
  const go = (to) => { if (q.trim()) remember(q.trim()); onClose(true); nav(to); };
  const key = (e) => {
    if (e.key === "Escape") onClose();
    else if (e.key === "ArrowDown") { e.preventDefault(); setSel((s) => Math.min(s + 1, flat.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setSel((s) => Math.max(s - 1, 0)); }
    else if (e.key === "Enter" && flat[sel]) { e.preventDefault(); go(flat[sel].to); }
  };
  const group = (kind, title) => {
    const rows = flat.map((it, i) => ({ ...it, i })).filter((it) => it.kind === kind);
    if (!rows.length) return null;
    return (
      <section className="so-group"><h2 className="k-sec">{title}</h2>
        <ul role="listbox" aria-label={title}>{rows.map(({ x, to, i }) => (
          <li key={x.id} role="option" aria-selected={i === sel}>
            <button type="button" className={`so-row${i === sel ? " on" : ""}`} onMouseEnter={() => setSel(i)} onClick={() => go(to)} data-testid={`search-result-${kind}-${x.id}`}>
              {kind === "player" ? <PlayerAvatar player={x} size={44} /> : kind === "team" ? <Crest team={x} size={40} /> : <LeagueMark league={x} size={36} />}
              <span className="so-txt"><b><Mark text={x.name} q={r.data?.fuzzy ? "" : q.trim()} /></b><small>{kind === "player" ? posLabel(x.pos) : kind === "league" ? (x.country && x.country !== "Other" ? x.country : "League") : "Club"}{r.data?.fuzzy ? " · close match" : ""}</small></span>
              {kind === "player" && x.next && <span className="so-next" title={`Next: ${x.next.market}`} data-testid={`search-next-${x.id}`}><small>Next</small> <b>{Math.round(x.next.p * 100)}%</b></span>}
            </button>
          </li>
        ))}</ul>
      </section>
    );
  };
  const rec = recent();
  return createPortal(
    <div className="so" role="dialog" aria-modal="true" aria-label="Search" onKeyDown={key} data-testid="search-overlay">
      <div className="so-head">
        <label className="so-field"><Icon name="search" size={20} /><span className="sr-only">Search players, teams, leagues</span>
          <input ref={input} type="search" value={q} onChange={(e) => { setQ(e.target.value); setSel(0); }} placeholder="Search players, teams, leagues" autoComplete="off" data-testid="search-overlay-input" /></label>
        <button type="button" className="k-link so-cancel" onClick={() => onClose()} data-testid="search-overlay-cancel">Cancel</button>
      </div>
      <div className="so-body">
        {q.trim().length < 2 ? (
          <>
            {follows.length > 0 && <section className="so-group"><h2 className="k-sec">Following</h2><div className="so-chips">{follows.slice(0, 8).map((f) => (
              <button key={`${f.kind}-${f.id}`} type="button" className="k-chip" onClick={() => go(`/${f.kind}/${f.id}`)} data-testid={`search-follow-${f.id}`}>{f.name}</button>))}</div></section>}
            {rec.length > 0 && <section className="so-group"><h2 className="k-sec">Recent</h2><div className="so-chips">{rec.map((t) => (
              <button key={t} type="button" className="k-chip" onClick={() => setQ(t)} data-testid={`search-recent-${t}`}>{t}</button>))}</div></section>}
            {!follows.length && !rec.length && <p className="muted so-hint">Type at least 2 letters of a player, club or league.</p>}
          </>
        ) : r.loading && !r.data ? <Skeleton shape="row" count={4} testid="search-overlay-loading" />
          : r.error ? <ErrorState message="Search is not answering." onRetry={r.retry} testid="search-overlay-error" />
          : !flat.length ? <EmptyState icon="search" title={`Nothing matches “${q.trim()}”`} testid="search-overlay-empty">Check the spelling, or try the club's or player's last name.</EmptyState>
          : <>{group("player", "Players")}{group("team", "Teams")}{group("league", "Leagues")}</>}
      </div>
    </div>,
    document.body,
  );
}
