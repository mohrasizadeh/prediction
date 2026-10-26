// Keys (docs/10 §3.12): write-only cards. The browser never sees a saved key, only "•••• 3456". Owner only to change.
import { useState } from "react";
import { del, post, put } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useApi } from "../lib/useApi";
import { Confirm, FormError, useToast } from "../components/Ui";
import { ErrorBox, Loading } from "../components/States";
import Icon from "../components/Icon";
import { Chip, PageHead, when } from "./parts";

function KeyCard({ k, owner, onChange }) {
  const toast = useToast();
  const [val, setVal] = useState("");
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  const [rm, setRm] = useState(false);
  const save = async (e) => {
    e.preventDefault(); setErr(null); setBusy(true);
    try { await put(`/admin/keys/${k.provider}`, { key: val }); setVal(""); toast(`${k.label} saved`); onChange(); } catch (x) { setErr(x); } finally { setBusy(false); }
  };
  const test = async () => {
    try { const r = await post(`/admin/keys/${k.provider}/test`); toast(r?.message || (r?.ok === false ? "The test did not pass" : "Test passed"), r?.ok === false ? "err" : "ok"); } catch (x) { toast(x.message || "Test failed", "err"); }
  };
  return (
    <article className="a-card a-key" data-testid={`key-${k.provider}`}>
      <header className="a-key-head"><span className="a-key-ico"><Icon name="key" size={18} /></span><div><h2>{k.label}</h2><small>{k.hint}</small></div>
        <Chip tone={k.set ? "up" : k.source === "environment" ? "warn" : "muted"}>{k.set ? "Saved" : k.source === "environment" ? "From environment" : "Not set"}</Chip></header>
      <p className="a-key-mask" data-testid={`key-${k.provider}-masked`}>{k.masked || "••••"}</p>
      {k.rotated_at && <small className="a-muted">Changed {when(k.rotated_at)}</small>}
      {owner ? (
        <form className="a-key-form" onSubmit={save}>
          <input type="password" autoComplete="off" spellCheck={false} placeholder={k.set ? "Paste a new key to replace it" : "Paste the key"} value={val} onChange={(e) => setVal(e.target.value)} aria-label={`${k.label} value`} data-testid={`key-${k.provider}-input`} />
          <FormError error={err} />
          <div className="a-btns">
            <button className="btn btn--primary btn--sm" disabled={!val || busy} data-testid={`key-${k.provider}-save`}>Save</button>
            {k.set && <button type="button" className="btn btn--secondary btn--sm" onClick={test} data-testid={`key-${k.provider}-test`}>Test</button>}
            {k.set && <button type="button" className="btn btn--ghost btn--sm" onClick={() => setRm(true)} data-testid={`key-${k.provider}-delete`}>Remove</button>}
          </div>
        </form>
      ) : <p className="a-muted small"><Icon name="padlock" size={14} /> Only the owner can change keys.</p>}
      <Confirm open={rm} danger title={`Remove the ${k.label}?`} body="Anything that uses it stops working until a new key is saved." confirmLabel="Remove" onClose={() => setRm(false)} testid={`key-${k.provider}-confirm`}
               onConfirm={async () => { await del(`/admin/keys/${k.provider}`); setRm(false); toast("Key removed"); onChange(); }} />
    </article>
  );
}

export default function Keys() {
  const q = useApi("/admin/keys");
  const { user } = useAuth();
  return (
    <div className="a-page" data-testid="admin-keys">
      <PageHead title="Keys" lead="Stored encrypted. Never sent back to the browser, never logged. Changing an environment variable needs a redeploy, so use this screen." />
      {q.loading && !q.data ? <Loading rows={6} /> : q.error ? <ErrorBox error={q.error} onRetry={q.reload} /> : (
        <div className="a-key-grid">{q.data.keys.map((k) => <KeyCard key={k.provider} k={k} owner={user?.role === "owner"} onChange={q.reload} />)}</div>
      )}
    </div>
  );
}
