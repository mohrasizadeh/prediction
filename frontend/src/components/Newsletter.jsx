// Weekly e-mail box (docs/24, picture email_footer_dark.png): a concrete promise, a preview built from the
// current top Strong reads, one field and one button, the consent sentence under the button. Same answer for
// every address, so the list can't be probed. Pressing the button with the sentence shown is the consent.
import { useState } from "react";
import { post } from "../lib/api";
import { useApi } from "../lib/useApi";
import { pct } from "../lib/copy";

function Preview() {
  const q = useApi("/insights", { limit: 30 });
  const rows = (q.data || []).filter((x) => x.tier === "Strong").slice(0, 3);
  if (rows.length < 3) return null;
  return (
    <div className="nl-preview" aria-hidden="true" data-testid="newsletter-preview">
      <small className="k-sec">The e-mail · preview</small>
      <b>This week: the strongest reads</b>
      <ul>{rows.map((x) => <li key={x.fkey}><span>{x.player?.name || x.team?.name} {x.market}</span><em style={{ color: `var(--tier-${x.tier.toLowerCase()})` }}>{pct(x.p)}</em></li>)}</ul>
    </div>
  );
}

export default function NewsletterForm() {
  const s = useApi("/public/settings");
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(null);
  const [err, setErr] = useState(null);
  const text = s.data?.["newsletter.consent_text"];
  if (!text) return null;
  const send = async (e) => {
    e.preventDefault();
    setBusy(true); setErr(null);
    try { const r = await post("/newsletter/subscribe", { email, consent: true }); setDone(r.message); }
    catch (x) { setErr(x.message); }
    setBusy(false);
  };
  return (
    <section className="nl nl2" aria-label="E-mail list" data-testid="newsletter-form">
      <div className="nl2-main">
        <span className="nl2-tag">Free · weekly</span>
        <h2>The week's strongest reads, in one e-mail</h2>
        <p>With the reasons behind each one. A 2-minute read. Unsubscribe in one click.</p>
        {done ? <p className="nl-done" role="status" data-testid="newsletter-done">{done}</p> : (
          <form onSubmit={send} className="nl2-form">
            <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" aria-label="Your e-mail" autoComplete="email" maxLength={254} data-testid="newsletter-email" />
            <button className="btn btn--primary" disabled={busy} data-testid="newsletter-submit">{busy ? "Sending" : "Send me the e-mail"}</button>
          </form>
        )}
        {!done && <p className="nl2-consent" data-testid="newsletter-consent-text">{text}</p>}
        {err && <p className="form-error" role="alert" data-testid="newsletter-error">{err}</p>}
      </div>
      <Preview />
    </section>
  );
}
