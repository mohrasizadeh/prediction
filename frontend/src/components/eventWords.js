// ONE PLACE FOR THE EVENT VOCABULARY, because having two was the bug.
//
// `backend/normalize_af.py::events` is the only writer of a match event now, for both the live and
// the historical path, and it emits exactly these five words (its `EVENT_TYPES`):
//
//     goal   missed_penalty   yellow   red   sub
//
// This file used to be two separate maps -- one in MatchEvents.jsx, one in LiveBits.jsx -- both
// keyed on the words the RETIRED provider sent: `yellow_card`, `red_card`, `second_yellow`,
// `substitution`, and `own_goal`/`penalty` as types. So of everything the writer actually produces
// only `goal` had a label; a red card and a substitution fell through to the grey "unknown"
// fallback and were captioned with the raw column word. Match.jsx meanwhile counted cards with
// `e.type === "yellow" || e.type === "red"` -- correct, and on the same page -- so one screen was
// reading two vocabularies at once.
//
// The distinctions a reader cares about (own goal, penalty, second yellow) are BOOLEANS on the row
// rather than types, so the label has to be computed from the row and cannot be a plain lookup.

export const EVENT_CLASS = {
  goal: "goal",
  missed_penalty: "miss",
  yellow: "yellow",
  red: "red",
  sub: "sub",
};

// A substitution is not news: it must never be a live card's headline "last event".
export const NOT_HEADLINE = "sub";

export function eventLabel(e) {
  switch (e && e.type) {
    case "goal":
      return e.own_goal ? "Own goal" : e.penalty ? "Penalty goal" : "Goal";
    case "missed_penalty":
      return "Penalty missed";
    case "yellow":
      return "Yellow card";
    case "red":
      return e.second_yellow ? "Second yellow" : "Red card";
    case "sub":
      return "Substitution";
    default:
      return ((e && e.type) || "Event").replace(/_/g, " ");
  }
}

export function eventClass(e) {
  return EVENT_CLASS[e && e.type] || "other";
}
