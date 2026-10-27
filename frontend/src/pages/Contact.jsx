// Contact (docs/13 §2): a plain message form. Staff read messages in Admin > Inbox; no auto-reply is sent.
import { useEffect, useState } from "react";
import { post } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useTitle } from "../components/Football";
import { FormError } from "../components/Ui";
import Icon from "../components/Icon";

export default function Contact() {
  const { user } = useAuth();
  useTitle("Contact");
  const [f, setF] = useState({ name: user?.display_name || "", email: user?.email || "", message: "" });
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [err, setErr] = useState(null);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  useEffect(() => { if (user) setF((x) => ({ ...x, name: x.name || user.display_name || "", email: x.email || user.email || "" })); }, [user]);
  const send = async (e) => {
    e.preventDefault();
    setBusy(true); setErr(null);
    try { await post("/contact", f); setDone(true); } catch (x) { setErr(x); }
    setBusy(false);
  };
  return (
    <section className="contact" data-testid="contact-page">
      <h1>Contact us</h1>
      <p className="muted lead">Questions about the data, your account or a payment. We reply by e-mail, usually within two working days.</p>
      {done ? <p className="link-page-ok card" role="status" data-testid="contact-done"><Icon name="check" size={18} />Thanks, your message is with us. We'll reply to {f.email}.</p> : (
        <form className="card contact-form" onSubmit={send} data-testid="contact-form">
          <label className="field"><span>Your name (optional)</span><input value={f.name} onChange={set("name")} maxLength={80} autoComplete="name" data-testid="contact-name" /></label>
          <label className="field"><span>Your e-mail</span><input type="email" required value={f.email} onChange={set("email")} maxLength={254} autoComplete="email" data-testid="contact-email" /></label>
          <label className="field"><span>Message</span><textarea required rows={6} value={f.message} onChange={set("message")} maxLength={4000} data-testid="contact-message" /><small className="muted">{f.message.length} / 4000</small></label>
          <FormError error={err} />
          <button className="btn btn--primary" disabled={busy || f.message.trim().length < 5} data-testid="contact-submit">{busy ? "Sending…" : "Send message"}</button>
          <p className="muted small">Never send passwords or card numbers.</p>
        </form>
      )}
    </section>
  );
}
