// Endpoint explorer (docs/10 §3.10): run an allowed PitchAPI call through the server's cache, see cached or real,
// the cost in calls, and the raw JSON. Force refresh spends a real call. Save as fixture downloads the JSON.
import { useEffect, useRef, useState } from "react";
import { post } from "../lib/api";
import { Confirm, Field, FormError } from "../components/Ui";
import Icon from "../components/Icon";
import { Card, Chip, JsonTree, MissingRoutes, PageHead, notMounted } from "./parts";

const CALLS = [
  { id: "leagues", label: "All leagues and seasons", path: "/v1/leagues", parts: [], params: [] },
  { id: "league", label: "One league", path: "/v1/leagues/{league}", parts: ["league"], params: [] },
  { id: "matches", label: "A league's matches", path: "/v1/leagues/{league}/matches", parts: ["league"], params: [["season", "2025/2026"], ["status", "all"]] },
  { id: "date", label: "Matches on a date", path: "/v1/date/{date}", parts: ["date"], params: [["status", "upcoming"]] },
  { id: "match", label: "One match", path: "/v1/matches/{match}", parts: ["match"], params: [] },
  { id: "players", label: "Match player stats", path: "/v1/matches/{match}/players", parts: ["match"], params: [] },
  { id: "stats", label: "Match team stats", path: "/v1/matches/{match}/stats", parts: ["match"], params: [] },
  { id: "lineups", label: "Match lineups", path: "/v1/matches/{match}/lineups", parts: ["match"], params: [] },
  { id: "h2h", label: "Head to head", path: "/v1/matches/{match}/h2h", parts: ["match"], params: [] },
  { id: "advanced", label: "Advanced team metrics", path: "/v1/matches/{match}/advanced", parts: ["match"], params: [] },
  { id: "advanced_players", label: "Advanced player metrics", path: "/v1/matches/{match}/advanced/players", parts: ["match"], params: [] },
  { id: "team", label: "One team", path: "/v1/teams/{team}", parts: ["team"], params: [] },
  { id: "player", label: "One player", path: "/v1/players/{player}", parts: ["player"], params: [] },
];

export default function Explorer({ head = true }) {
  const [callId, setCallId] = useState("leagues");
  const [vals, setVals] = useState({});
  const [res, setRes] = useState(null);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  const [askForce, setAskForce] = useState(false);
  const outRef = useRef(null);
  useEffect(() => { if (res || err) outRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }); }, [res, err]);
  const call = CALLS.find((c) => c.id === callId);
  const path = call.parts.reduce((p, k) => p.replace(`{${k}}`, encodeURIComponent((vals[k] || "").trim())), call.path);
  const params = Object.fromEntries(call.params.map(([k, d]) => [k, vals[k] ?? d]));
  const ready = call.parts.every((k) => (vals[k] || "").trim());
  const run = async (force = false) => {
    setBusy(true); setErr(null); setAskForce(false);
    try { setRes(await post("/admin/explorer", { path, params, force })); } catch (x) { setErr(x); setRes(null); } finally { setBusy(false); }
  };
  const save = () => {
    const url = URL.createObjectURL(new Blob([JSON.stringify({ path: res.path, params: res.params, data: res.data }, null, 2)], { type: "application/json" }));
    const a = document.createElement("a"); a.href = url; a.download = `fixture${res.path.replace(/\//g, "_")}.json`; a.click(); URL.revokeObjectURL(url);
  };
  return (
    <div className="a-page" data-testid="admin-explorer">
      {head && <PageHead title="Endpoint explorer" lead="Runs one allowed PitchAPI call through the cache. A cached answer costs nothing; a real call counts toward today's budget." />}
      <Card testid="explorer-form">
        <form className="a-form" onSubmit={(e) => { e.preventDefault(); run(false); }}>
          <Field label="Call" as="select" value={callId} onChange={(e) => { setCallId(e.target.value); setRes(null); setErr(null); }} testid="explorer-call">
            {CALLS.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}
          </Field>
          {(call.parts.length > 0 || call.params.length > 0) && (
            <div className="a-form-row">
              {call.parts.map((k) => <Field key={k} label={k === "date" ? "Date (YYYY-MM-DD)" : `${k[0].toUpperCase() + k.slice(1)} id`} value={vals[k] || ""} onChange={(e) => setVals({ ...vals, [k]: e.target.value })} testid={`explorer-${k}`} />)}
              {call.params.map(([k, d]) => k === "status"
                ? <Field key={k} label="Status" as="select" value={vals[k] ?? d} onChange={(e) => setVals({ ...vals, [k]: e.target.value })} testid="explorer-status">{["played", "upcoming", "all"].map((o) => <option key={o}>{o}</option>)}</Field>
                : <Field key={k} label="Season" value={vals[k] ?? d} hint="2025/2026, or 2025 for calendar-year leagues" onChange={(e) => setVals({ ...vals, [k]: e.target.value })} testid={`explorer-${k}`} />)}
            </div>
          )}
          <code className="a-path" data-testid="explorer-path">GET {path}{Object.keys(params).length ? "?" + new URLSearchParams(params) : ""}</code>
          <FormError error={notMounted(err) ? null : err} />
          <div className="a-btns">
            <button className="btn btn--primary" disabled={!ready || busy} data-testid="explorer-run"><Icon name="send" size={16} />{busy ? "Running…" : "Run"}</button>
            <button type="button" className="btn btn--secondary" disabled={!ready || busy} onClick={() => setAskForce(true)} data-testid="explorer-force"><Icon name="refresh" size={16} />Force refresh</button>
          </div>
        </form>
      </Card>
      <div ref={outRef} />
      {notMounted(err) && <MissingRoutes />}
      {res && (
        <Card title="Answer" testid="explorer-result" actions={<button className="btn btn--ghost btn--sm" onClick={save} data-testid="explorer-save"><Icon name="download" size={16} />Save as fixture</button>}>
          <div className="a-btns a-result-meta">
            {res.from_cache ? <Chip tone="up" testid="explorer-source">From cache</Chip> : <Chip tone="warn" testid="explorer-source">Real call</Chip>}
            <Chip testid="explorer-cost">Cost: {res.cost} {res.cost === 1 ? "call" : "calls"}</Chip>
          </div>
          <div className="a-jt-wrap"><JsonTree data={res.data} /></div>
        </Card>
      )}
      <Confirm open={askForce} title="Make a real call?" body="This skips the cache and costs 1 call from today's budget." confirmLabel="Call PitchAPI" onClose={() => setAskForce(false)} onConfirm={() => run(true)} testid="explorer-force-confirm" />
    </div>
  );
}
