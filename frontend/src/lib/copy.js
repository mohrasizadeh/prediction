// Copy rules live in docs/03 (analysis only, plain words). `node scripts/check-copy.js` scans src for the words
// that list forbids; the same list is enforced on the server by backend/textguard.py.
export const DISCLAIMER = "Statistical analysis for information and entertainment. Not betting advice.";
// The tier badge, and the ONE place its words are decided (docs/76).
//
// Strong / Solid / Watch are confidence words, and they grade the LIKELIHOOD -- always, one rule,
// whatever `engine.personal_lines` is set to. Strong is 90% or more, Solid 80%, Watch 60%
// (engine.strong_min and friends).
//
// It did not used to be. With personal lines on, the badge graded the DEPARTURE from a player's
// usual game instead, which is how a 57% card reading Watch ended up beside a 56% one reading
// Solid. Two fixes were tried: renaming the words to the departure axis (wrong -- "Strong" is a
// confidence word and a reader is right to read it as one), and explaining the two meanings in the
// copy (wrong for the same reason, one rule earlier). The answer was to grade the likelihood
// always and write the departure out in words on the card. docs/76.
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
