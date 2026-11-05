// Compare two clubs (update pack part A, docs/24 §9): search pickers with a swap, "as a fixture" toggle,
// radar first, edge bars that lean to the better side, and "What stands out".
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { get } from "../lib/api";
import { useApi } from "../lib/useApi";
import { Crest } from "../components/Media";
import TeamRadar from "../components/TeamRadar";
import { useTitle } from "../components/Football";
import Icon from "../components/Icon";
import { EmptyState, ErrorState, Segmented, Skeleton } from "../components/ui";

function Picker({ side, team, onPick }) {
  const [q, setQ] = useState("");
  const [rows, setRows] = useState([]);
  useEffect(() => {
    if (q.trim().length < 2) { setRows([]); return undefined; }
    const t = setTimeout(() => get("/search", { q: q.trim() }).then((r) => setRows(r.teams || [])).catch(() => setRows([])), 200);
    return () => clearTimeout(t);
  }, [q]);
  return (
    <div className="cp-pick" data-testid={`compare-pick-${side}`}>
      {team ? <div className="cp-team"><Crest team={team} size={44} /><b>{team.name}</b></div> : <p className="muted">Pick a club</p>}
      <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search a club" aria-label={`Search club ${side === "a" ? "one" : "two"}`} data-testid={`compare-search-${side}`} />
      {rows.length > 0 && <ul className="cp-results">{rows.map((t) => <li key={t.id}><button type="button" onClick={() => { onPick(t.id); setQ(""); }} data-testid={`compare-result-${side}-${t.id}`}><Crest team={t} size={22} />{t.name}</button></li>)}</ul>}
    </div>
  );
}

function Edges({ edges, a, b }) {
  return (
    <ul className="cp-edges" data-testid="compare-edges">
      {edges.map((e) => {
        const tot = (e.a || 0) + (e.b || 0) || 1;
        return (
          <li key={e.key} className={`lean-${e.lean || "none"}`}>
            <b>{e.a}</b>
            <span className="cp-edge-mid"><small>{e.label}{e.lean ? `, edge to ${e.lean === "a" ? a : b}` : ""}</small>
              <span className="cp-edge-bar" aria-hidden="true"><i className="ea" style={{ width: `${(e.a / tot) * 100}%` }} /><i className="eb" style={{ width: `${(e.b / tot) * 100}%` }} /></span></span>
            <b>{e.b}</b>
          </li>
        );
      })}
    </ul>
  );
}

export default function Compare() {
  const [sp, setSp] = useSearchParams();
  const a = sp.get("a") || "", b = sp.get("b") || "";
  const window = sp.get("window") || "season";
  const fixture = sp.get("as_fixture") === "1";
  const set = (k, v) => { const n = new URLSearchParams(sp); if (v) n.set(k, v); else n.delete(k); setSp(n, { replace: true }); };
  const ready = a && b && a !== b;
  const q = useApi(ready ? "/teams/compare" : null, { a, b, window, as_fixture: fixture });
  const d = ready ? q.data : null;
  const one = useApi(a && !ready ? `/teams/${a}` : null);
  // CRITIQUE: landing cold, this page showed two empty search boxes and an empty state whose advice
  // was to go to a different page. A tool that asks for two decisions before it shows anything is
  // the "answer first, ask second" rule broken harder than anywhere else in the product. When a
  // reader arrives with nothing chosen we fill both sides from the next fixture, so the page opens
  // with a real comparison they can change rather than a form they must complete.
  const seed = useApi(!a && !b ? "/fixtures" : null, { date: new Date().toISOString().slice(0, 10) });
  useEffect(() => {
    if (a || b) return;
    const first = Array.isArray(seed.data) ? seed.data.find((m) => m.home?.id && m.away?.id) : null;
    if (!first) return;
    const n = new URLSearchParams(sp);
    n.set("a", first.home.id); n.set("b", first.away.id);
    setSp(n, { replace: true });
  }, [seed.data, a, b, sp, setSp]);
  const soloA = one.data?.team;
  useTitle(d ? `${d.a.team.name} v ${d.b.team.name}` : "Compare");
  const swap = () => { const n = new URLSearchParams(sp); n.set("a", b); n.set("b", a); setSp(n, { replace: true }); };
  return (
    <section className="cp" data-testid="compare-page">
      <h1>Compare</h1>
      <div className="cp-hero">
        <Picker side="a" team={d?.a.team || soloA} onPick={(id) => set("a", id)} />
        <button type="button" className="k-icon-btn cp-swap" onClick={swap} disabled={!a || !b} aria-label="Swap clubs" data-testid="compare-swap"><Icon name="refresh" size={20} /></button>
        <Picker side="b" team={d?.b.team} onPick={(id) => set("b", id)} />
      </div>
      <div className="cp-controls">
        <Segmented options={[{ id: "season", label: "Season" }, { id: "last5", label: "Last 5" }]} value={window} onChange={(v) => set("window", v === "season" ? "" : v)} label="Games" testid="compare-window" />
        <label className="cp-fixture"><input type="checkbox" checked={fixture} onChange={(e) => set("as_fixture", e.target.checked ? "1" : "")} data-testid="compare-as-fixture" />
          <span>{d ? `As a fixture: ${d.a.team.name} at home vs ${d.b.team.name} away` : "As a fixture (first club at home)"}</span></label>
      </div>
      {!ready ? <EmptyState icon="users" title="Pick two clubs" testid="compare-empty">Search a club on each side, or tick two clubs in a league's Teams tab.</EmptyState>
        : q.loading && !q.data ? <Skeleton shape="card" count={2} testid="compare-loading" />
        : q.error ? <ErrorState message="We could not load this comparison." onRetry={q.reload} testid="compare-error" />
        : !d ? <Skeleton shape="card" count={2} testid="compare-loading" />
        : !d.a.row || !d.b.row ? <EmptyState icon="shield" title="Not enough matches yet" testid="compare-no-data">One of these clubs has no finished matches this season for this view.</EmptyState>
        : (
          <div className="cp-body">
            <div className="card cp-radar"><TeamRadar axes={d.radar} aName={d.a.team.name} bName={d.b.team.name} />
              {!d.same_league && <p className="muted small">Different leagues: each club is placed within its own league.</p>}</div>
            <div className="cp-side">
              {d.stands_out.length > 0 && <div className="card cp-out" data-testid="compare-stands-out"><h2 className="k-sec">What stands out</h2><ul>{d.stands_out.map((s) => <li key={s}>{s}</li>)}</ul></div>}
              <div className="card"><h2 className="k-sec">Per game · {d.a.team.name} v {d.b.team.name}</h2><Edges edges={d.edges} a={d.a.team.name} b={d.b.team.name} /></div>
            </div>
          </div>
        )}
    </section>
  );
}
