// Copy rules live in docs/03 (analysis only, plain words). `node scripts/check-copy.js` scans src for the words
// that list forbids; the same list is enforced on the server by backend/textguard.py.
export const DISCLAIMER = "Statistical analysis for information and entertainment. Not betting advice.";
// The tier badge, and the ONE place its words are decided (docs/75).
//
// Strong / Solid / Watch are confidence words, and that is correct AS LONG AS the badge grades the
// likelihood: Strong is 90% or more, Solid 80%, Watch 60% (engine.strong_min and friends). It stops
// being correct the moment `engine.personal_lines` is on, because a personal line sits where the
// player lands about half the time and the badge then grades the DEPARTURE from their usual game
// instead -- which is how a 57% card reading Watch ends up beside a 56% one reading Solid.
//
// The words were briefly renamed to the departure axis to resolve that. The owner's answer was
// better: keep the words and keep the grading they describe. See docs/75.
export const TIER = {
  Strong: { dots: 3, label: "Strong" },
  Solid: { dots: 2, label: "Solid" },
  Watch: { dots: 1, label: "Watch" },
};
// What a row with no tier is called where something has to be called something -- a filter chip.
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
