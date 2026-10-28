// Live count and live sheet (docs/24 "Navigation"): polls our own GET /api/live every 60 s while the tab is
// visible. The floating pill shows while something is live and opens this sheet; the full page stays at /live.
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { get } from "../lib/api";
import { BottomSheet, EmptyState, LiveCard, Skeleton } from "./ui";
import { isoDay } from "./ui/DateScroller";

export function useLiveNow() {
  const [d, setD] = useState(null);
  useEffect(() => {
    let stop = false, t = null;
    const load = () => get("/live", { date: isoDay(new Date()), tz: -new Date().getTimezoneOffset() }).then((r) => { if (!stop) setD(r); }).catch(() => {});
    const loop = () => { if (document.visibilityState === "visible") load(); t = setTimeout(loop, 60000); };
    loop();
    return () => { stop = true; clearTimeout(t); };
  }, []);
  return d;
}

export function LiveSheet({ open, onClose, data }) {
  const live = (data?.leagues || []).flatMap((g) => g.fixtures.filter((f) => f.status === "LIVE").map((f) => ({ ...f, league_name: g.league })));
  return (
    <BottomSheet open={open} onClose={onClose} title="Live now" testid="live-sheet"
      footer={<Link to="/live" className="btn btn--primary k-grow" onClick={onClose} data-testid="live-sheet-all">All scores today</Link>}>
      {!data ? <Skeleton shape="match" count={2} testid="live-sheet-loading" />
        : !live.length ? <EmptyState icon="clock" title="Nothing live right now" testid="live-sheet-empty">Matches show here as soon as they kick off.</EmptyState>
        : <div className="ls-list">{live.map((f) => (
          f.match_id ? <Link key={f.sid} to={`/match/${f.match_id}`} onClick={onClose} className="ls-link" data-testid={`live-sheet-match-${f.sid}`}><LiveCard f={f} testid={`live-sheet-card-${f.sid}`} /></Link>
            : <LiveCard key={f.sid} f={f} testid={`live-sheet-card-${f.sid}`} />
        ))}</div>}
    </BottomSheet>
  );
}
