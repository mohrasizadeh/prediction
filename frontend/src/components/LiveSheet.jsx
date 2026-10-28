// Live sheet (docs/24 §2): polls our own GET /api/live every 60 s (30 s while open). Live cards first; a score
// change flashes the card once and lifts it to the top for 30 seconds; "Later today" and a collapsed
// "Finished (n)" group below. The full page stays at /live.
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { get } from "../lib/api";
import { utc } from "../lib/time";
import { BottomSheet, EmptyState, LiveCard, Skeleton } from "./ui";
import { isoDay } from "./ui/DateScroller";

export function useLiveNow(fast = false) {
  const [d, setD] = useState(null);
  useEffect(() => {
    let stop = false, t = null;
    const load = () => get("/live", { date: isoDay(new Date()), tz: -new Date().getTimezoneOffset() }).then((r) => { if (!stop) setD(r); }).catch(() => {});
    const loop = () => { if (document.visibilityState === "visible") load(); t = setTimeout(loop, fast ? 30000 : 60000); };
    loop();
    return () => { stop = true; clearTimeout(t); };
  }, [fast]);
  return d;
}

function useFlash(fixtures) {
  const prev = useRef({});
  const [lift, setLift] = useState({});
  useEffect(() => {
    const now = Date.now(), up = {};
    fixtures.forEach((f) => { const s = `${f.score?.home}-${f.score?.away}`; if (prev.current[f.sid] && prev.current[f.sid] !== s) up[f.sid] = now; prev.current[f.sid] = s; });
    if (Object.keys(up).length) setLift((l) => ({ ...l, ...up }));
  }, [fixtures]);
  return (sid) => lift[sid] && Date.now() - lift[sid] < 30000;
}

function Card({ f, onClose, flash }) {
  const [ev, setEv] = useState([]);
  useEffect(() => { get(`/live/${f.sid}/events`).then((r) => setEv(r.events || [])).catch(() => {}); }, [f.sid, f.events_n, f.score?.home, f.score?.away]);
  const card = <LiveCard f={f} events={ev} flash={flash} testid={`live-sheet-card-${f.sid}`} />;
  return f.match_id ? <Link to={`/match/${f.match_id}`} onClick={onClose} className="ls-link" data-testid={`live-sheet-match-${f.sid}`}>{card}</Link> : card;
}

export function LiveSheet({ open, onClose, data }) {
  const [fin, setFin] = useState(false);
  const all = (data?.leagues || []).flatMap((g) => g.fixtures.map((f) => ({ ...f, league_name: g.league })));
  const live = all.filter((f) => f.status === "LIVE");
  const flash = useFlash(live);
  live.sort((a, b) => Number(!!flash(b.sid)) - Number(!!flash(a.sid)));
  const later = all.filter((f) => f.status === "Scheduled");
  const done = all.filter((f) => !["LIVE", "Scheduled"].includes(f.status));
  return (
    <BottomSheet open={open} onClose={onClose} title={live.length ? `Live now · ${live.length}` : "Live scores"} testid="live-sheet"
      footer={<Link to="/live" className="btn btn--primary k-grow" onClick={onClose} data-testid="live-sheet-all">All scores today</Link>}>
      {!data ? <Skeleton shape="match" count={2} testid="live-sheet-loading" /> : (
        <>
          {live.length ? <div className="ls-list">{live.map((f) => <Card key={f.sid} f={f} onClose={onClose} flash={!!flash(f.sid)} />)}</div>
            : <EmptyState icon="clock" title="Nothing live right now" testid="live-sheet-empty">Matches show here as soon as they kick off.</EmptyState>}
          {later.length > 0 && <section data-testid="live-sheet-later"><h3 className="k-sec">Later today</h3><ul className="ls-mini">{later.map((f) => (
            <li key={f.sid}><time>{utc(f.kickoff).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}</time><span>{f.home.team?.name || f.home.name} v {f.away.team?.name || f.away.name}</span></li>))}</ul></section>}
          {done.length > 0 && <section data-testid="live-sheet-finished">
            <button type="button" className="k-link" aria-expanded={fin} onClick={() => setFin(!fin)} data-testid="live-sheet-finished-toggle">Finished ({done.length})</button>
            {fin && <ul className="ls-mini">{done.map((f) => <li key={f.sid}><b>{f.score?.home}–{f.score?.away}</b><span>{f.home.team?.name || f.home.name} v {f.away.team?.name || f.away.name}</span></li>)}</ul>}
          </section>}
        </>
      )}
    </BottomSheet>
  );
}
