// Copy rules live in docs/03 (analysis only, plain words). `node scripts/check-copy.js` scans src for the words
// that list forbids; the same list is enforced on the server by backend/textguard.py.
export const DISCLAIMER = "Statistical analysis for information and entertainment. Not betting advice.";
// The tier badge, and the ONE place its words are decided (docs/75).
//
// The stored values are still Strong / Solid / Watch -- the engine writes them, settings name them,
// forecast_outcomes keeps them, filters query them. Only the WORDS changed, and they changed because
// the old ones were teaching the wrong thing.
//
// "Strong" is a confidence word. A reader maps it to "strong chance" and then meets a 57% card
// reading Watch beside a 56% one reading Solid, and concludes the product is broken. It is not: the
// badge grades the DEPARTURE from this player's usual game (docs/52, docs/58), never the percentage
// beside it. The concept was right and the label was arguing with it.
//
// Named for the axis it measures, the contradiction disappears without a word of explanation:
// "56%, above usual" next to "57%, near usual" is obviously coherent.
export const TIER = {
  Strong: { dots: 3, label: "Well above usual" },
  Solid: { dots: 2, label: "Above usual" },
  Watch: { dots: 1, label: "Near usual" },
};
// What a row with no tier is called, where something has to be called something -- a filter chip.
// On a card it stays what it has always been: nothing at all.
export const NO_TIER_LABEL = "Typical";
export const tierLabel = (t) => TIER[t]?.label || (t ? String(t) : NO_TIER_LABEL);
export const pct = (p) => (p == null ? "–" : `${Math.round(p * 100)}%`);
// The likely range around a forecast, as docs/03 §4.4 asks: "74% (66 to 81)". Null when the line has no range
// (ladder answers) or the range rounds to the number itself.
export const range = (lo, hi) => {
  if (lo == null || hi == null) return null;
  const a = Math.round(lo * 100), b = Math.round(hi * 100);
  return a === b ? null : `${a} to ${b}`;
};
