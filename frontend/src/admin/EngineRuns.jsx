// Engine runs + markets (GET /admin/engine) and the forecast browser with Hide / Unhide and a reason
// (GET /admin/forecasts, POST /admin/forecasts/{id}/hide). Hidden forecasts never appear on public pages.
import { useState } from "react";
import { post } from "../lib/api";
import { useApi } from "../lib/useApi";
import { Confirm, useToast } from "../components/Ui";
import { Card, Chip, DataState, KV, Pager, ResponsiveTable, when } from "./parts";

const RUN_TONE = { done: "up", skipped: "warn", running: "muted" };

// Why the next two days have the Strong lines they have (GET /admin/engine/tiers, tiering.funnel).
// A line can carry a Strong number and still not be badged Strong: the bottom of its range is too
// low, or our own record on that market is too thin or says lower. This says which.
const HELD = {
  range: "Range too wide: the low end is under the Strong floor",
  record_thin: "Our record on this market is not measured yet",
  record_lower: "Our record says similar lines happened less often",
  ungraded: "This market carries no badge (match goals)",
  other: "Other",
};

function TierCheck() {
  const q = useApi("/admin/engine/tiers", { hours: 48 });
  return (
    <DataState q={q} empty="No forecasts in the next two days.">
      {(d) => (
        <Card title="Strong check, next 48 hours" testid="engine-tiers">
          <div className="a-btns">
            {Object.entries(d.tiers).map(([t, n]) => <Chip key={t} tone={t === "Strong" ? (n ? "up" : "warn") : "muted"} testid={`tiers-${t}`}>{t === "none" ? "No badge" : t}: {n}</Chip>)}
          </div>
          <p className="a-muted small">Strong needs {Math.round(d.rule.strong_min * 100)}% or more, a low end of {Math.round(d.rule.strong_lo_min * 100)}% or more, and {d.rule.record_min_n} settled lines near 90% in our own record for that market.</p>
          {d.near.length > 0 ? (
            <>
              <KV obj={Object.fromEntries(Object.entries(d.held).filter(([, n]) => n).map(([k, n]) => [HELD[k], `${n} line${n === 1 ? "" : "s"}`]))} />
              <ResponsiveTable testid="tiers-near" rowKey={(r) => r.k} rows={d.near.map((r, i) => ({ ...r, k: `${r.match_iid}-${r.player_iid || r.team_iid}-${i}` }))} columns={[
                { key: "who", label: "Who", primary: true, render: (r) => <b>{r.player_name || r.team_name || "Unknown"}</b> },
                { key: "market", label: "Line" },
                { key: "p", label: "Chance", render: (r) => `${Math.round(r.p * 100)}% (low ${Math.round((r.lo || 0) * 100)}%)` },
                { key: "tier", label: "Badge", render: (r) => r.tier || "None" },
                { key: "why", label: "Held by", render: (r) => HELD[r.why] },
              ]} />
            </>
          ) : <p className="a-muted small">No line in the next two days has a chance of {Math.round(d.rule.strong_min * 100)}% or more.</p>}
          <details>
            <summary>Our record near the Strong cut, by market</summary>
            <KV obj={Object.fromEntries(d.record.map((r) => [`${r.scope} ${r.stat}`, r.n ? `${r.n} settled${r.happened != null ? `, ${Math.round(r.happened * 100)}% happened` : ""}${r.enough ? "" : " (not enough yet)"}` : "None yet"]))} />
          </details>
        </Card>
      )}
    </DataState>
  );
}

export function Runs() {
  const q = useApi("/admin/engine", { limit: 40 });
  const cols = [
    { key: "league_name", label: "League", primary: true, render: (r) => <span className="a-person"><b>{r.league_name || `League ${r.league_iid}`}</b><small>{r.note || ""}</small></span> },
    { key: "status", label: "Status", render: (r) => <Chip tone={RUN_TONE[r.status] || "muted"} testid={`run-status-${r.run_id}`}>{r.status}</Chip> },
    { key: "started_at", label: "Started", render: (r) => when(r.started_at) },
    { key: "forecasts", label: "Forecasts", render: (r) => r.forecasts ?? "None" },
    { key: "matches_in_fit", label: "Matches used", render: (r) => r.matches_in_fit ?? "None" },
  ];
  return (
    <DataState q={q} empty="The engine has not run yet.">
      {(d) => (
        <div className="a-stack">
          <TierCheck />
          <Card title="Markets per switched-on league" testid="engine-markets">
            {d.leagues.length ? d.leagues.map((l) => (
              <details key={l.league_iid} data-testid={`engine-league-${l.league_iid}`}>
                <summary><b>{l.name}</b> <Chip tone={l.forecasts ? "up" : "muted"}>{l.forecasts} current</Chip>{l.hidden > 0 && <Chip tone="warn">{l.hidden} hidden</Chip>}</summary>
                {Object.values(l.markets).some(Boolean) ? <div className="a-btns">{Object.entries(l.markets).map(([m, on]) => <Chip key={m} tone={on ? "up" : "muted"}>{m}{on ? "" : " (off)"}</Chip>)}</div> : <p className="a-muted small">No market switched on yet. Markets turn on when the data coverage is high enough.</p>}
              </details>
            )) : <p className="a-muted small">No league is switched on.</p>}
          </Card>
          <Card title="Recent runs" testid="engine-runs">
            {d.runs.length ? <ResponsiveTable columns={cols} rows={d.runs} rowKey={(r) => r.run_id} testid="engine-runs-table" /> : <p className="a-muted small">The engine has not run yet.</p>}
          </Card>
        </div>
      )}
    </DataState>
  );
}

function Filters({ f, set, leagues }) {
  const ch = (k) => (e) => set({ ...f, [k]: e.target.value, page: 1 });
  return (
    <div className="a-filters">
      <select aria-label="League" value={f.league_iid} onChange={ch("league_iid")} data-testid="fc-league"><option value="">Every league</option>{leagues.map((l) => <option key={l.league_iid} value={l.league_iid}>{l.name}</option>)}</select>
      <select aria-label="Scope" value={f.scope} onChange={ch("scope")} data-testid="fc-scope"><option value="">Teams and players</option><option value="team">Teams</option><option value="player">Players</option></select>
      <select aria-label="Shown or hidden" value={f.hidden} onChange={ch("hidden")} data-testid="fc-hidden"><option value="">Shown and hidden</option><option value="no">Shown</option><option value="yes">Hidden</option></select>
      <input className="a-input" aria-label="Market" placeholder="Market, e.g. 2+ shots" value={f.market} onChange={ch("market")} data-testid="fc-market" />
    </div>
  );
}

export function Forecasts() {
  const toast = useToast();
  const [f, setF] = useState({ league_iid: "", scope: "", hidden: "", market: "", page: 1 });
  const [pick, setPick] = useState(null);
  const [busy, setBusy] = useState(false);
  const meta = useApi("/admin/engine", { limit: 1 });
  const q = useApi("/admin/forecasts", f);
  const cols = [
    { key: "who", label: "Forecast", primary: true, render: (r) => <span className="a-person"><b>{r.player_name || r.team_name || "Unknown"}</b><small>{r.market}</small></span> },
    { key: "kickoff", label: "Kickoff", render: (r) => when(r.kickoff) },
    { key: "p", label: "Likelihood", render: (r) => `${Math.round(r.p * 100)}%` },
    { key: "tier", label: "Tier", render: (r) => r.tier || "None" },
    { key: "x", label: "", render: (r) => <span onClick={(e) => e.stopPropagation()} role="presentation"><button className={"btn btn--sm " + (r.hidden ? "btn--secondary" : "btn--ghost")} onClick={() => setPick(r)} data-testid={`fc-toggle-${r.id}`}>{r.hidden ? "Unhide" : "Hide"}</button></span> },
  ];
  const save = async (reason) => {
    setBusy(true);
    try { await post(`/admin/forecasts/${pick.id}/hide`, { hidden: !pick.hidden, reason }); } finally { setBusy(false); }
    toast(pick.hidden ? "Forecast shown again" : "Forecast hidden"); setPick(null); q.reload();
  };
  return (
    <div className="a-stack" data-testid="engine-forecasts">
      <Filters f={f} set={setF} leagues={meta.data?.leagues || []} />
      <DataState q={q} empty="No current forecasts match these filters.">
        {(d) => <><ResponsiveTable columns={cols} rows={d.rows} onRow={setPick} testid="fc-table" /><Pager page={d.page} limit={d.limit} total={d.total} onPage={(page) => setF({ ...f, page })} /></>}
      </DataState>
      <Confirm open={!!pick} title={pick?.hidden ? "Show this forecast again?" : "Hide this forecast?"} danger={!pick?.hidden}
               body={pick && <><p>{pick.player_name || pick.team_name} · {pick.market}</p>{pick.hidden && <KV obj={{ reason: pick.hidden_reason, by: pick.hidden_by, at: when(pick.hidden_at) }} />}<p className="a-muted small">{pick.hidden ? "It appears on public pages again." : "It disappears from every public page and stays hidden after the next engine run."}</p></>}
               reason={pick?.hidden ? undefined : "Reason (required)"} confirmLabel={pick?.hidden ? "Unhide" : "Hide"}
               busy={busy} onClose={() => setPick(null)} onConfirm={save} testid="fc-confirm" />
    </div>
  );
}
