// Forecast detail sheet (docs/24): every line, the top 3 reasons, chance he plays, lineup status, last 10 games,
// our record on this tier (only once the track record is ready), Save and Share. Reads our own API only.
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { get, put } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { DISCLAIMER, pct, range } from "../../lib/copy";
import { PlayerAvatar, Crest } from "../Media";
import { SaveButton } from "../Actions";
import { BottomSheet } from "./BottomSheet";
import { GameStrip } from "./Marks";
import { QuickView } from "./QuickView";
import { AnswerBlock, LadderList, SubjectHead, WhyList } from "./Subject";
import { answerFor } from "../../lib/lines";
import { STATS, TEAM_HISTORY_STATS } from "../Football";
import { timeOf } from "./ForecastCard";
import { posLabel } from "../Football";

// A match market (match_yellow_cards and the rest) is stored with scope "team" against the home
// side, so scope alone cannot tell a club line from a fixture line. The stat prefix can, and
// Subject.jsx reads it the same way.
const isMatchLine = (f) => !!f.stat?.startsWith("match_");

function useSheetData(open, f) {
  const [d, setD] = useState({ games: null, record: null });
  useEffect(() => {
    if (!open) return undefined;
    let stop = false;
    // Keep the API's rows whole. This used to map each game to a single true/false, which threw away the
    // opponent, the minutes and the figure itself -- everything the strip needs to say more than "yes/no" (docs/45).
    const strip = (r) => { if (!stop) setD((x) => ({ ...x, games: r.games || [] })); };    // team lines only
    // History is fetched by the QuickView below, which can change the stat, the window and the
    // venue; asking for it here as well would be the same call twice (docs/48). That now holds for
    // a club as well as a player, so only a MATCH line still needs the plain strip fetched here --
    // a match line is stored with scope "team" against the home side, but it is about the fixture,
    // not about that club, so there is no entity to interrogate.
    if (isMatchLine(f) && f.team?.id) get(`/teams/${f.team.id}/history`, { stat: f.stat, last: 10 }).then(strip).catch(() => {});
    get("/track-record", { scope: f.scope, stat: f.stat }).then((r) => { if (!stop) setD((x) => ({ ...x, record: r })); }).catch(() => {});
    return () => { stop = true; };
  }, [open, f]);
  return d;
}

function NoteBox({ player, testid }) {
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [msg, setMsg] = useState("");
  useEffect(() => {
    if (!open || !user) return;
    get(`/me/notes/${player.id}`).then((r) => setText(r.text || "")).catch(() => {});
  }, [open, user, player.id]);
  if (!user) return <Link to="/sign-in" className="btn btn--ghost" data-testid={`${testid}-note-signin`}>Note</Link>;
  const save = async () => { try { await put(`/me/notes/${player.id}`, { text }); setMsg("Saved"); } catch (x) { setMsg(x.message || "Could not save"); } };
  return open ? (
    <div className="k-fs-note" data-testid={`${testid}-note`}>
      <label className="sr-only" htmlFor={`${testid}-note-text`}>Your note on {player.name}</label>
      <textarea id={`${testid}-note-text`} rows={3} maxLength={2000} value={text} onChange={(e) => { setText(e.target.value); setMsg(""); }} placeholder={`Your note on ${player.name}`} data-testid={`${testid}-note-text`} />
      <span><button type="button" className="btn btn--primary btn--sm" onClick={save} data-testid={`${testid}-note-save`}>Save note</button>{msg && <small className="k-faint" role="status">{msg}</small>}</span>
    </div>
  ) : <button type="button" className="btn btn--ghost" onClick={() => setOpen(true)} data-testid={`${testid}-note-open`}>Note</button>;
}

const STAT_WORD = { shots: "shots", sot: "on-target", tackles: "tackles", corners: "corners", yellow_cards: "card", match_yellow_cards: "match card" };

export function ForecastSheet({ open, onClose, f, fx, testid = "ui-fsheet" }) {
  const d = useSheetData(open, f);
  // The reader's chosen line. Reported: "changing the lines or filters doesn't reflect on the
  // percentage -- that percentage on the card is fixed for 1+ tackle." The Quick view below knew
  // the answer for every rung and had nowhere to put it, so moving its controls did nothing
  // visible. The sheet owns the choice now, and the headline follows it.
  const [sel, setSel] = useState({ stat: f.stat, line: Math.floor(f.thr) + 1 });
  useEffect(() => { setSel({ stat: f.stat, line: Math.floor(f.thr) + 1 }); }, [f.fkey, f.stat, f.thr]);
  const all = [f, ...(f.more_lines || [])];
  const statLabel = ((f.scope === "team" ? TEAM_HISTORY_STATS : STATS).find((x) => x.id === sel.stat) || {}).label || sel.stat;
  const picked = answerFor(all, sel.stat, sel.line, statLabel);
  // On the line they tapped, the sheet says everything it knows. One rung along, most of what it
  // knows belongs to the other rung: the reasons, the defence sentence, the streak and the season
  // count are all computed per threshold, and carrying them across would attach one line's
  // evidence to another line's number. So they go, and the panel says which line it is answering.
  const onTapped = picked.source === "stored" && picked.fkey === f.fkey;
  const shown = picked.p == null ? f : picked;
  const tier = d.record?.ready && f.tier ? d.record.tiers?.[f.tier] : null;
  const share = async () => {
    const url = f.match_id ? `${window.location.origin}/match/${f.match_id}` : window.location.href;
    const text = `${f.player?.name || fx.team?.name || ""}: ${f.market}, ${pct(f.p)}`;
    try { if (navigator.share) await navigator.share({ title: text, text, url }); else await navigator.clipboard.writeText(`${text} ${url}`); } catch { /* closed */ }
  };
  const lines = [{ fkey: f.fkey, market: f.market, p: f.p, lo: f.lo, hi: f.hi, tier: f.tier }, ...(f.more_lines || [])];
  const rng = f.p_display ? null : range(f.lo, f.hi);
  const title = `${f.player?.name || fx.team?.name || "Forecast"} · ${f.market}`;
  return (
    <BottomSheet open={open} onClose={onClose} title={title} headed testid={testid}
      footer={<>{f.fkey && <SaveButton fkey={f.fkey} />}{f.scope === "player" && f.player?.id && <NoteBox player={f.player} testid={testid} />}<button type="button" className="btn btn--secondary" onClick={share} data-testid={`${testid}-share`}>Share</button></>}>
      {/* The sheet is the player page for most readers -- it is what opens when they tap a card --
          so it leads with the same facts in the same order: who he is, which club, and whether the
          next match is home or away. It used to show only the fixture as plain text. */}
      <SubjectHead f={f} fx={fx} size="sheet" testid={testid} />
      <AnswerBlock f={shown} size="sheet" testid={testid} />
      {!onTapped && <p className="k-faint k-small v2-fs-other" data-testid={`${testid}-other-line`}>
        {picked.source === "ladder"
          ? <>Read off the ladder for this line, so there is no range or tier for it. <button type="button" className="k-link" onClick={() => setSel({ stat: f.stat, line: Math.floor(f.thr) + 1 })} data-testid={`${testid}-back`}>Back to {f.market}</button></>
          : <>Showing {picked.market}. <button type="button" className="k-link" onClick={() => setSel({ stat: f.stat, line: Math.floor(f.thr) + 1 })} data-testid={`${testid}-back`}>Back to {f.market}</button></>}
      </p>}
      {onTapped && <WhyList reasons={f.reasons} testid={`${testid}-why`} />}
      <div className="k-fs-head sr-only" aria-hidden="true" style={{ "--tone": f.tier ? `var(--tier-${f.tier.toLowerCase()})` : "var(--text3)" }}>
        {f.player ? <PlayerAvatar player={f.player} size={52} /> : <Crest team={fx.team} size={52} />}
        <span className="k-fc-who">
          {f.player && (
            <span className="v2-fs-who">
              {/* The sheet answers one line. Everything else a reader wants next -- another market,
                  the season, the notes -- lives on the player page, and there was no way to it from
                  here but the browser's back button. The name is that way. */}
              {f.player?.id && <Link to={`/player/${f.player.id}`} className="v2-fs-name" data-testid={`${testid}-player-link`}>{f.player.name}</Link>}
              {f.pos && <span className="v2-pos">{posLabel(f.pos)}</span>}
              {fx.team && <Link to={`/team/${fx.team.id}`} className="v2-club" onClick={(e) => e.stopPropagation()}><Crest team={fx.team} size={18} /> {fx.team.name}</Link>}
            </span>
          )}
          <small className="k-fs-fx" data-testid={`${testid}-fixture`}>
            {f.team_iid != null && f.home_iid != null && <span className="v2-nextfx-at">{f.team_iid === f.home_iid ? "Home" : "Away"}</span>}
            <span className="k-fs-fx-m">{fx.text}</span>{f.kickoff ? <span className="k-fs-fx-t">{timeOf(f.kickoff)}</span> : null}
          </small>
        </span>
        <span className="k-fc-pwrap"><b className="k-fc-p">{pct(f.p)}</b>{rng && <small className="k-fc-range">{rng}</small>}</span>
      </div>
      {rng && <p className="k-faint k-small sr-only" data-testid={`${testid}-range-note`}>That range is how sure we are: the wider it is, the less sure the forecast.</p>}
      {/* For a player, the full Quick view, opened on the line being looked at: the reader's next question is
          almost always "what about 2+, or only at home", and that used to mean leaving the sheet (docs/48). */}
      {(f.scope === "player" ? f.player?.id : !isMatchLine(f) && f.scope === "team" ? f.team?.id : null) && (
        <>
          {/* AnswerBlock states the likelihood above, so the Quick view must not state it again --
              it was the third printing of the same number in one panel. Filters start closed here:
              a 190px control console is most of a phone screenful inside a modal. */}
          <QuickView playerId={f.scope === "player" ? f.player.id : undefined}
                     teamId={f.scope === "team" ? f.team.id : undefined}
                     stat={f.stat} line={Math.floor(f.thr) + 1} title="The last ten, and any other line"
                     collapsible defaultOpen={false} showForecast={false}
                     value={sel} onChange={setSel}
                     forecasts={all} testid={`${testid}-qv`} />
          <Link to={f.scope === "player" ? `/player/${f.player.id}` : `/team/${f.team.id}`} className="v2-fs-open"
                data-testid={f.scope === "player" ? `${testid}-open-player` : `${testid}-open-team`}>
            Open {(f.scope === "player" ? f.player.name : f.team.name)}&rsquo;s page
          </Link>
        </>
      )}
      {/* A match line has no entity behind it, so it keeps the plain strip. Only when the feed
          carries the stat: a strip of dashes says nothing. */}
      {isMatchLine(f) && d.games?.some((g) => g[f.stat] != null) && (
        <section>
          <h3 className="k-sec">Last {d.games.filter((g) => g[f.stat] != null).length} games · {f.market}</h3>
          <GameStrip games={d.games} stat={f.stat} line={Math.floor(f.thr) + 1} label={f.market} testid={`${testid}-hits`} />
        </section>
      )}
      {/* This paragraph said "A player like him in a fixture like this" for ANY scope -- so a club
          line read "a player ... him" -- and it was the third different label for p_usual, which is
          the entity's OWN rate before this opponent. AnswerBlock states it once, as "Usual". The
          season count stays, over its own window, labelled as the season. */}
      {onTapped && f.scope === "player" && f.rec_n >= 8 && (
        <p className="k-faint k-small k-fs-ctx">
          {/* "This season" was an overclaim: rec_n counts his last 40 appearances, which is not a
              season and in October is nothing like one. Say the window we actually counted. */}
          <span data-testid={`${testid}-rec`}>Reached this line in {f.rec_k} of his last {f.rec_n} appearances.</span>
        </p>
      )}
      <LadderList lines={lines} current={picked.fkey || f.fkey} parent={{ ...f, team: f.team || fx.team }} actions testid={`${testid}-ladder`} />
      {onTapped && tier && tier.n > 0 && <p className="k-fs-record" data-testid={`${testid}-record`}>Our record on {f.tier} {f.scope} {STAT_WORD[f.stat] || f.stat} forecasts: <b>{tier.n >= 100 ? `${Math.round(tier.actual * 100)} of 100` : `${Math.round(tier.actual * tier.n)} of ${tier.n}`}</b> came true{tier.n < 100 ? " so far" : ""}. <Link to={`/track-record?stat=${f.stat}`}>Track record</Link></p>}
      <p className="k-faint k-small">{DISCLAIMER} <Link to="/learn/forecast-card" aria-label="How to read a forecast card" data-testid={`${testid}-learn`}>How to read this card (?)</Link></p>
    </BottomSheet>
  );
}
