// Footer e-mail sign-up with a consent tick box (docs/16 §4). Same answer for every address, so the list can't be probed.
import { useState } from "react";
import { post } from "../lib/api";
import { useApi } from "../lib/useApi";

export default function NewsletterForm() {
  const s = useApi("/public/settings");
  const [email, setEmail] = useState("");
  const [ok, setOk] = useState(false);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(null);
  const [err, setErr] = useState(null);
  const text = s.data?.["newsletter.consent_text"];
  if (!text) return null;
  const send = async (e) => {
    e.preventDefault();
    setBusy(true); setErr(null);
    try { const r = await post("/newsletter/subscribe", { email, consent: ok }); setDone(r.message); }
    catch (x) { setErr(x.message); }
    setBusy(false);
  };
  return (
    <section className="nl" aria-label="E-mail list" data-testid="newsletter-form">
      <div className="nl-copy"><h3>The weekly forecast e-mail</h3><p>One short e-mail a week with the strongest statistical reads and the reasons behind them.</p></div>
      {done ? <p className="nl-done" role="status" data-testid="newsletter-done">{done}</p> : (
        <form onSubmit={send}>
          <div className="nl-row">
            <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Your e-mail" aria-label="Your e-mail" autoComplete="email" maxLength={254} data-testid="newsletter-email" />
            <button className="btn btn--primary" disabled={busy || !ok} data-testid="newsletter-submit">{busy ? "Sending" : "Sign me up"}</button>
          </div>
          <label className="pop-consent"><input type="checkbox" checked={ok} onChange={(e) => setOk(e.target.checked)} data-testid="newsletter-consent" /><span>{text}</span></label>
          {err && <p className="form-error" role="alert" data-testid="newsletter-error">{err}</p>}
        </form>
      )}
    </section>
  );
}
