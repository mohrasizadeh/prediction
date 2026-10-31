// The combo bar and the review sheet (docs/28 §1, boards 4, 5, 6, 8). Mounted once in Layout.
// The bar floats above the phone tab bar; on a computer it is a card in the bottom right corner.
import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { ApiError, post, put } from "../lib/api";
import { comboText, drawCard, useCombo } from "../lib/combo";
import { pct } from "../lib/copy";
import { useAuth } from "../lib/auth";
import Icon from "./Icon";
import { Crest, PlayerAvatar } from "./Media";
import { BottomSheet } from "./ui";

// The combined chance for the lines in the open combo. Waits 150 ms so quick taps make one request.
export function useEstimate(fkeys) {
  const [s, setS] = useState({ est: null, error: null, busy: false });
  const key = fkeys.join("|");
  useEffect(() => {
    if (!fkeys.length) { setS({ est: null, error: null, busy: false }); return undefined; }
    const ac = new AbortController();
    setS((x) => ({ ...x, busy: true, error: null }));
    const t = setTimeout(() => {
      post("/combo/estimate", { fkeys }).then((est) => !ac.signal.aborted && setS({ est, error: null, busy: false }))
        .catch((error) => !ac.signal.aborted && setS((x) => ({ est: error.status === 409 || error.status === 404 ? null : x.est, error, busy: false })));
    }, 150);
    return () => { ac.abort(); clearTimeout(t); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return s;
}

const who = (l) => l.player?.name || l.team?.name || "";
export const lineWhen = (iso) => (iso ? new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : iso + "Z").toLocaleString(undefined, { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : "");

function Face({ l, size = 28 }) {
  return l.player ? <PlayerAvatar player={l.player} size={size} /> : <Crest team={l.team} size={size} />;
}

function Alternatives({ line, lines, onPick }) {
  const opts = [{ fkey: line.fkey, market: line.market, p: line.p }, ...line.more].sort((a, b) => b.p - a.p);
  const [res, setRes] = useState({});
  const keys = opts.map((o) => o.fkey).join("|");
  const others = lines.filter((l) => l.fkey !== line.fkey).map((l) => l.fkey);
  useEffect(() => {
    let live = true;
    Promise.all(opts.map((o) => post("/combo/estimate", { fkeys: [...others, o.fkey] }).then((e) => [o.fkey, e.combined]).catch(() => [o.fkey, null])))
      .then((r) => live && setRes(Object.fromEntries(r)));
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [keys, others.join("|")]);
  return (
    <div className="cb-alt" data-testid="combo-alt">
      <p className="small muted">Change the line. The combo would be:</p>
      <div className="cb-alt-row">{opts.map((o) => (
        <button key={o.fkey} type="button" className={"cb-opt" + (o.fkey === line.fkey ? " on" : "")} aria-pressed={o.fkey === line.fkey} onClick={() => o.fkey !== line.fkey && onPick(o)} data-testid={`combo-opt-${o.fkey}`}>
          <b>{o.market}</b><small>{pct(o.p)}{res[o.fkey] != null ? ` · combo ${pct(res[o.fkey])}` : ""}</small>
        </button>))}
      </div>
    </div>
  );
}

function Review() {
  const { combo, setOpen, clear, swap, toggle } = useCombo();
  const { est, error, busy } = useEstimate((combo?.lines || []).map((l) => l.fkey));
  const [openRow, setOpenRow] = useState(null);
  const [saved, setSaved] = useState(null);
  const [note, setNote] = useState(null);
  const [saving, setSaving] = useState(false);
  const lineBy = Object.fromEntries((est?.lines || []).map((l) => [l.fkey, l]));
  const when = est ? lineWhen(est.kickoff) : "";

  const save = async () => {
    setSaving(true); setNote(null);
    try { const r = await put("/me/combos", { fkeys: combo.lines.map((l) => l.fkey) }); setSaved(r); }
    catch (e) { if (!(e instanceof ApiError) || e.status !== 401) setNote(e.message || "We could not save that."); }
    setSaving(false);
  };
  const copy = async () => { try { await navigator.clipboard.writeText(comboText(est, est.label)); setNote("Copied."); } catch { setNote("Your browser did not let us copy. Select the text instead."); } };
  const share = async () => {
    try {
      const blob = await drawCard(est, est.label, when);
      const file = new File([blob], "combo.png", { type: "image/png" });
      if (navigator.canShare?.({ files: [file] })) await navigator.share({ files: [file], title: "My combo" });
      else { const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = "combo.png"; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 2000); }
    } catch (e) { if (e?.name !== "AbortError") setNote("We could not make the picture."); }
  };
  if (!combo) return null;
  const weakest = est?.weakest;
  return (
    <BottomSheet open title="Your combo" onClose={() => setOpen(false)} testid="combo-sheet"
      footer={<div className="cb-actions">
        {saved ? <Link to="/combos" className="btn btn--primary" onClick={() => setOpen(false)} data-testid="combo-saved-link">Saved. Open My combos</Link>
          : <button type="button" className="btn btn--primary" disabled={!est || saving} onClick={save} data-testid="combo-save">{saving ? "Saving…" : "Save combo"}</button>}
        <div className="cb-actions-row">
          <button type="button" className="btn btn--secondary" disabled={!est} onClick={copy} data-testid="combo-copy"><Icon name="copy" size={18} />Copy as text</button>
          <button type="button" className="btn btn--secondary" disabled={!est} onClick={share} data-testid="combo-share"><Icon name="download" size={18} />Share image</button>
        </div>
        <button type="button" className="k-link" onClick={clear} data-testid="combo-clear">Clear combo</button>
      </div>}>
      {error && !est && <p className="cb-err" role="alert" data-testid="combo-error">{error.message}</p>}
      <div className="cb-hero" data-testid="combo-hero" aria-busy={busy}>
        <div><small className="k-sec">All {combo.lines.length} line{combo.lines.length === 1 ? "" : "s"} together</small><b className="cb-big" data-testid="combo-big">{est ? pct(est.combined) : "–"}</b></div>
        <div className="cb-hero-r"><b>{est?.plain || ""}</b>{est && <small>Range {Math.round(est.range.lo * 100)} to {Math.round(est.range.hi * 100)}%</small>}</div>
        <span className="cb-track" aria-hidden="true">{est && <><i className="cb-rg" style={{ left: `${est.range.lo * 100}%`, width: `${(est.range.hi - est.range.lo) * 100}%` }} /><i className="cb-mark" style={{ left: `${est.combined * 100}%` }} /></>}</span>
        {est?.state === "pre" && <small className="muted">Lineups are not out, so we add a small correction. We tested it on 237,000 real combinations.</small>}
      </div>
      <ul className="cb-lines">
        {combo.lines.map((l) => {
          const e = lineBy[l.fkey];
          const sub = e ? (e.scope === "player" ? `${pct(e.p)} if he plays · ${pct(e.p_play)} to play` : "Team line") : "";
          const on = openRow === l.fkey;
          return (
            <li key={l.fkey} className="cb-line" data-testid={`combo-line-${l.fkey}`}>
              <div className="cb-line-row">
                <button type="button" className="cb-line-main" onClick={() => setOpenRow(on ? null : l.fkey)} aria-expanded={on} aria-label={`${who(e || l)}, ${l.market}. Change the line`}>
                  <Face l={e || l} size={36} />
                  <span className="cb-line-t"><b>{who(e || l)} · {l.market}</b><small>{sub}</small>{weakest && e && e.id === weakest && combo.lines.length > 1 && <span className="cb-weak">Weakest line</span>}</span>
                  <b className="cb-line-p">{e ? pct(e.chance) : pct(l.p)}</b>
                </button>
                <button type="button" className="cb-x" aria-label={`Remove ${who(e || l)} ${l.market}`} onClick={() => toggle({ ...l, match_iid: combo.match_iid, player_iid: undefined })} data-testid={`combo-remove-${l.fkey}`}><Icon name="x" size={18} /></button>
              </div>
              {on && l.more.length > 0 && <Alternatives line={l} lines={combo.lines} onPick={(o) => { swap(l.fkey, o); setOpenRow(o.fkey); }} />}
            </li>
          );
        })}
      </ul>
      {(est?.notes || []).map((n) => <p key={n} className="cb-note" data-testid="combo-note"><Icon name="info" size={16} />{n}</p>)}
      {note && <p className="small muted" role="status" data-testid="combo-flash">{note}</p>}
    </BottomSheet>
  );
}

function SwitchAsk() {
  const { ask, setAsk, confirmAsk, combo, setOpen } = useCombo();
  const { est } = useEstimate(ask && combo ? combo.lines.map((l) => l.fkey) : []);
  const { user } = useAuth();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  if (!ask) return null;
  const saveFirst = async () => {
    setBusy(true); setErr(null);
    try { if (!user) { setOpen(true); setAsk(null); return; } await put("/me/combos", { fkeys: combo.lines.map((l) => l.fkey) }); confirmAsk(); }
    catch (e) { setErr(e.message || "We could not save it."); }
    setBusy(false);
  };
  return (
    <BottomSheet open title="Start a new combo?" onClose={() => setAsk(null)} testid="combo-switch"
      footer={<div className="cb-actions">
        <button type="button" className="btn btn--primary" onClick={saveFirst} disabled={busy} data-testid="combo-switch-save">{user ? "Save it, then start the new one" : "Open it so I can save it"}</button>
        <button type="button" className="btn btn--secondary" onClick={confirmAsk} data-testid="combo-switch-new">Start a new combo</button>
        <button type="button" className="k-link" onClick={() => setAsk(null)} data-testid="combo-switch-keep">Keep my open combo</button>
      </div>}>
      <p>Each combo stays inside one match. Your open combo has {combo?.lines.length} line{combo?.lines.length === 1 ? "" : "s"} from {est?.label || "another match"}{est ? `, ${pct(est.combined)} together` : ""}.</p>
      {err && <p className="cb-err" role="alert">{err}</p>}
    </BottomSheet>
  );
}

export default function ComboHost() {
  const { combo, count, setOpen, open, flash } = useCombo();
  const { pathname } = useLocation();
  const { est, busy } = useEstimate((combo?.lines || []).map((l) => l.fkey));
  const prev = useRef(null);
  const [pulse, setPulse] = useState(false);
  useEffect(() => { if (est && prev.current != null && prev.current !== est.combined) { setPulse(true); const t = setTimeout(() => setPulse(false), 500); return () => clearTimeout(t); } prev.current = est?.combined ?? null; return undefined; }, [est]);
  useEffect(() => { prev.current = est?.combined ?? null; }, [est]);
  useEffect(() => { document.body.classList.toggle("has-combo", count > 0); return () => document.body.classList.remove("has-combo"); }, [count]);
  const hide = /^\/(admin|sign-|forgot|reset|verify|confirm|enroll|change-password|combos)/.test(pathname);
  const openIt = useCallback(() => setOpen(true), [setOpen]);
  return (
    <>
      {count > 0 && !hide && (
        <button type="button" className={"cb-bar" + (pulse ? " cb-bar--pulse" : "")} onClick={openIt} aria-label={`Review your combo: ${count} lines${est ? `, ${pct(est.combined)} together` : ""}`} data-testid="combo-bar">
          <span className="cb-faces">{combo.lines.slice(0, 4).map((l) => <span key={l.fkey}><Face l={(est?.lines || []).find((x) => x.fkey === l.fkey) || l} size={26} /></span>)}</span>
          <span className="cb-bar-t"><b data-testid="combo-bar-text">{count} line{count === 1 ? "" : "s"} · {est ? pct(est.combined) : busy ? "…" : "–"}</b><small>{est ? `${est.plain}${est.state === "pre" ? " · before lineups" : ""}` : "Working it out"}</small></span>
          <span className="cb-bar-go">Review<Icon name="check" size={16} /></span>
        </button>
      )}
      {flash && <div className="cb-flash" role="status" data-testid="combo-limit">{flash}</div>}
      {open && <Review />}
      <SwitchAsk />
    </>
  );
}
