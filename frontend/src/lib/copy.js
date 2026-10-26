// Copy rules live in docs/03 (analysis only, plain words). `node scripts/check-copy.js` scans src for the words
// that list forbids; the same list is enforced on the server by backend/textguard.py.
export const DISCLAIMER = "Statistical analysis for information and entertainment. Not betting advice.";
export const TIER = { Strong: { dots: 3 }, Solid: { dots: 2 }, Watch: { dots: 1 } };
export const pct = (p) => (p == null ? "–" : `${Math.round(p * 100)}%`);
