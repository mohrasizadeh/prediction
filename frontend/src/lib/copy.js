// Copy rules live in docs/03 (analysis only, plain words). `node scripts/check-copy.js` scans src for the words
// that list forbids; the same list is enforced on the server by backend/textguard.py.
export const DISCLAIMER = "Statistical analysis for information and entertainment. Not betting advice.";
export const TIER = { Strong: { dots: 3 }, Solid: { dots: 2 }, Watch: { dots: 1 } };
export const pct = (p) => (p == null ? "–" : `${Math.round(p * 100)}%`);
// The likely range around a forecast, as docs/03 §4.4 asks: "74% (66 to 81)". Null when the line has no range
// (ladder answers) or the range rounds to the number itself.
export const range = (lo, hi) => {
  if (lo == null || hi == null) return null;
  const a = Math.round(lo * 100), b = Math.round(hi * 100);
  return a === b ? null : `${a} to ${b}`;
};
