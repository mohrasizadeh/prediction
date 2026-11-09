// /waitlist (docs/68): the page an advert points at.
//
// It leads with the one claim nobody else in this space can make and this product can CHECK --
// what it said, against what happened, from its own scored record. Everything else on the page is
// an explanation of how that number is arrived at.
//
// The record is read live from /track-record. If it is not ready the page says so and leads with
// the method instead; it never prints a figure it cannot stand behind, which would be a strange
// way to advertise a product whose whole argument is that it does not do that.
//
// Outside the app shell on purpose: someone arriving from a post should meet one page with one
// thing to do, not a navigation bar inviting them elsewhere.
import { useState } from "react";
import { Link } from "react-router-dom";
import { post } from "../lib/api";
import { useApi } from "../lib/useApi";
import { DISCLAIMER, pct } from "../lib/copy";
import { sayError } from "../lib/errors";
import { useSite } from "../lib/site";
import { useTitle } from "../components/Football";
import { BrandLogo } from "../components/Media";

const CONSENT = "Yes, send me the match-day e-mail. I can unsubscribe from any of them.";

function Record({ q }) {
  const d = q.data;
  if (!d?.ready) return null;
  const bands = (d.bins || []).filter((b) => b.from >= 0.6);
  return (
    <section className="wl-rec" data-testid="wl-record">
      <h2>What we said, against what happened</h2>
      <p className="wl-sub">
        Every forecast we publish is scored once the match is over. This is all of them —{" "}
        <b>{d.scored.toLocaleString()}</b> scored so far. Nothing is left out for looking bad.
      </p>
      <ul className="wl-bands">
        {bands.map((b) => (
          <li key={b.from}>
            <span className="wl-band-h">{Math.round(b.from * 100)}–{Math.round(b.to * 100)}%</span>
            <span className="wl-band-n">
              <b>{pct(b.stated)}</b> said
              <i aria-hidden="true">→</i>
              <b>{pct(b.actual)}</b> happened
            </span>
            <small>{b.n.toLocaleString()} scored</small>
          </li>
        ))}
      </ul>
      <p className="wl-note">
        The point is not that the second number is high. It is that the two are <b>close</b>. When we
        say 80%, we want it to happen about 80 times in 100 — not more, which would mean we were
        being timid, and not less, which would mean we were overclaiming.
      </p>
      <Link className="wl-more" to="/track-record" data-testid="wl-to-record">See the whole record →</Link>
    </section>
  );
}

function Form() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [consent, setConsent] = useState(false);
  const [state, setState] = useState("");          // "" | "busy" | "done"
  const [err, setErr] = useState("");

  const submit = async (e) => {
    e.preventDefault();
    setErr("");
    if (!consent) { setErr("Please tick the box so we know you want the e-mail."); return; }
    setState("busy");
    try {
      await post("/newsletter/subscribe", { email, name, consent, source: "waitlist" });
      setState("done");
    } catch (x) { setErr(sayError(x)); setState(""); }
  };

  if (state === "done") {
    return (
      <div className="wl-done" data-testid="wl-done">
        <h3>You are on the list.</h3>
        <p>
          Check your inbox — there may be one e-mail asking you to confirm. After that you will get
          our three strongest forecasts on every match day, with the reasons and the range, until we
          open.
        </p>
      </div>
    );
  }

  return (
    <form className="wl-form" onSubmit={submit} data-testid="wl-form">
      <label className="wl-field">
        <span>First name</span>
        <input value={name} onChange={(e) => setName(e.target.value)} autoComplete="given-name"
          placeholder="So we know what to call you" maxLength={80} data-testid="wl-name" />
      </label>
      <label className="wl-field">
        <span>E-mail</span>
        <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)}
          autoComplete="email" placeholder="you@example.com" maxLength={254} data-testid="wl-email" />
      </label>
      <label className="wl-consent">
        <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} data-testid="wl-consent" />
        <span>{CONSENT}</span>
      </label>
      {err && <p className="wl-err" role="alert" data-testid="wl-err">{err}</p>}
      <button className="btn btn--primary btn--lg" type="submit" disabled={state === "busy"} data-testid="wl-submit">
        {state === "busy" ? "Adding you…" : "Send me the three"}
      </button>
      <p className="wl-small">One e-mail per match day. Unsubscribe in one click. We never pass your address on.</p>
    </form>
  );
}

const HOW = [
  ["A model per player, not a rule of thumb",
   "Every player gets his own fitted distribution for every market — shots, on target, tackles, fouls, cards — built from how often he does it, how much he plays, and how far the count swings from week to week."],
  ["The opponent, by position",
   "A winger facing a side that concedes to wingers is not the same forecast as the same winger facing one that does not. We measure what each opponent gives up, position by position, and move the number for it."],
  ["Whether he actually plays",
   "Every percentage is “if he is on the pitch”. Whether he will be is a separate question with a separate answer, read off how many of his club's last ten he started — never folded into the first number where it could hide."],
  ["Two things together is not two things multiplied",
   "A player's shots and his shots on target happen together far more often than multiplying says. We measured that across 237,000 real combinations and correct for it, which is why our combined numbers differ from the obvious arithmetic."],
];

export default function Waitlist() {
  useTitle("Join the waitlist");
  const { cfg } = useSite();
  const rec = useApi("/track-record");
  const ready = rec.data?.ready;
  const high = rec.data?.high;

  return (
    <div className="wl" data-testid="waitlist-page">
      <header className="wl-top">
        <Link to="/" className="brand" data-testid="wl-brand"><BrandLogo brand={cfg?.brand} /></Link>
      </header>

      <section className="wl-hero">
        {ready && high ? (
          <>
            <p className="wl-kicker">Across {high.n.toLocaleString()} scored forecasts</p>
            <h1>We said {pct(high.stated)}. It happened {pct(high.actual)} of the time.</h1>
            <p className="wl-lead">
              Most football stats tell you what already happened. We tell you what is likely to
              happen next — and then we publish whether we were right. Join the list and we will
              send you the three we are most confident in, every match day, until we open.
            </p>
          </>
        ) : (
          <>
            <p className="wl-kicker">Football forecasts, scored in public</p>
            <h1>What is likeliest to happen tonight — and whether we have been right before.</h1>
            <p className="wl-lead">
              Every forecast we publish is scored once the match ends, and the record is on the site
              for anyone to read. Join the list and we will send you the three we are most confident
              in, every match day, until we open.
            </p>
          </>
        )}
        <Form />
      </section>

      <Record q={rec} />

      <section className="wl-how" data-testid="wl-how">
        <h2>How the engine works</h2>
        <p className="wl-sub">Four things it does that a table of averages cannot.</p>
        <ul className="wl-how-list">
          {HOW.map(([h, b]) => <li key={h}><b>{h}</b><span>{b}</span></li>)}
        </ul>
      </section>

      <section className="wl-hon" data-testid="wl-honest">
        <h2>Three things we do that cost us</h2>
        <ul className="wl-hon-list">
          <li><b>We show the range, not just the number.</b> Every forecast carries the spread around it, so you can see which ones we are sure of and which we are not.</li>
          <li><b>We show nothing under 60%.</b> A coin flip dressed as an insight is worse than an empty screen, so when there is nothing worth showing, the screen says so.</li>
          <li><b>We publish the misses.</b> The record above counts every scored forecast, not a selection of them.</li>
        </ul>
      </section>

      <footer className="wl-foot">
        <p>{DISCLAIMER}</p>
        <p>
          <Link to="/legal/terms">Terms</Link> · <Link to="/legal/privacy">Privacy</Link> ·{" "}
          <Link to="/track-record">Track record</Link>
        </p>
      </footer>
    </div>
  );
}
