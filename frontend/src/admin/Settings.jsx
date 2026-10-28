// Settings (docs/10 §3.11): grouped, searchable, typed inputs, reset to default, history. Owner-only shows a padlock;
// locked settings are read-only with the reason (docs/03 §3). The server type-checks every value.
import { useEffect, useMemo, useState } from "react";
import { del, get, put } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useApi } from "../lib/useApi";
import { Drawer, Switch, useToast } from "../components/Ui";
import { Empty, ErrorBox, Loading } from "../components/States";
import { sayError } from "../lib/errors";
import Icon from "../components/Icon";
import { Chip, KV, PageHead, when } from "./parts";

const LOCKED = { "engine.lineup_effects": "Failed its test on simulated data. Stays off until a real-data backtest passes." };
const enumOpts = (s) => ((s.help || "").split(".")[0].includes("|") ? s.help.split(".")[0].split("|").map((x) => x.trim()) : null);
const toText = (s, v) => (["json", "list"].includes(s.type) ? JSON.stringify(v, null, 2) : v === null || v === undefined ? "" : String(v));

function parse(s, raw) {
  if (s.type === "int") return parseInt(raw, 10);
  if (s.type === "number") return Number(raw);
  if (s.type === "json" || s.type === "list") return JSON.parse(raw);
  return raw;
}

export function Row({ s, canOwner, onSaved, onHistory }) {
  const toast = useToast();
  const [raw, setRaw] = useState(toText(s, s.value));
  const [err, setErr] = useState(null);
  const lockedWhy = LOCKED[s.key];
  const ro = !!lockedWhy || (s.owner_only && !canOwner);
  const dirty = raw !== toText(s, s.value);
  const save = async (val) => {
    setErr(null);
    try { await put(`/admin/settings/${encodeURIComponent(s.key)}`, { value: val }); toast(`Saved ${s.label}`); onSaved(); } catch (x) { setErr(x instanceof SyntaxError ? "That is not valid JSON." : sayError(x)); }
  };
  const reset = async () => { try { await del(`/admin/settings/${encodeURIComponent(s.key)}`); toast("Back to default"); onSaved(); } catch (x) { setErr(sayError(x)); } };
  const opts = s.type === "enum" ? enumOpts(s) : null;
  const tid = `setting-${s.key.replace(/\./g, "-")}`;
  return (
    <div className="a-setting" data-testid={tid}>
      <div className="a-setting-meta">
        <strong>{s.label}{s.owner_only && <Icon name="padlock" size={14} className="a-padlock" />}</strong>
        <code>{s.key}</code>
        {s.help && <p>{s.help}</p>}
        <small className="a-setting-who" data-testid={`${tid}-who`}>Default: <code>{toText(s, s.default).slice(0, 60) || "empty"}</code>{!s.is_default && (s.updated_by || s.updated_at) ? ` · changed by ${s.updated_by || "someone"}${s.updated_at ? ` on ${when(s.updated_at)}` : ""}` : ""}</small>
        <span className="a-setting-tags">{s.public && <Chip>public</Chip>}<Chip>{s.applies_at?.replace(/_/g, " ")}</Chip>{!s.is_default && <Chip tone="brand">changed</Chip>}</span>
        {lockedWhy && <p className="a-padlocked"><Icon name="padlock" size={14} />Locked: {lockedWhy}</p>}
      </div>
      <div className="a-setting-input">
        {s.type === "boolean" ? (
          <Switch label={s.value ? "On" : "Off"} checked={!!s.value} disabled={ro} onChange={(v) => save(v)} testid={`${tid}-input`} />
        ) : opts ? (
          <select value={raw} disabled={ro} onChange={(e) => { setRaw(e.target.value); save(e.target.value); }} aria-label={s.label} data-testid={`${tid}-input`}>{opts.map((o) => <option key={o}>{o}</option>)}</select>
        ) : ["json", "list"].includes(s.type) ? (
          <textarea rows={Math.min(8, raw.split("\n").length + 1)} value={raw} disabled={ro} onChange={(e) => setRaw(e.target.value)} aria-label={s.label} spellCheck={false} data-testid={`${tid}-input`} />
        ) : (
          <input type={["int", "number"].includes(s.type) ? "number" : "text"} step={s.type === "number" ? "any" : undefined} value={raw} disabled={ro} onChange={(e) => setRaw(e.target.value)} aria-label={s.label} data-testid={`${tid}-input`} />
        )}
        {err && <small className="field-err" role="alert">{err}</small>}
        <div className="a-setting-actions">
          {s.type !== "boolean" && !opts && <button className="btn btn--primary btn--sm" disabled={!dirty || ro} onClick={() => { try { save(parse(s, raw)); } catch { setErr("That is not valid JSON."); } }} data-testid={`${tid}-save`}>Save</button>}
          <button className="btn btn--ghost btn--sm" disabled={s.is_default || ro} onClick={reset} data-testid={`${tid}-reset`}>Reset to default</button>
          <button className="btn btn--ghost btn--sm" onClick={() => onHistory(s)} data-testid={`${tid}-history`}>History</button>
        </div>
      </div>
    </div>
  );
}

export function History({ s, onClose }) {
  const [h, setH] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => { if (s) { setH(null); get(`/admin/settings/${encodeURIComponent(s.key)}/history`).then((r) => setH(r.history)).catch(setErr); } }, [s]);
  return (
    <Drawer open={!!s} onClose={onClose} title={`History: ${s?.label || ""}`} testid="setting-history">
      {err ? <ErrorBox error={err} /> : !h ? <Loading /> : h.length === 0 ? <Empty>No changes yet.</Empty> : h.map((r, i) => <KV key={i} obj={r} />)}
    </Drawer>
  );
}

export default function Settings() {
  const q = useApi("/admin/settings");
  const { user } = useAuth();
  const [search, setSearch] = useState("");
  const [group, setGroup] = useState("");
  const [hist, setHist] = useState(null);
  const rows = useMemo(() => q.data || [], [q.data]);
  const groups = useMemo(() => [...new Set(rows.map((r) => r.group))], [rows]);
  const list = rows.filter((r) => (!group || r.group === group) && (r.key + r.label + (r.help || "")).toLowerCase().includes(search.toLowerCase()));
  return (
    <div className="a-page" data-testid="admin-settings">
      <PageHead title="Settings" lead={`${rows.length} settings. Changes are type-checked by the server and recorded.`} />
      <div className="a-filters">
        <div className="a-search"><Icon name="search" size={18} /><input type="search" placeholder="Search settings" aria-label="Search settings" value={search} onChange={(e) => setSearch(e.target.value)} data-testid="settings-search" /></div>
        <select aria-label="Group" value={group} onChange={(e) => setGroup(e.target.value)} data-testid="settings-group"><option value="">All groups</option>{groups.map((g) => <option key={g}>{g}</option>)}</select>
      </div>
      {q.loading && !q.data ? <Loading rows={6} /> : q.error ? <ErrorBox error={q.error} onRetry={q.reload} /> : list.length === 0 ? <Empty>No setting matches.</Empty> : (
        groups.filter((g) => list.some((r) => r.group === g)).map((g) => (
          <section key={g} className="a-card a-settings-group"><h2>{g}</h2>
            {list.filter((r) => r.group === g).map((s) => <Row key={s.key + JSON.stringify(s.value)} s={s} canOwner={user?.role === "owner"} onSaved={q.reload} onHistory={setHist} />)}
          </section>
        ))
      )}
      <History s={hist} onClose={() => setHist(null)} />
    </div>
  );
}
