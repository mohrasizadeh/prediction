// Admin > Engine > Availability (docs/22): per club, mark a player out, doubtful or available, with reason and end date.
import { useState } from "react";
import { put } from "../lib/api";
import { useApi } from "../lib/useApi";
import { useToast } from "../components/Ui";
import { Card, DataState, when } from "./parts";

function Row({ p, onDone }) {
  const toast = useToast();
  const [f, setF] = useState({ status: p.status, reason: p.reason || "", until: p.until ? String(p.until).slice(0, 10) : "" });
  const save = async () => {
    try {
      await put("/admin/availability", { player_id: p.id, status: f.status, reason: f.reason, until: f.until ? `${f.until}T23:59:00Z` : null });
      toast("Saved"); onDone();
    } catch (x) { toast(x.message, "err"); }
  };
  const dirty = f.status !== p.status || f.reason !== (p.reason || "") || f.until !== (p.until ? String(p.until).slice(0, 10) : "");
  return (
    <li className="av-row" data-testid={`av-row-${p.id}`}>
      <span className="av-name"><b>{p.name}</b><small className="a-muted">{p.pos || ""}{p.source ? ` · ${p.source}${p.updated_at ? ` ${when(p.updated_at)}` : ""}` : ""}</small></span>
      <select aria-label={`Status of ${p.name}`} value={f.status} onChange={(e) => setF({ ...f, status: e.target.value })} data-testid={`av-status-${p.id}`}>
        <option value="available">Available</option><option value="doubtful">Doubtful</option><option value="out">Out</option>
      </select>
      <input aria-label="Reason" maxLength={80} placeholder="Reason (public)" value={f.reason} onChange={(e) => setF({ ...f, reason: e.target.value })} disabled={f.status === "available"} data-testid={`av-reason-${p.id}`} />
      <input aria-label="Until" type="date" value={f.until} onChange={(e) => setF({ ...f, until: e.target.value })} disabled={f.status === "available"} data-testid={`av-until-${p.id}`} />
      <button className="btn btn--primary btn--sm" disabled={!dirty} onClick={save} data-testid={`av-save-${p.id}`}>Save</button>
    </li>
  );
}

function Squad({ team }) {
  const q = useApi("/admin/availability", { team });
  return (
    <DataState q={q} empty="No players for this club.">
      {(d) => d.players.length ? <ul className="av-list" data-testid="av-list">{d.players.map((p) => <Row key={p.id} p={p} onDone={q.reload} />)}</ul> : <p className="a-muted">No players for this club.</p>}
    </DataState>
  );
}

export default function Availability() {
  const clubs = useApi("/admin/clubs");
  const [team, setTeam] = useState("");
  return (
    <Card title="Who cannot play" testid="admin-availability">
      <p className="a-muted small">An Out player gets no forecast and his share of shots and tackles goes to team-mates. A Doubtful player's chance to play is halved. A confirmed lineup always wins. The reason shows on the match page, so keep it short and factual. Changes apply when the club's next matches re-run, within a few minutes.</p>
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
