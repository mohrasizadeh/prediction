// Swipeable day strip (docs/24). Yesterday, Today, Tomorrow, then weekdays; a dot under days with games.
// The last day picked is remembered for the session (sessionStorage) when `storeKey` is given.
import { useEffect, useMemo, useRef, useState } from "react";
import Icon from "../Icon";
import { LeagueMark } from "../Media";

export const isoDay = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const NAMES = { "-1": "Yest.", 0: "Today", 1: "Tmrw" };

export function useSessionDay(storeKey) {
  const [day, setDay] = useState(() => (storeKey && sessionStorage.getItem(storeKey)) || isoDay(new Date()));
  const set = (d) => { setDay(d); if (storeKey) sessionStorage.setItem(storeKey, d); };
  return [day, set];
}

const MAX_MARKS = 3;                       // more than three crests on a 62 px day is a smudge, not information

export function DateScroller({ value, onChange, from = -1, count = 7, gameDays, dayLeagues, testid = "ui-dates" }) {
  const ref = useRef(null);
  const days = useMemo(() => [...Array(count)].map((_, i) => { const d = new Date(); d.setDate(d.getDate() + from + i); return { d, off: from + i }; }), [from, count]);
  useEffect(() => {
    const el = ref.current?.querySelector('[aria-selected="true"]');
    if (el?.scrollIntoView) el.scrollIntoView({ block: "nearest", inline: "center" });
  }, [value]);
  const pick = (e) => { if (e.target.value) onChange(e.target.value); };
  return (
    <div className="k-days-wrap">
      <div className="k-days" role="tablist" aria-label="Day" ref={ref} data-testid={testid}>
        {days.map(({ d, off }) => {
          const k = isoDay(d);
          const has = gameDays ? gameDays.has(k) : false;
          const lgs = (dayLeagues && dayLeagues[k]) || [];
          return (
            <button key={k} type="button" role="tab" aria-selected={k === value} aria-current={k === value ? "date" : undefined} className={`k-day${k === value ? " on" : ""}`} onClick={() => onChange(k)}
              aria-label={`${NAMES[off] || d.toLocaleDateString(undefined, { weekday: "short" })} ${d.getDate()}, ${d.toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" })}${lgs.length ? `, ${lgs.map((l) => l.name).join(", ")}` : has ? ", has games" : ""}`} data-testid={`${testid}-${k}`}>
              <span className="w">{NAMES[off] || d.toLocaleDateString(undefined, { weekday: "short" })}</span>
              <span className="n">{d.getDate()}</span>
              {lgs.length ? (
                <span className="k-day-lgs" aria-hidden="true">
                  {lgs.slice(0, MAX_MARKS).map((l) => <LeagueMark key={l.id} league={l} size={14} />)}
                  {lgs.length > MAX_MARKS && <i className="k-day-more">+{lgs.length - MAX_MARKS}</i>}
                </span>
              ) : <span className={`dot${has ? "" : " no"}`} aria-hidden="true" />}
            </button>
          );
        })}
      </div>
      <label className="k-day k-day--cal" title="Pick a date">
        <Icon name="calendar" size={20} /><span className="sr-only">Pick a date</span>
        <input type="date" value={value} onChange={pick} data-testid={`${testid}-calendar`} />
      </label>
    </div>
  );
}
