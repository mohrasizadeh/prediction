// Fails when any banned word (docs/03, mirrored from backend/textguard.py) appears in src outside comments.
// The exact disclaimer sentence is the one allowed use.
const fs = require("fs");
const path = require("path");
const DISCLAIMER = "Statistical analysis for information and entertainment. Not betting advice.";
const BANNED = /\b(bet|bets|betting|bettors?|bookies?|bookmakers?|sportsbooks?|odds|wagers?|wagering|parlays?|accumulators?|stakes?|punt|punters?|tipsters?|locks?|bankers?|units|hit rate|picks|props)\b/gi;
let bad = 0;
const walk = (d) => fs.readdirSync(d, { withFileTypes: true }).forEach((e) => {
  const p = path.join(d, e.name);
  if (e.isDirectory()) return walk(p);
  if (!/\.(js|jsx|ts|tsx|html|json|md)$/.test(e.name)) return;
  fs.readFileSync(p, "utf8").split("\n").forEach((line, i) => {
    const code = line.replace(/\/\/.*$/, "").replace(/\/\*.*?\*\//g, "").replace(DISCLAIMER, "");
    // props is a React word; only flag it inside quotes or JSX text
    const hits = [...code.matchAll(BANNED)].map((m) => m[0]).filter((w) => !(w.toLowerCase() === "props" && !/["'`>][^"'`<]*\bprops\b/i.test(code)));
    if (hits.length) { bad++; console.log(`${p}:${i + 1}: ${hits.join(", ")}`); }
  });
});
walk(path.join(__dirname, "..", "src"));
walk(path.join(__dirname, "..", "public"));
if (bad) { console.error(`${bad} line(s) use banned words.`); process.exit(1); }
console.log("copy check passed");
