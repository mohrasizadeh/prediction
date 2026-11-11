// ForecastList -- a list of forecasts, drawn the one agreed way.
//
// ForecastRow renders a <tr> and owns which rung is picked, but not which row is expanded: only
// one Why panel should be open at a time, and that belongs to the list. Every screen that drew a
// grid of cards was otherwise about to grow its own copy of this table and its own useState, six
// times over.
import { useState } from "react";
import { ForecastRow } from "./ForecastRow";

export function ForecastList({ rows, teams, homeIid, track, testid, extras = true }) {
  const [open, setOpen] = useState(null);
  if (!rows?.length) return null;
  return (
    <table className="lk-tbl" data-testid={testid}>
      {/* The widths live here, not on the cells. With `table-layout: fixed` a table takes its
          column widths from its FIRST row -- which is the header now -- so widths set on the body's
          cells were ignored and all eight columns came out equal. A colgroup says it once, for the
          table, whichever row happens to come first. */}
      <colgroup>
        <col className="lk-c-say" /><col className="lk-c-run" /><col className="lk-c-res" />
        <col className="lk-c-lk" /><col className="lk-c-tier" /><col className="lk-c-why" />
        <col className="lk-c-lu" /><col className="lk-c-act" />
      </colgroup>
      {/* Saying what each column is, once, is the cheapest clarity available -- and it is what lets
          the rows themselves stay short. Hidden on a phone, where a card has no columns to label. */}
      <thead>
        <tr>
          <th className="lk-h-say">Forecast</th><th>Last 10</th><th>Result</th>
          <th className="lk-h-lk">Chance</th><th>Grade</th><th>Why</th><th>Lineup</th><th aria-label="Save and combo" />
        </tr>
      </thead>
      <tbody>
        {rows.map((f, i) => (
          <ForecastRow
            key={f.id || f.fkey || i}
            f={f}
            floor={0}
            teams={teams}
            homeIid={homeIid}
            track={track}
            extras={extras}
            open={open === (f.id || f.fkey)}
            onToggle={() => setOpen(open === (f.id || f.fkey) ? null : (f.id || f.fkey))}
          />
        ))}
      </tbody>
    </table>
  );
}
