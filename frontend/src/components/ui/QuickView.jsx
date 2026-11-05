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

export function QuickView({ playerId, stat: stat0 = "shots", line: line0 = 1, title, collapsible = false, children, testid = "quick-view" }) {
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
  return (
    <section className="qv" data-testid={testid}>
      {title && <h3 className="k-sec">{title}</h3>}
      {q.loading && !q.data ? <Loading /> : q.error ? <ErrorBox error={q.error} onRetry={q.reload} /> : !games.length ? <Empty icon="activity">No games match these filters.</Empty> : (
        <>
          <p className="muted small" data-testid={`${testid}-summary`}>{known ? `${line} or more in ${hits} of ${known} games.` : "No data for this stat."}</p>
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
