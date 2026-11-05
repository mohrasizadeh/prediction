// The Quick view (docs/48): pick a stat, a window, a line and a venue, and see game by game whether it was
// reached -- minutes above, the figure in the middle, the opponent's crest below.
//
// It lived only on the player page. The forecast sheet showed a fixed last-10 strip for whatever line you had
// tapped, so the one question a reader actually has next -- "what about 2+, or only at home, or only when he
// started?" -- meant leaving the sheet. Both screens now use this, and the sheet opens it already set to the
// line being looked at.
import { useState } from "react";
import { useApi } from "../../lib/useApi";
import { STATS, Seg, Select } from "../Football";
import { Empty, ErrorBox, Loading } from "../States";
import { GameStrip } from "./Marks";

export function QuickView({ playerId, stat: stat0 = "shots", line: line0 = 1, title, collapsible = false, forecasts, children, testid = "quick-view" }) {
  const [open, setOpen] = useState(!collapsible);
  const [stat, setStat] = useState(STATS.some((s) => s.id === stat0) ? stat0 : "shots");
  const [last, setLast] = useState(10);
  const [line, setLine] = useState(line0 || 1);
  const [venue, setVenue] = useState("all");
  const [started, setStarted] = useState(false);
  const q = useApi(playerId ? `/players/${playerId}/history` : null, { last, started, ...(venue !== "all" ? { venue } : {}) });
  const label = STATS.find((s) => s.id === stat)?.label || stat;
  const games = q.data?.games || [];
  const known = games.filter((g) => g[stat] != null).length;
  const hits = games.filter((g) => g[stat] != null && g[stat] >= line).length;
  // Asked for: whichever market and line the reader picks, show what we expect for it next match.
  // Matching only the stored line would leave most choices blank, because a player keeps three
  // lines per stat and the reader can pick five. Every forecast carries the whole ladder, so the
  // percentage is resolved from that and follows any market and line combination.
  const fcAny = (forecasts || []).find((f) => f.stat === stat);
  const fcExact = (forecasts || []).find((f) => f.stat === stat && Math.floor(f.thr) + 1 === Number(line));
  const fromLadder = fcAny?.ladder?.[String(Number(line) - 0.5)];
  const fcP = fcExact ? fcExact.p : (typeof fromLadder === "number" ? fromLadder : null);
  const fc = fcP == null ? null : { p: fcP, tier: fcExact?.tier || null, exact: !!fcExact };
  return (
    <section className="qv" data-testid={testid}>
      {title && <h3 className="k-sec">{title}</h3>}
      {q.loading && !q.data ? <Loading /> : q.error ? <ErrorBox error={q.error} onRetry={q.reload} /> : !games.length ? <Empty icon="activity">No games match these filters.</Empty> : (
        <>
          <div className="v2-qv-head">
            <p className="muted small" data-testid={`${testid}-summary`}>{known ? `${line} or more in ${hits} of ${known} games.` : "No data for this stat."}</p>
            {fc ? (
              <p className="v2-qv-fc" data-testid={`${testid}-forecast`}>
                <span>{line}+ {label.toLowerCase()} next match</span>
                <b>{Math.round((fc.p || 0) * 100)}%</b>
                {fc.tier ? <em>{fc.tier}</em> : null}
              </p>
            ) : forecasts ? (
              /* Silence here read as a bug: switch to a market this player has no forecast for and
                 the figure simply vanished, with nothing to say whether it was missing or loading. */
              <p className="v2-qv-fc v2-qv-fc--none" data-testid={`${testid}-forecast`}>
                <span>No forecast for {label.toLowerCase()} next match</span>
              </p>
            ) : null}
          </div>
          <GameStrip games={games} stat={stat} line={line} label={label} testid={`${testid}-strip`} />
          {/* docs/redesign/v2: the market and the line ARE the question this box answers, so they lead
              it rather than hiding behind "Change the line or filters" and then arriving as five
              full-width stacked rows. Window, venue and started-only are refinements and sit after. */}
          {open && (
            <div className="filters v2-qv">
              <Select label="Stat" value={stat} onChange={setStat} options={STATS} testid={`${testid}-stat`} />
              <Seg label="Line" value={line} onChange={(v) => setLine(Number(v))} options={[1, 2, 3, 4, 5].map((n) => ({ id: n, label: `${n}+` }))} testid={`${testid}-line`} />
              <Seg label="Window" value={last} onChange={setLast} options={[5, 10, 20].map((n) => ({ id: n, label: `Last ${n}` }))} testid={`${testid}-window`} />
              <Seg label="Venue" value={venue} onChange={setVenue} options={[{ id: "all", label: "All" }, { id: "home", label: "Home" }, { id: "away", label: "Away" }]} testid={`${testid}-venue`} />
              <label className="check-inline"><input type="checkbox" checked={started} onChange={(e) => setStarted(e.target.checked)} data-testid={`${testid}-started`} /> Started only</label>
            </div>
          )}
          {collapsible && <button type="button" className="k-link qv-toggle" aria-expanded={open} onClick={() => setOpen((o) => !o)} data-testid={`${testid}-toggle`}>{open ? "Hide filters" : "Change the line or filters"}</button>}
          {typeof children === "function" ? children(games) : children}
        </>
      )}
    </section>
  );
}
