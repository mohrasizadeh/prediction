// Resolving "what do we say about THIS line?" in one place.
//
// Reported: "changing the lines or filters doesn't reflect on the percentage — that percentage on
// the card is fixed for 1+ tackle." It was true. QuickView already worked out the answer for
// whichever rung the reader picked (`fcP`), and then rendered it nowhere, because the sheet passes
// `showForecast={false}` to stop the headline being printed a second time. The decision was right;
// it just left the control with no readout at all, so moving it appeared to do nothing.
//
// The formula now lives here and both the headline and the rung chips read it, so they cannot
// disagree.
//
// Three sources, in order of how much we know:
//   "stored" — a rung the engine kept. Everything is real: range, tier, usual.
//   "ladder" — a rung outside the kept band. ONLY the percentage is real (engine_bridge stamps the
//              whole ladder on every kept line). No range, no tier, nothing to save or combine.
//   "none"   — a stat we hold history for but no forecast.

export const MAX_RUNGS = 8;          // as many lines as fit a phone row without becoming a wall

const thrOf = (line) => Number(line) - 0.5;

// Which lines can be offered at all, from the ladder the engine stamped on this stat's forecasts.
// A player's ladder is three to five rungs; a club's is sixteen, which is a wall rather than a
// choice, so it is windowed around the line the reader arrived on.
export function rungsFor(forecasts, stat, around) {
  const any = (forecasts || []).find((f) => f.stat === stat);
  const all = any?.ladder
    ? Object.keys(any.ladder).map((k) => Math.floor(Number(k)) + 1).filter((v) => v > 0).sort((a, b) => a - b)
    : null;
  if (!all || !all.length) return [1, 2, 3, 4, 5];
  if (all.length <= MAX_RUNGS) return all;
  const at = all.indexOf(Number(around) || all[0]);
  const from = Math.min(Math.max(0, (at < 0 ? 0 : at) - 1), all.length - MAX_RUNGS);
  return all.slice(from, from + MAX_RUNGS);
}

// The answer for one stat and one line. `label` is the human stat name, used only to compose a
// market string for a ladder rung, which carries none.
export function answerFor(forecasts, stat, line, label) {
  const list = forecasts || [];
  const exact = list.find((f) => f.stat === stat && Math.floor(f.thr) + 1 === Number(line));
  if (exact) return { ...exact, source: "stored", line: Number(line) };
  const any = list.find((f) => f.stat === stat);
  const p = any?.ladder?.[String(thrOf(line))];
  if (typeof p !== "number") return { source: "none", stat, thr: thrOf(line), line: Number(line), p: null };
  // Only the percentage survives. Everything else on a card -- the range, the tier, the reasons,
  // the span sentence, the streak, the season count -- belongs to a rung the engine actually kept,
  // and carrying any of it across would attach one line's evidence to another line's number.
  return {
    source: "ladder", fkey: null, id: null, stat, thr: thrOf(line), line: Number(line),
    market: `${line}+ ${(label || stat).toLowerCase()}`,
    p, lo: null, hi: null, tier: null, tier_note: null, p_usual: null, span: null, span_pos: null,
    reasons: null, streak: null, rec_k: null, rec_n: null, addable: false, from_ladder: true,
    p_display: p > 0.95 ? "95%+" : p < 0.5 ? "under 50%" : null,
  };
}
