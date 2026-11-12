// Match events timeline (docs/23, docs/38): one centre column with the minute in the middle, home events on
// the left, away on the right. Used by the match page (Live and Recap), /live and the live card, so a goal looks
// the same wherever it is read. Text labels as well as symbols, so colour never carries meaning alone.
//
// Three shapes reach the browser and none of them is ours to rename (README: never invent a field):
//   * recap rows, `match_extras.normalize_events` + queries.match_detail:
//       {type: goal|yellow|red|sub, minute: 45, added: 2, side, player_name, in_name, own_goal, penalty, player, player_in}
//   * SportAPI live rows, `sportapi.events_for`:
//       {type: goal|own_goal|penalty|missed_penalty|yellow_card|second_yellow|red_card|substitution|var, side,
//        player_name, minute: "45+2'", minute_num, extra}
//   * API-Football live rows passed through as stored by `live_af._event_rows`:
//       {type: "Goal"|"Card"|"subst"|"Var", side: null, minute: 45, extra: 2}. No side and no card colour reach us
//       for these, so they read as a neutral "Card" in the centre rather than a guessed colour on a guessed side.
// `normEvent` reads all three into one shape; nothing below it looks at the raw rows.
import { Link } from "react-router-dom";
import { EmptyState } from "./ui/StateViews";   // not "./ui": ui/LiveBits imports this file

const KINDS = {
  goal: "Goal", pen_goal: "Penalty goal", own_goal: "Own goal", pen_miss: "Penalty missed",
  yellow: "Yellow card", second_yellow: "Second yellow, sent off", red: "Red card", card: "Card",
  sub: "Substitution", var: "VAR check", other: "Event",
};
const LIVE_TYPES = {
  goal: "goal", penalty: "pen_goal", penalty_goal: "pen_goal", own_goal: "own_goal", missed_penalty: "pen_miss",
  yellow_card: "yellow", yellow: "yellow", second_yellow: "second_yellow", red_card: "red", red: "red",
  substitution: "sub", sub: "sub", subst: "sub", var: "var", card: "card",
};
export const GOALS = new Set(["goal", "pen_goal", "own_goal"]);
const other = (s) => (s === "home" ? "away" : s === "away" ? "home" : null);

function minuteOf(e) {
  if (typeof e.minute === "number") {
    const added = typeof e.added === "number" ? e.added : typeof e.extra === "number" ? e.extra : 0;
    return [e.minute, added || 0];
  }
  const m = /(\d+)\s*(?:\+\s*(\d+))?/.exec(String(e.minute ?? ""));
  if (m) return [Number(m[1]), m[2] ? Number(m[2]) : 0];
  if (String(e.minute).toUpperCase() === "HT") return [45, 0];
  return [typeof e.minute_num === "number" ? Math.floor(e.minute_num) : null, 0];
}

export function normEvent(e) {
  const raw = String(e.type || "").trim().toLowerCase().replace(/\s+/g, "_");
  let kind = LIVE_TYPES[raw] || "other";
  if (kind === "goal" && e.own_goal) kind = "own_goal";
  else if (kind === "goal" && e.penalty) kind = "pen_goal";
  const [base, added] = minuteOf(e);
  const sub = kind === "sub";
  // A recap substitution names the player going off in `player` and the one coming on in `player_in`.
  // API-Football's own "subst" rows (no in/out keys) name the player going OFF, not the one coming on.
  const afSub = sub && raw === "subst" && !e.in_name && !e.out_name;
  const name = afSub ? "" : sub && (e.player_in || e.in_name) ? e.player_in?.name || e.in_name : e.player?.name || e.player_name || "";
  const id = sub && (e.player_in || e.in_name) ? e.player_in?.id : e.player?.id;
  const out = afSub ? e.player_name : sub ? (e.player_in || e.in_name ? e.player?.name || e.player_name : e.out_name) : null;
  const outId = sub && (e.player_in || e.in_name) ? e.player?.id : null;
  // An own goal is filed under the player's club and counts for the other one (match_extras: first_goal_side).
  const side = e.side === "home" || e.side === "away" ? e.side : null;
  const scorer = kind === "own_goal" ? other(side) : GOALS.has(kind) ? side : null;
  const text = typeof e.extra === "string" && e.extra.trim() ? e.extra.trim() : "";
  return {
    kind, side, scorer, base, added, name, id, out, outId,
    assist: e.assist_name || null,
    note: kind === "var" ? text : text && !/^off:/i.test(text) && text.toLowerCase() !== KINDS[kind].toLowerCase() ? text : "",
    offText: !out && /^off:/i.test(text) ? text.replace(/^off:\s*/i, "") : null,
    label: base == null ? "" : `${base}${added ? `+${added}` : ""}'`,
    order: base == null ? 999 : base + added / 100,
  };
}

export const kindLabel = (k) => KINDS[k] || KINDS.other;

// Inline stroke icons, drawn in the event's own colour token so Site Studio themes still apply.
export function EvIcon({ kind, size = 20 }) {
  const p = { width: size, height: size, viewBox: "0 0 24 24", "aria-hidden": true, focusable: "false", className: `tl-svg tl-svg--${kind}` };
  if (kind === "yellow" || kind === "red" || kind === "card") return <svg {...p}><rect x="7" y="3.5" width="10" height="17" rx="2" /></svg>;
  if (kind === "second_yellow") return <svg {...p}><rect className="tl-y" x="4.5" y="3" width="9.5" height="15" rx="2" /><rect className="tl-r" x="10" y="6" width="9.5" height="15" rx="2" /></svg>;
  if (kind === "sub") return <svg {...p}><path className="tl-in" d="M8 20V5M4 9l4-4 4 4" /><path className="tl-out" d="M16 4v15M12 15l4 4 4-4" /></svg>;
  if (kind === "var") return <svg {...p}><rect x="3" y="4.5" width="18" height="12" rx="2" /><path d="M9 20.5h6M12 16.5v4" /></svg>;
  if (kind === "pen_miss") return <svg {...p}><circle cx="12" cy="12" r="8.5" /><path d="M5.5 18.5 18.5 5.5" /></svg>;
  if (GOALS.has(kind)) return <svg {...p}><circle cx="12" cy="12" r="8.5" /><path d="m12 7.6 3.3 2.4-1.3 3.9h-4l-1.3-3.9z" /><path d="M12 3.5v4.1M15.3 10l4.1-1.3M14 13.9l2.6 3.4M10 13.9l-2.6 3.4M8.7 10 4.6 8.7" /></svg>;
  return <svg {...p}><circle cx="12" cy="12" r="4" /></svg>;
}

const who = (name, id) => (id ? <Link to={`/player/${id}`}>{name}</Link> : name);

// Rows in the order they happened, with the period dividers between them. `score` is the provider's
// {home, away, ht_home, ht_away, pen_home, pen_away}; `phase` "live" | "final".
export function buildTimeline(events, { score = {}, phase = "final", status } = {}) {
  const ev = events.map(normEvent).sort((a, b) => a.order - b.order);
  // Running score only when the goals we hold add up to the score we know. A feed that is still filling in
  // (docs/38 §1c) would otherwise print a 1-0 that never happened.
  let h = 0, a = 0;
  ev.forEach((e) => { if (e.scorer === "home") h += 1; else if (e.scorer === "away") a += 1; e.run = [h, a]; });
  const known = score.home != null && score.away != null;
  const trust = known ? h === Number(score.home) && a === Number(score.away) : phase !== "live" && ev.every((e) => !GOALS.has(e.kind) || e.scorer);
  const st = String(status || "").toUpperCase();
  const pastHalf = phase === "final" || ev.some((e) => e.base > 45) || ["HT", "2H", "ET", "BT", "P", "AET", "PEN", "PENS"].includes(st);
  const extra = ev.some((e) => e.base > 90) || ["ET", "BT", "P", "AET", "PEN", "PENS"].includes(st) || score.pen_home != null;
  const at = (n) => { const last = [...ev].reverse().find((e) => e.base != null && e.base <= n); return last ? last.run : [0, 0]; };
  const ht = score.ht_home != null && score.ht_away != null ? [score.ht_home, score.ht_away] : trust ? at(45) : null;
  const rows = [];
  const div = (id, label, sc) => rows.push({ div: id, label, score: sc });
  let didHt = false, didFt = false;
  ev.forEach((e) => {
    if (!didHt && pastHalf && e.base > 45) { div("ht", "Half-time", ht); didHt = true; }
    if (!didFt && extra && e.base > 90) { div("ft90", "End of normal time", trust ? at(90) : null); didFt = true; }
    rows.push({ ...e, run: trust ? e.run : null });
  });
  if (!didHt && pastHalf) div("ht", "Half-time", ht);
  if (phase === "final") {
    const fin = known ? [score.home, score.away] : trust ? [h, a] : null;
    if (extra && !didFt) div("ft90", "End of normal time", null);
    div("ft", extra ? "After extra time" : "Full time", fin);
    if (score.pen_home != null) div("pens", "Penalties", [score.pen_home, score.pen_away]);
  }
  return rows;
}

function Row({ e, names, i, testid }) {
  if (e.div) {
    return (
      <li className={`tl-div tl-div--${e.div}`} data-testid={`${testid}-div-${e.div}`}>
        <span>{e.label}{e.score && <b>{e.score[0]}–{e.score[1]}</b>}</span>
      </li>
    );
  }
  const k = kindLabel(e.kind);
  // An own goal sits with the club it counted for, beside the score it changed (the convention readers know).
  const side = (e.kind === "own_goal" ? e.scorer : e.side) || "mid";
  const body = (
    <span className="tl-body">
      <EvIcon kind={e.kind} />
      <span className="tl-txt">
        <b className="tl-who">{e.kind === "sub" && <span className="sr-only">On: </span>}{who(e.name || k, e.id)}{GOALS.has(e.kind) && e.run && <span className="tl-run" aria-label={`, score ${e.run[0]} to ${e.run[1]}`}>{e.run[0]}–{e.run[1]}</span>}</b>
        <small>
          {e.kind === "sub" ? (e.out || e.offText ? <>Off: {who(e.out || e.offText, e.outId)}</> : k)
            : e.kind === "var" ? `VAR${e.note ? `: ${e.note}` : " check"}`
            : <>{k}{e.assist ? <> · assist {e.assist}</> : null}{e.note ? ` · ${e.note}` : ""}</>}
        </small>
      </span>
    </span>
  );
  return (
    <li className={`tl-row tl-row--${side} tl-row--${e.kind}${GOALS.has(e.kind) ? " is-goal" : ""}`} data-testid={`${testid}-${i}`}>
      <span className="sr-only">{side !== "mid" ? `${names[side]}. ` : ""}</span>
      <span className="tl-cell tl-cell--home">{side === "home" && body}</span>
      <span className="tl-min">{e.label}</span>
      <span className="tl-cell tl-cell--away">{side === "away" && body}</span>
      {side === "mid" && <span className="tl-cell tl-cell--mid">{body}</span>}
    </li>
  );
}

// Newest first while the match is on: the reader comes back for what just happened, and it should be the
// first line without a scroll (the score is already in the hero). Once it is over the timeline reads as the
// story of the match, top to bottom, with half-time and full time where they fell.
export default function MatchEvents({ events = [], testid = "live-events", score, phase = "live", status, home = "Home", away = "Away", order, emptyText, show }) {
  if (!events.length) return <EmptyState icon="activity" title="No events yet" testid={`${testid}-empty`}>{emptyText || "Goals, cards and substitutions appear here as they happen."}</EmptyState>;
  // The filter runs after the timeline is built, so the running score and the dividers still come from every goal.
  const rows = buildTimeline(events, { score, phase, status }).filter((r) => r.div || !show || show(r.kind));
  const newest = (order || (phase === "live" ? "newest" : "oldest")) === "newest";
  if (newest) rows.reverse();
  return (
    <div className="tl" data-testid={`${testid}-wrap`}>
      <div className="tl-head" aria-hidden="true"><span>{home}</span><span>{away}</span></div>
      <ol className="tl-list" aria-label={newest ? "Match events, newest first" : "Match events, in order"} data-testid={testid}>
        {rows.map((e, i) => <Row key={e.div ? `d-${e.div}` : `${e.order}-${e.kind}-${i}`} e={e} i={i} testid={testid} names={{ home, away }} />)}
      </ol>
    </div>
  );
}

// Goals and cards per quarter-hour for each side -- what the feed can honestly say about who was pushing.
// Substitutions are left out (they are the bench's decision, not the run of play). Only drawn from three
// events up (docs/redesign/README: data gaps).
export function Momentum({ events, testid = "momentum", home = "Home", away = "Away" }) {
  const ev = events.map(normEvent).filter((e) => e.side && e.base != null && e.kind !== "sub");
  if (ev.length < 3) return null;
  const last = Math.max(90, ...ev.map((e) => e.base));
  const n = Math.ceil(last / 15);
  const bins = Array.from({ length: n }, (_, i) => {
    const xs = ev.filter((e) => Math.min(n - 1, Math.floor((e.base - 1) / 15)) === i);
    return [xs.filter((e) => e.side === "home").length, xs.filter((e) => e.side === "away").length];
  });
  const max = Math.max(1, ...bins.flat());
  const sum = bins.map(([h, a], i) => `${i * 15}-${(i + 1) * 15}': ${home} ${h}, ${away} ${a}`).join("; ");
  return (
    <figure className="tl-mo" data-testid={testid}>
      <figcaption>Goals and cards by quarter-hour</figcaption>
      <div className="tl-mo-bars" role="img" aria-label={`Goals and cards by quarter-hour. ${sum}`}>
        {bins.map(([h, a], i) => (
          <span key={i} className="tl-mo-bin" aria-hidden="true">
            <i className="tl-mo-h" style={{ height: `${(h / max) * 100}%` }} />
            <i className="tl-mo-a" style={{ height: `${(a / max) * 100}%` }} />
          </span>
        ))}
      </div>
      <div className="tl-mo-key" aria-hidden="true"><span className="tl-mo-kh">{home} up</span><span className="tl-mo-ka">{away} down</span></div>
    </figure>
  );
}
