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
