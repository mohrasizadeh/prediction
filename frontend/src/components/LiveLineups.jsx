// Lineups: the shared pitch (match page) and the live feed's starters and bench (docs/23, docs/24 "Pitch view").
//
// One pitch for both clubs: home in the top half and away in the bottom half on a phone, the two halves side
// by side on a wide screen. Where a player stands comes from the lineup's own coordinates when it has real ones
// (pitch_x = depth from his own goal, pitch_y = across). API-Football sends none (normalize_af writes pitch_x
// None) and the demo sends every player at 0.5/0.5, so without them the shape is drawn from the formation
// string and each player's line, which every source does carry.
import { Link } from "react-router-dom";
import { Crest, PlayerAvatar } from "./Media";
import { EvIcon } from "./MatchEvents";

// The line a player plays in, whatever the source calls it: PitchAPI position_id 0-3, API-Football "G/D/M/F",
// our own GK/DEF/MID/FWD.
const LINE = { 0: 0, g: 0, gk: 0, goalkeeper: 0, 1: 1, d: 1, def: 1, defender: 1, 2: 2, m: 2, mid: 2, midfielder: 2, 3: 3, f: 3, fwd: 3, att: 3, forward: 3, attacker: 3 };
export const lineOf = (...xs) => { for (const x of xs) { const v = LINE[String(x ?? "").toLowerCase()]; if (v != null) return v; } return null; };

// A short name that still says who he is: the surname, unless the surname is a number or initials.
export const shortName = (name = "") => {
  const t = name.trim().split(/\s+/);
  const last = t[t.length - 1] || "";
  return t.length > 1 && (last.length <= 2 || /^\d+$/.test(last)) ? t.slice(-2).join(" ") : last;
};

function place(players, formation) {
  const xy = players.filter((p) => typeof p.x === "number" && typeof p.y === "number");
  const spread = new Set(xy.map((p) => `${p.x.toFixed(2)}:${p.y.toFixed(2)}`)).size;
  if (xy.length === players.length && spread > players.length / 2) return players.map((p) => ({ ...p, d: p.x, w: p.y }));
  // API-Football's "row:col" grid is the formation itself: row 1 the keeper, one row per line, so a 4-2-3-1
  // keeps its two midfield rows apart even though both call themselves "M".
  const g = players.map((p) => /^(\d+):(\d+)$/.exec(String(p.grid || "")));
  if (players.length && g.every(Boolean)) {
    const by = {}; players.forEach((p, i) => (by[+g[i][1]] = by[+g[i][1]] || []).push({ ...p, c: +g[i][2] }));
    const rows = Object.keys(by).map(Number).sort((a, b) => a - b).map((r) => by[r].sort((a, b) => a.c - b.c));
    const R = rows.length;
    return rows.flatMap((row, r) => row.map((p, j) => ({ ...p, d: R === 1 ? 0.5 : 0.11 + (r * 0.72) / (R - 1), w: 0.1 + (0.8 * (j + 0.5)) / row.length })));
  }
  const ranked = players.map((p, i) => ({ ...p, i, r: p.line ?? 2 })).sort((a, b) => a.r - b.r || a.i - b.i);
  const parts = String(formation || "").split("-").map(Number).filter((n) => n > 0);
  let rows;
  if (parts.length && parts.reduce((a, b) => a + b, 0) + 1 === ranked.length && ranked[0].r === 0) {
    rows = []; let k = 0;
    for (const n of [1, ...parts]) { rows.push(ranked.slice(k, k + n)); k += n; }
  } else {
    const by = {}; ranked.forEach((p) => (by[p.r] = by[p.r] || []).push(p));
    rows = Object.keys(by).sort().map((r) => by[r]);
  }
  const R = rows.length;
  // The keeper sits just off his line and the front row stops short of halfway, so no chip is cut by the
  // pitch edge or runs into the other side's forwards.
  return rows.flatMap((row, r) => row.map((p, j) => ({ ...p, d: R === 1 ? 0.5 : 0.11 + (r * 0.72) / (R - 1), w: 0.1 + (0.8 * (j + 0.5)) / row.length })));
}

function Badges({ b }) {
  if (!b) return null;
  const out = [];
  for (let i = 0; i < (b.goals || 0); i++) out.push(<EvIcon key={`g${i}`} kind="goal" size={14} />);
  for (let i = 0; i < (b.og || 0); i++) out.push(<EvIcon key={`o${i}`} kind="own_goal" size={14} />);
  if (b.red) out.push(<EvIcon key="r" kind={b.yellow ? "second_yellow" : "red"} size={14} />);
  else if (b.yellow) out.push(<EvIcon key="y" kind="yellow" size={14} />);
  const words = [b.goals && `${b.goals} goal${b.goals > 1 ? "s" : ""}`, b.og && "own goal", b.red ? "sent off" : b.yellow && "booked", b.off != null && `off ${b.off}'`].filter(Boolean).join(", ");
  if (!out.length && b.off == null) return null;
  return (
    <>
      {out.length > 0 && <span className="lpv-badges" aria-hidden="true">{out}</span>}
      {b.off != null && <span className="lpv-off" aria-hidden="true"><svg viewBox="0 0 24 24" width="10" height="10"><path d="M12 4v15M6 13l6 6 6-6" /></svg>{b.off}'</span>}
      <span className="sr-only">: {words}</span>
    </>
  );
}

// sides: [{ key: "home"|"away", team, formation, players: [{ key, name, shirt, line, x, y, id, pct, unsure, captain, badges }] }]
export function PitchView({ sides, testid = "pitch" }) {
  return (
    <div className="lpv" data-testid={`${testid}-wrap`}>
      {sides.map((s) => (
        <p key={s.key} className={`lpv-team lpv-team--${s.key}`} data-testid={`${testid}-team-${s.key}`}>
          <Crest team={s.team} size={20} /><b>{s.team?.name}</b>{s.formation && <span className="lpv-form">{s.formation}</span>}
        </p>
      ))}
      <div className="lpv-pitch" data-testid={testid}>
        <span className="lpv-line lpv-line--half" aria-hidden="true" /><span className="lpv-circle" aria-hidden="true" />
        <span className="lpv-box lpv-box--home" aria-hidden="true" /><span className="lpv-box lpv-box--away" aria-hidden="true" />
        {sides.map((s) => (
          <ul key={s.key} className={`lpv-side lpv-side--${s.key}`} aria-label={`${s.team?.name || s.key}${s.formation ? `, ${s.formation}` : ""}`}>
            {place(s.players, s.formation).map((p) => {
              // Depth runs from each side's own goal line to the halfway line; the away side faces the other way.
              const d = s.key === "home" ? p.d * 50 : 100 - p.d * 50;
              const w = s.key === "home" ? p.w * 100 : 100 - p.w * 100;
              const inner = (
                <>
                  <span className="lpv-av">
                    <PlayerAvatar player={{ id: p.id || p.name, name: p.name, image: p.image }} size={34} />
                    {p.shirt != null && p.shirt !== "" && <span className="lpv-shirt" aria-hidden="true">{p.shirt}</span>}
                    {p.captain && <span className="lpv-cap" aria-hidden="true">C</span>}
                  </span>
                  <span className="lpv-name" aria-hidden="true">{shortName(p.name)}</span><span className="sr-only">{p.name}{p.shirt != null && p.shirt !== "" ? `, number ${p.shirt}` : ""}{p.captain ? ", captain" : ""}</span>
                  {p.pct && <span className="lpv-pct">{p.pct}<span className="sr-only"> chance to start</span></span>}
                  <Badges b={p.badges} />
                </>
              );
              const cls = `lpv-p lpv-p--${s.key}${p.unsure ? " lpv-p--unsure" : ""}`;
              const style = { "--d": `${d}%`, "--w": `${w}%` };
              return (
                <li key={p.key} className={cls} style={style} data-testid={`${testid}-player-${p.key}`}>
                  {p.id ? <Link to={`/player/${p.id}`} title={p.name}>{inner}</Link> : <span title={p.name}>{inner}</span>}
                </li>
              );
            })}
          </ul>
        ))}
      </div>
    </div>
  );
}

function Side({ name, block, side }) {
  // Every named player wears his face, here as everywhere else. The lineup feed carries no picture
  // (sportapi.lineups_for returns name, shirt, captain, mins and player_id), so the shared avatar
  // falls back to his initials rather than this file inventing its own.
  const row = (p, i) => (
    <li key={i} className="llu-row"><span className="llu-shirt">{p.shirt ?? ""}</span><PlayerAvatar player={{ id: p.player_id ?? p.name, name: p.name }} size={24} /><span className="llu-name">{p.player_id ? <Link to={`/player/${p.player_id}`}>{p.name}</Link> : p.name}</span>{p.captain && <em className="llu-c" title="Captain" aria-label="Captain">C</em>}</li>
  );
  return (
    <div className={`llu-side llu-side--${side}`} data-testid={`live-lineup-${side}`}>
      <h4 className="llu-head">{name}{block.formation && <span className="lpv-form">{block.formation}</span>}</h4>
      {(block.starters || []).length > 0 && <ol className="llu-list" aria-label={`${name}, starting eleven`}>{block.starters.map(row)}</ol>}
      {(block.subs || []).length > 0 && <><p className="llu-bench">Bench</p><ol className="llu-list llu-list--bench" aria-label={`${name}, bench`}>{block.subs.map(row)}</ol></>}
    </div>
  );
}

// The provider's announced eleven and bench while the match is on. `bench` shows only the substitutes, for the
// Lineups tab where the eleven is already on the pitch.
export default function LiveLineups({ lineups, home, away, bench = false, title, testid = "live-lineups" }) {
  if (!lineups || (!lineups.home && !lineups.away)) return null;
  const only = (b) => (b && bench ? { ...b, starters: [] } : b);
  if (bench && !(lineups.home?.subs || []).length && !(lineups.away?.subs || []).length) return null;
  return (
    <section className="llu-wrap" data-testid={testid}>
      {title !== null && <h3 className="k-sec">{title || (bench ? "Substitutes" : "Lineups from the match feed")}</h3>}
      <div className="llu">
        {lineups.home && <Side name={home} block={only(lineups.home)} side="home" />}
        {lineups.away && <Side name={away} block={only(lineups.away)} side="away" />}
      </div>
    </section>
  );
}
