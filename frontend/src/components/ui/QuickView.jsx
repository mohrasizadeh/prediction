// The Quick view (docs/48): pick a stat, a window, a line and a venue, and see game by game whether it was
// reached -- minutes above, the figure in the middle, the opponent's crest below.
//
// It lived only on the player page. The forecast sheet showed a fixed last-10 strip for whatever line you had
// tapped, so the one question a reader actually has next -- "what about 2+, or only at home, or only when he
// started?" -- meant leaving the sheet. Both screens now use this, and the sheet opens it already set to the
// line being looked at.
import { useEffect, useMemo, useState } from "react";
import { useApi } from "../../lib/useApi";
import { STATS, TEAM_HISTORY_STATS, Seg, Select } from "../Football";
import { Empty, ErrorBox, Loading } from "../States";
import { GameStrip } from "./Marks";

const MAX_RUNGS = 8;          // as many lines as fit a phone row without turning the control into a wall

export function QuickView({ playerId, teamId, stat: stat0 = "shots", line: line0 = 1, title, collapsible = false,
                            defaultOpen, showForecast = true, forecasts, children, testid = "quick-view" }) {
  // A club gets the same interrogation a player has. Before this, QuickView took `playerId` only,
  // so the club's sheet fell back to a fixed ten-game strip for whichever line had been tapped and
  // the club page had no evidence block at all -- while the reader's next question after "3+
  // corners, 87%" is "what about 4+, and only away?". That was the single biggest asymmetry
  // between the two entity types (docs/redesign/v4/TEAMS.md §4.3).
  const isTeam = !playerId && !!teamId;
  const OPTS = isTeam ? TEAM_HISTORY_STATS : STATS;
  const [open, setOpen] = useState(defaultOpen != null ? defaultOpen : !collapsible);
  const [stat, setStat] = useState(OPTS.some((s) => s.id === stat0) ? stat0 : (isTeam ? "corners" : "shots"));
  const [last, setLast] = useState(10);
  const [line, setLine] = useState(line0 || 1);
  const [venue, setVenue] = useState("all");
  const [started, setStarted] = useState(false);
  // `stat` is a query parameter for a club and NOT for a player, which is not an oversight to tidy
  // up: /players/{id}/history returns every stat for each game, /teams/{id}/history returns one.
  // That is why changing the Stat control refetches for a club and does not for a player.
  const q = useApi(playerId ? `/players/${playerId}/history` : teamId ? `/teams/${teamId}/history` : null,
                   playerId ? { last, started, ...(venue !== "all" ? { venue } : {}) }
                            : { stat, last, ...(venue !== "all" ? { venue } : {}) });
  const label = OPTS.find((s) => s.id === stat)?.label || stat;
  const games = q.data?.games || [];
  const known = games.filter((g) => g[stat] != null).length;
  const hits = games.filter((g) => g[stat] != null && g[stat] >= line).length;
  // Asked for: whichever market and line the reader picks, show what we expect for it next match.
  // Matching only the stored line would leave most choices blank, because a player keeps three
  // lines per stat and the reader can pick five. Every forecast carries the whole ladder, so the
  // percentage is resolved from that and follows any market and line combination.
  const fcAny = (forecasts || []).find((f) => f.stat === stat);
  // Offer the lines we can actually answer. engine.player_ladder is per stat -- tackles starts at
  // 2+, on-target stops at 4+ -- so a fixed 1+..5+ row promised five answers and delivered as few
  // as three, which read as the forecast being broken rather than the line never being modelled.
  // With no ladder at all (a stat we hold history but no forecast for) the plain row is still the
  // right tool for reading the run.
  // Memoised on the ladder itself: a new array each render made the effect below depend on
  // identity rather than on content, so it re-ran on every single render.
  const lineOpts = useMemo(() => {
    const rungs = fcAny?.ladder ? Object.keys(fcAny.ladder).map((k) => Math.floor(Number(k)) + 1).filter((v) => v > 0).sort((a, b) => a - b) : null;
    if (!rungs || !rungs.length) return [1, 2, 3, 4, 5];
    // A player's ladder is three to five rungs. A club's is sixteen (6.5 through 22.5 on the demo
    // league), and sixteen chips is not a choice, it is a wall -- measured, the row forced the
    // whole Quick view to 857px inside a 390px phone. So a window of MAX_RUNGS around the line the
    // reader arrived on, which is the only part of the ladder they are reading against.
    if (rungs.length <= MAX_RUNGS) return rungs;
    const at = rungs.indexOf(line0 || rungs[0]);
    const from = Math.min(Math.max(0, (at < 0 ? 0 : at) - 1), rungs.length - MAX_RUNGS);
    return rungs.slice(from, from + MAX_RUNGS);
  }, [fcAny?.ladder, line0]);
  useEffect(() => {
    // Switching market can strip the line out from under the reader; land on the nearest we have.
    if (lineOpts.includes(line)) return;
    setLine(lineOpts.reduce((best, v) => (Math.abs(v - line) < Math.abs(best - line) ? v : best), lineOpts[0]));
  }, [stat, line, lineOpts]);
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
            {!showForecast ? null : fc ? (
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
              <Select label="Stat" value={stat} onChange={setStat} options={OPTS} testid={`${testid}-stat`} />
              <Seg label="Line" value={line} onChange={(v) => setLine(Number(v))} options={lineOpts.map((n) => ({ id: n, label: `${n}+` }))} testid={`${testid}-line`} />
              <Seg label="Window" value={last} onChange={setLast} options={[5, 10, 20].map((n) => ({ id: n, label: `Last ${n}` }))} testid={`${testid}-window`} />
              <Seg label="Venue" value={venue} onChange={setVenue} options={[{ id: "all", label: "All" }, { id: "home", label: "Home" }, { id: "away", label: "Away" }]} testid={`${testid}-venue`} />
              {!isTeam && <label className="check-inline"><input type="checkbox" checked={started} onChange={(e) => setStarted(e.target.checked)} data-testid={`${testid}-started`} /> Started only</label>}
            </div>
          )}
          {collapsible && <button type="button" className="k-link qv-toggle" aria-expanded={open} onClick={() => setOpen((o) => !o)} data-testid={`${testid}-toggle`}>{open ? "Hide filters" : "Change the line or filters"}</button>}
          {typeof children === "function" ? children(games) : children}
        </>
      )}
    </section>
  );
}
