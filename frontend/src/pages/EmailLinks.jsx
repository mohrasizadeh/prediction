// Pages opened from e-mail links. A GET only shows who the link is for; the button makes the change (mail scanners open links).
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { post } from "../lib/api";
import { useApi } from "../lib/useApi";
import { ErrorBox, Loading } from "../components/States";
import Icon from "../components/Icon";

function LinkPage({ title, q, doneText, action, label, testid, ask }) {
  const [state, setState] = useState(null);
  const [err, setErr] = useState(null);
  const go = async () => { setState("busy"); setErr(null); try { await action(); setState("done"); } catch (x) { setErr(x); setState(null); } };
  return (
    <section className="link-page card" data-testid={testid}>
      <h1>{title}</h1>
      {q.loading ? <Loading rows={1} /> : q.error ? <><ErrorBox error={q.error} /><Link to="/" className="btn btn--secondary">Go to the home page</Link></> : state === "done" ? (
        <><p className="link-page-ok" data-testid={`${testid}-done`}><Icon name="check" size={18} />{doneText}</p><Link to="/" className="btn btn--secondary">Go to the home page</Link></>
      ) : (
        <><p>{ask(q.data?.email)}</p>{err && <ErrorBox error={err} />}
          <button className="btn btn--primary" onClick={go} disabled={state === "busy"} data-testid={`${testid}-button`}>{label}</button></>
      )}
    </section>
  );
}

export function NewsletterConfirm() {
  const [sp] = useSearchParams();
  const token = sp.get("token") || "";
  const q = useApi(token ? "/newsletter/confirm" : null, { token });
  return <LinkPage title="Confirm your sign-up" q={token ? q : { error: { message: "This link has expired or was already used." } }} testid="newsletter-confirm"
                   ask={(e) => `Add ${e} to the weekly forecast e-mail?`} label="Yes, add me" doneText="You're on the list. The next weekly e-mail will reach you."
                   action={() => post("/newsletter/confirm", { token })} />;
}

export function Unsubscribe() {
  const [sp] = useSearchParams();
  const t = sp.get("t") || "";
  const q = useApi(t ? "/email/unsubscribe" : null, { t });
  return <LinkPage title="Unsubscribe" q={t ? q : { error: { message: "This link is not valid." } }} testid="unsubscribe"
                   ask={(e) => `Stop non-essential e-mails to ${e}? Account and payment e-mails still arrive.`} label="Unsubscribe" doneText="Done. You won't get these e-mails any more."
                   action={() => post("/email/unsubscribe", { t })} />;
}
