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
import { answerFor, rungsFor } from "../../lib/lines";

export function QuickView({ playerId, teamId, stat: stat0 = "shots", line: line0 = 1, title, collapsible = false,
                            defaultOpen, showForecast = true, forecasts, children, value, onChange, testid = "quick-view" }) {
  // A club gets the same interrogation a player has. Before this, QuickView took `playerId` only,
  // so the club's sheet fell back to a fixed ten-game strip for whichever line had been tapped and
  // the club page had no evidence block at all -- while the reader's next question after "3+
  // corners, 87%" is "what about 4+, and only away?". That was the single biggest asymmetry
  // between the two entity types (docs/redesign/v4/TEAMS.md §4.3).
  const isTeam = !playerId && !!teamId;
  const OPTS = isTeam ? TEAM_HISTORY_STATS : STATS;
  const [open, setOpen] = useState(defaultOpen != null ? defaultOpen : !collapsible);
  // The stat and the line can be owned from outside, because they choose the CLAIM and a panel
  // that shows a headline has to agree with them. The window, the venue and started-only stay
  // here: those filter the evidence, and the claim is the same whichever games you look at.
  const [own, setOwn] = useState({ stat: OPTS.some((s) => s.id === stat0) ? stat0 : (isTeam ? "corners" : "shots"), line: line0 || 1 });
  const sel = value || own;
  const put = (patch) => { const next = { ...sel, ...patch }; if (onChange) onChange(next); if (!value) setOwn(next); };
  const stat = sel.stat;
  const line = sel.line;
  const setStat = (v) => put({ stat: v });
  const setLine = (v) => put({ line: Number(v) });
  const [last, setLast] = useState(10);
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
  // Offer the lines we can actually answer. engine.player_ladder is per stat -- tackles starts at
  // 2+, on-target stops at 4+ -- so a fixed 1+..5+ row promised five answers and delivered as few
  // as three, which read as the forecast being broken rather than the line never being modelled.
  // Windowed around the line the reader ARRIVED on, not the one they are standing on: a window
  // that slid under every tap would move the chips out from under the finger.
  const lineOpts = useMemo(() => rungsFor(forecasts, stat, line0), [forecasts, stat, line0]);
  const snap = lineOpts.includes(line) ? null
    : lineOpts.reduce((best, v) => (Math.abs(v - line) < Math.abs(best - line) ? v : best), lineOpts[0]);
  useEffect(() => {
    // Switching market can strip the line out from under the reader; land on the nearest we have.
    if (snap != null) setLine(snap);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [snap]);
  const ans = forecasts ? answerFor(forecasts, stat, line, label) : null;
  const fc = ans && ans.p != null ? { p: ans.p, tier: ans.tier, exact: ans.source === "stored" } : null;
  return (
    <section className="qv" data-testid={testid}>
      {title && <h3 className="k-sec">{title}</h3>}
      {q.loading && !q.data ? <Loading /> : q.error ? <ErrorBox error={q.error} onRetry={q.reload} /> : !games.length ? <Empty icon="activity">No games match these filters.</Empty> : (
        <>
          <div className="v2-qv-head">
            <p className="muted small" data-testid={`${testid}-summary`}>{known ? `${line} or more in ${hits} of ${known} games.` : "No data for this stat."}</p>
            {fc && showForecast ? (
              <p className="v2-qv-fc" data-testid={`${testid}-forecast`}>
                <span>{line}+ {label.toLowerCase()} next match</span>
                <b>{Math.round((fc.p || 0) * 100)}%</b>
                {fc.tier ? <em>{fc.tier}</em> : null}
              </p>
            ) : forecasts && !fc ? (
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
