// Admin > Engine > Availability (docs/22, docs/24 Admin): pick a club, see the squad as photo cards,
// tap a card to cycle Available, Doubtful, Out; add a reason and an end date in a bottom sheet.
import { useState } from "react";
import { put } from "../lib/api";
import { useApi } from "../lib/useApi";
import { useToast } from "../components/Ui";
import { PlayerAvatar } from "../components/Media";
import { BottomSheet } from "../components/ui";
import { Card, DataState, when } from "./parts";

const NEXT = { available: "doubtful", doubtful: "out", out: "available" };
const LABEL = { available: "Available", doubtful: "Doubtful", out: "Out" };
const day = (u) => (u ? String(u).slice(0, 10) : "");

async function save(p, f) {
  await put("/admin/availability", { player_id: p.id, status: f.status, reason: f.status === "available" ? "" : f.reason, until: f.status !== "available" && f.until ? `${f.until}T23:59:00Z` : null });
}

function Details({ p, onClose, onDone }) {
  const toast = useToast();
  const [f, setF] = useState({ status: p.status, reason: p.reason || "", until: day(p.until) });
  const go = async () => { try { await save(p, f); toast("Saved"); onDone(); onClose(); } catch (x) { toast(x.message, "err"); } };
  return (
    <BottomSheet open onClose={onClose} title={p.name} testid="av-sheet"
      footer={<><button type="button" className="btn btn--primary" onClick={go} data-testid="av-sheet-save">Save</button><button type="button" className="btn btn--ghost" onClick={onClose} data-testid="av-sheet-cancel">Cancel</button></>}>
      <div className="av-seg" role="radiogroup" aria-label="Status">{Object.keys(LABEL).map((s) => (
        <button key={s} type="button" role="radio" aria-checked={f.status === s} className={`av-seg-btn av--${s}${f.status === s ? " on" : ""}`} onClick={() => setF({ ...f, status: s })} data-testid={`av-sheet-${s}`}>{LABEL[s]}</button>
      ))}</div>
      <label className="field"><span>Reason (shown on the match page)</span><input maxLength={80} value={f.reason} disabled={f.status === "available"} onChange={(e) => setF({ ...f, reason: e.target.value })} data-testid="av-sheet-reason" /></label>
      <label className="field"><span>Until</span><input type="date" value={f.until} disabled={f.status === "available"} onChange={(e) => setF({ ...f, until: e.target.value })} data-testid="av-sheet-until" /></label>
      {p.source && <p className="a-muted small">Last set by {p.by || p.source}{p.updated_at ? ` on ${when(p.updated_at)}` : ""}</p>}
    </BottomSheet>
  );
}

function PlayerCard({ p, onDone, onOpen }) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const cycle = async () => {
    const status = NEXT[p.status];
    setBusy(true);
    try { await save(p, { status, reason: p.reason || "", until: day(p.until) }); toast(`${p.name}: ${LABEL[status]}`); onDone(); } catch (x) { toast(x.message, "err"); } finally { setBusy(false); }
  };
  return (
    <li className={`av-card av--${p.status}`} data-testid={`av-card-${p.id}`}>
      <button type="button" className="av-card-main" disabled={busy} onClick={cycle} aria-label={`${p.name}, ${LABEL[p.status]}. Tap to change.`} data-testid={`av-cycle-${p.id}`}>
        <PlayerAvatar player={p} size={56} />
        <b>{p.name}</b>
        <small className="a-muted">{p.pos || ""}</small>
        <span className="av-state" data-testid={`av-state-${p.id}`}>{LABEL[p.status]}</span>
        {p.status !== "available" && p.reason && <small className="av-why">{p.reason}{p.until ? ` · until ${day(p.until)}` : ""}</small>}
      </button>
      <button type="button" className="av-card-more" onClick={() => onOpen(p)} data-testid={`av-details-${p.id}`}>Reason and date</button>
    </li>
  );
}

function Squad({ team }) {
  const q = useApi("/admin/availability", { team });
  const [open, setOpen] = useState(null);
  return (
    <DataState q={q} empty="No players for this club.">
      {(d) => d.players.length ? (
        <>
          <ul className="av-grid" data-testid="av-list">{d.players.map((p) => <PlayerCard key={p.id} p={p} onDone={q.reload} onOpen={setOpen} />)}</ul>
          {open && <Details key={open.id} p={open} onClose={() => setOpen(null)} onDone={q.reload} />}
        </>
      ) : <p className="a-muted">No players for this club.</p>}
    </DataState>
  );
}

export default function Availability() {
  const clubs = useApi("/admin/clubs");
  const [team, setTeam] = useState("");
  return (
    <Card title="Who cannot play" testid="admin-availability">
      <p className="a-muted small">Tap a player to cycle Available, Doubtful, Out. An Out player gets no forecast and his share of shots and tackles goes to team-mates. A Doubtful player's chance to play is halved. A confirmed lineup always wins. Changes apply when the club's next matches re-run, within a few minutes.</p>
      <DataState q={clubs} empty="No leagues switched on.">
        {(d) => (
          <select aria-label="Club" value={team} onChange={(e) => setTeam(e.target.value)} data-testid="av-club">
            <option value="">Pick a club</option>
            {d.leagues.map((l) => <optgroup key={l.iid} label={l.name}>{l.teams.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}</optgroup>)}
          </select>
        )}
      </DataState>
      {team && <Squad team={team} />}
    </Card>
  );
}
