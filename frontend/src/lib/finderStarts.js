// Eight questions the Finder can answer, shown on the screen a reader first lands on.
//
// Reported against the counting tools: their screener opens with eight named searches, each with
// a sentence and its exact parameters printed on the card, so you learn the tool by reading it.
// Ours opened with "Pick a league first" and a counter saying how many searches were left. We
// gated where they taught.
//
// Three different things, kept separate (docs/redesign/v3/audit/COMPETITORS.md): these shipped
// starts, the searches a reader saves themselves, and the forecasts they follow. This file is only
// the first. Nothing here is a recommendation -- each one is a question, and the answer is whatever
// the data says today.
//
// The chips under each name are DERIVED from the query below them, never written by hand, so the
// card cannot drift from the search it runs.
export const FINDER_STARTS = [
  { id: "all-ten", name: "Every single game",
    why: "A shot in all ten of their last ten. The shortest list on this page, and the hardest to argue with.",
    q: "mode=form&stat=shots&n=1&last_n=10&min=10" },
  { id: "on-a-run", name: "On a run right now",
    why: "Two or more shots, every game, streak still unbroken. Ends the moment it ends.",
    q: "mode=run&stat=shots&n=2&last_n=10" },
  { id: "def-shots", name: "Defenders who shoot",
    why: "Set pieces put centre-backs in the box. Some of them are there often enough for it to be a habit.",
    q: "mode=form&stat=shots&n=1&last_n=10&min=6&positions=DEF" },
  { id: "tacklers", name: "Tackle machines",
    why: "Two or more tackles in seven of their last ten, from the back line and midfield.",
    q: "mode=form&stat=tackles&n=2&last_n=10&min=7&positions=DEF,MID" },
  { id: "fouls-made", name: "In the thick of it",
    why: "A foul committed in eight of their last ten. The players who break up play for a living.",
    q: "mode=form&stat=fouls_committed&n=1&last_n=10&min=8" },
  { id: "fouled", name: "Fouled a lot",
    why: "Fouled twice or more in six of their last ten. Usually a dribbler, sometimes a target man.",
    q: "mode=form&stat=fouls_won&n=2&last_n=10&min=6&positions=MID,FWD" },
  { id: "corners", name: "Clubs that win corners",
    why: "Five or more corners in seven of their last ten. A club question, not a player one.",
    q: "mode=form&scope=team&stat=corners&n=5&last_n=10&min=7" },
  { id: "we-rate", name: "What we rate highest",
    why: "Not a run at all: our forecast for the next match, strongest first. A long run and a good forecast are different claims, and this is the second one.",
    q: "mode=likelihood&stat=shots&n=2" },
];

const MODE = { form: "How often", run: "Streak", likelihood: "Our forecast" };

// The parameters, read back off the query so what is printed is what runs.
export function startChips(q, statLabel) {
  const p = new URLSearchParams(q);
  const n = p.get("n") || "2";
  const out = [MODE[p.get("mode") || "form"], `${statLabel} ${n}+`];
  if (p.get("scope") === "team") out.push("Clubs"); else out.push("Players");
  const last = p.get("last_n") || "10";
  if (p.get("mode") === "run") out.push(`Last ${last}`);
  else out.push(`${p.get("min") || "6"} of the last ${last}`);
  if (p.get("positions")) out.push(p.get("positions").split(",").join("/"));
  if (p.get("venue")) out.push(p.get("venue") === "home" ? "At home" : "Away");
  return out;
}
