// Swipeable day strip (docs/24). Yesterday, Today, Tomorrow, then weekdays; a dot under days with games.
// The last day picked is remembered for the session (sessionStorage) when `storeKey` is given.
import { useEffect, useMemo, useRef, useState } from "react";
import Icon from "../Icon";

export const isoDay = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const NAMES = { "-1": "Yest.", 0: "Today", 1: "Tmrw" };

export function useSessionDay(storeKey) {
  const [day, setDay] = useState(() => (storeKey && sessionStorage.getItem(storeKey)) || isoDay(new Date()));
  const set = (d) => { setDay(d); if (storeKey) sessionStorage.setItem(storeKey, d); };
  return [day, set];
}

// The league crests that used to sit under each date are gone. Three 14px marks plus a gap need
// about 48px of unshrinkable content inside a tile that measures 44px on a 390px phone, so the
// row could not shrink to the viewport and the WHOLE PAGE scrolled sideways -- the day strip was
// the thing pushing Today off its own screen. They were also the wrong information for the slot:
// a reader scanning dates is asking "is there football on", not "which five competitions", and
// the answer to the first is one dot. The leagues stay in the tile's accessible name, where they
// cost no width.

// How many days fit on a phone before a tile goes under the project's 44px touch-target floor.
// Seven days and a calendar button need 552px at their natural width; wrapping them instead cost
// three rows and 230px, which is 30% of a phone fold spent on a date picker before a stranger has
// seen one forecast. Five fit in one row at 56px on the narrowest phone we support, and the
// calendar button reaches every other day anyway.
const NARROW = 420;
const NARROW_COUNT = 5;

function useDayCount(count) {
  const [narrow, setNarrow] = useState(() => (typeof window !== "undefined" && window.matchMedia
    ? window.matchMedia(`(max-width: ${NARROW - 1}px)`).matches : false));
  useEffect(() => {
    if (!window.matchMedia) return undefined;
    const mq = window.matchMedia(`(max-width: ${NARROW - 1}px)`);
    const h = (e) => setNarrow(e.matches);
    mq.addEventListener("change", h);
    setNarrow(mq.matches);
    return () => mq.removeEventListener("change", h);
  }, []);
  return narrow ? Math.min(count, NARROW_COUNT) : count;
}

export function DateScroller({ value, onChange, from = -1, count: count0 = 7, gameDays, dayLeagues, testid = "ui-dates" }) {
  const count = useDayCount(count0);
  const ref = useRef(null);
  const cal = useRef(null);
  // The strip never said which month it was in. Crossing a boundary it read "31" then "1", and a
  // reader three taps deep had no way to tell which. The month is printed when it changes.
  const monthOf = (d) => d.toLocaleDateString(undefined, { month: "short" });
  // Without bounds a reader could land on 1994 and get an empty page with no explanation. A year
  // back and two months forward is the range this product has anything to say about.
  const bound = (n) => { const d = new Date(); d.setDate(d.getDate() + n); return isoDay(d); };
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
              <span className="n">{d.getDate()}{d.getDate() === 1 || off === from ? <i className="k-day-mon">{monthOf(d)}</i> : null}</span>
              <span className={`dot${has || lgs.length ? "" : " no"}`} aria-hidden="true" />
            </button>
          );
        })}
      </div>
      {/* Clicking the icon used to rely on the label focusing the input, which does not open the
          picker on a desktop browser -- so on a computer the control often did nothing at all.
          showPicker opens it directly where the browser supports it. */}
      <button type="button" className="k-day k-day--cal" title="Pick a date"
              onClick={() => { const el = cal.current; if (el?.showPicker) { try { el.showPicker(); return; } catch { /* fall through */ } } el?.focus(); el?.click(); }}>
        <Icon name="calendar" size={20} /><span className="sr-only">Pick a date</span>
        <input ref={cal} type="date" value={value} min={bound(-365)} max={bound(60)} onChange={pick}
               onClick={(e) => e.stopPropagation()} data-testid={`${testid}-calendar`} />
      </button>
    </div>
  );
}
