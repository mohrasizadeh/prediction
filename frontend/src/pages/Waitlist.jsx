// /waitlist (docs/68): the page an advert lands on.
//
// One job: a visitor gives a name and an e-mail in exchange for the three forecasts we are most
// confident in, every match day, until we open.
//
// Outside the app shell on purpose -- someone arriving from a post should meet one page with one
// thing to do, not a navigation bar inviting them elsewhere.
//
// EVERY NUMBER IS READ FROM THE FEED. The proof cards come from /proof (forecasts that were
// published, scored, and came in, with what actually happened), the record from /track-record, and
// the live card from the top of /likely. Nothing is typed in, so the page is different tomorrow
// without anyone touching it -- which is the whole reason it is worth advertising.
//
// The drawing lives in lib/lpfigures.js and runs in an effect once both feeds have arrived. React
// owns the shell and the form; that file owns the geometry.
import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { post } from "../lib/api";
import { useApi } from "../lib/useApi";
import { useSite } from "../lib/site";
import { DISCLAIMER } from "../lib/copy";
import { sayError } from "../lib/errors";
import { useTitle } from "../components/Football";
import { ErrorState, Skeleton } from "../components/ui";
import { paint } from "../lib/lpfigures";

const CONSENT = "Yes, send me the match-day e-mail. I can unsubscribe from any of them.";

function Form() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [consent, setConsent] = useState(false);
  const [state, setState] = useState("");
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
      <div className="form-card" data-testid="wl-done">
        <h2>You are on the list.</h2>
        <p className="fc-sub">
          Check your inbox — there may be one e-mail asking you to confirm. After that you will get
          three forecasts on every match day, each with its range, its lineup word and its last-ten
          run, until we open.
        </p>
      </div>
    );
  }

  return (
    <form className="form-card" onSubmit={submit} noValidate data-testid="wl-form">
      <h2>Three forecasts, every match day</h2>
      <p className="fc-sub">Free while we are in private build. No card, no app to install.</p>
      <label className="field"><span>First name</span>
        <input value={name} onChange={(e) => setName(e.target.value)} autoComplete="given-name"
          maxLength={80} placeholder="So we know what to call you" data-testid="wl-name" /></label>
      <label className="field"><span>E-mail</span>
        <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)}
          autoComplete="email" maxLength={254} placeholder="you@example.com" data-testid="wl-email" /></label>
      <label className="consent">
        <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} data-testid="wl-consent" />
        <span>{CONSENT}</span></label>
      {err && <p className="wl-err" role="alert" data-testid="wl-err">{err}</p>}
      <button className="submit" type="submit" disabled={state === "busy"} data-testid="wl-submit">
        {state === "busy" ? "Adding you…" : "Send me the next three"}
      </button>
      <p className="fineprint">One e-mail per match day. Unsubscribe in one click. We never pass your address on.</p>
    </form>
  );
}

export default function Waitlist() {
  // The page's wording, editable by the owner in admin under "Waitlist page". An empty or missing
  // setting falls back to the text shipped here, so the page never renders a blank heading because
  // somebody cleared a field.
  const { cfg } = useSite();
  const t = (k, fallback) => {
    const v = cfg?.waitlist?.[k];
    return typeof v === "string" && v.trim() ? v : fallback;
  };
  useTitle("Join the waitlist");
  const rec = useApi("/track-record");
  const pf = useApi("/proof", { limit: 8 });
  const lk = useApi("/likely", { within_h: 24, limit: 1 });
  const drawn = useRef(false);

  // The card at the top of the page is the first row of /likely, reshaped into what the drawings
  // expect. Football does not run every day, and on a quiet one this page -- the first thing a
  // stranger sees -- had a heading over an empty band, because the window is 24 hours and nothing
  // was inside it.
  //
  // So when the window is empty it falls back to the most recent SETTLED line, which is the
  // strongest card this product owns: the same drawing, plus what actually happened. The page says
  // which it is looking at rather than passing a finished match off as tonight's.
  const shape = (f, past) => {
    if (!f) return null;
    const n = Math.floor(Number(f.thr)) + 1;
    const run = (f.run || []).map((g) => (g && typeof g === "object" ? g.v : g)).filter((v) => v != null);
    return {
      player: { name: f.player?.name || f.team?.name || "", pos: f.pos || "" },
      team: { name: f.team?.name || "" }, opp: { name: f.opp?.name || "" },
      kickoff: f.kickoff, market: f.market, p: f.p, lo: f.lo, hi: f.hi,
      lineup: f.lineup_badge === "confirmed" ? "Starting" : f.lineup_badge === "likely" ? "Usually starts" : "",
      run,
      need: n, reached: run.filter((v) => v >= n).length,
      past, actual: past ? f.actual : null,
    };
  };
  const tonight = useMemo(() => {
    const live = shape((lk.data?.rows || [])[0], false);
    if (live) return live;
    // Only once /likely has actually answered: a card drawn while it is still loading would flip
    // from a settled match to tonight's under the reader.
    if (!lk.data) return null;
    return shape((pf.data?.items || [])[0], true);
  }, [lk.data, pf.data]);  // eslint-disable-line react-hooks/exhaustive-deps

  const ready = rec.data && pf.data;
  // Every figure below is drawn from these two feeds, so until they land there is nothing in the
  // three section bodies -- and if they fail there never will be. They used to be three empty
  // divs: a heading, a sub-line and a band of nothing, with no way to try again. The rest of the
  // product answers that with the kit's three states (docs/24), and this page is the one a
  // stranger sees first.
  const failed = !!(rec.error || pf.error);
  const waiting = !ready && !failed;
  const retry = () => { if (rec.error) rec.reload(); if (pf.error) pf.reload(); };
  useEffect(() => {
    if (!ready || drawn.current) return;
    drawn.current = true;
    paint(pf.data.items || [], rec.data, tonight);
  }, [ready, pf.data, rec.data, tonight]);

  return (
    <div className="lp" data-testid="waitlist-page">
      <header className="top">
        <div className="wrap">
          <Link className="mark" to="/" data-testid="wl-brand">
            <svg className="glyph" viewBox="0 0 24 24" aria-hidden="true">
              <rect x="0" y="0" width="24" height="24" rx="6" fill="#034737" />
              <path d="M4 17.5 L9 11 L13 14 L20 5.5" fill="none" stroke="#A9FF9B" strokeWidth="2.3"
                strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            <span>Forecast</span>
          </Link>
          <span className="tag">{t("tag", "Opening soon — waitlist")}</span>
        </div>
      </header>

      <main>
        <section className="hero" id="join">
          <div className="wrap hero-grid">
            <div className="hero-left">
              <p className="kicker" id="kicker" />
              <h1>{t("headline", "We say what a player will do.")} <span className="said">{t("headline_em", "Then we publish what he did.")}</span></h1>
              <p className="lead">{t("lead",
                "A named player, a real line, a number — published before kick-off, scored after the "
                + "whistle, and left on the site either way. Join the list and we will send you the three "
                + "we are most confident in, every match day, until we open.")}</p>
              <Form />
            </div>
            <div className="hero-right"><div id="livecard" /><div className="counters" id="counters" /></div>
          </div>
        </section>

        <section className="band" id="proof">
          <div className="wrap">
            <p className="eyebrow">{t("proof_eyebrow", "Published, scored, settled")}</p>
            <h2>{t("proof_title", "The cards that already happened")}</h2>
            <p className="sub">{t("proof_sub",
              "These went out before kick-off and were scored after the whistle. The big number is "
              + "what we said; the bar under it is what he did, against the line we published.")}</p>
            {waiting ? <Skeleton shape="card" count={3} testid="wl-proof-loading" />
              : failed ? <ErrorState message="We could not load the scored cards just now." onRetry={retry} testid="wl-proof-error" />
              : <div className="proof-grid" id="proof-grid" />}
            <p className="foot-note" id="proof-note" />
          </div>
        </section>

        <section className="plain" id="engine">
          <div className="wrap">
            <p className="eyebrow">{t("engine_eyebrow", "Inside the engine")}</p>
            <h2>{t("engine_title", "Four things a table of averages cannot do")}</h2>
            <p className="sub">
              Every picture below is drawn from tonight&apos;s card at the top of this page — the same
              player, the same line, the same match. This is the machine, not a metaphor for it.
            </p>
            {/* One error on the page, not three: the three bands share the same two feeds, so the
                proof band above carries the message and the way back, and the bands below simply
                do not draw a frame around nothing. */}
            {waiting ? <Skeleton shape="card" count={4} testid="wl-engine-loading" />
              : failed ? null
              : <div className="eng-grid" id="eng-grid" />}
          </div>
        </section>

        <section className="band" id="record">
          <div className="wrap">
            <p className="eyebrow">{t("record_eyebrow", "The whole record")}</p>
            <h2>{t("record_title", "What we said, against what happened")}</h2>
            <p className="sub" id="rec-sub" />
            {waiting ? <Skeleton shape="match" count={3} testid="wl-record-loading" />
              : failed ? null
              : <div className="rec" id="rec" />}
            <p className="foot-note">
              The point is not that the right-hand dot is high. It is that the two dots are <b>close</b>.
              When we say 80%, we want it to happen about 80 times in 100 — more would mean we were
              being timid, less would mean we were overclaiming.
            </p>
          </div>
        </section>

        <section className="plain">
          <div className="wrap">
            <p className="eyebrow">{t("costs_eyebrow", "On purpose")}</p>
            <h2>{t("costs_title", "Three things we do that cost us")}</h2>
            <ul className="hon">
              <li><b>We show the range, not just the number.</b><span>Every forecast carries the spread around it, so you can see the ones we are sure of and the ones we are not.</span></li>
              <li><b>We show nothing under 60%.</b><span>A coin flip dressed as an insight is worse than an empty screen. When there is nothing worth showing, the screen says so.</span></li>
              <li><b>We publish the misses.</b><span>The record above counts every scored forecast, not a flattering selection of them.</span></li>
            </ul>
          </div>
        </section>

        <section className="cta">
          <div className="wrap">
            <h2>{t("close_title", "Three forecasts. Every match day. Until we open.")}</h2>
            <p>
              Each one with its range, its lineup word and its last-ten run — the whole card, not
              just a number. Then scored in public, like everything else here.
            </p>
            <a className="cta-btn" href="#join" data-testid="wl-cta">Join the list
              <svg width="17" height="17" viewBox="0 0 17 17" aria-hidden="true">
                <path d="M3 13.5 L13.5 3 M6 3 h7.5 v7.5" fill="none" stroke="#034737" strokeWidth="2"
                  strokeLinecap="round" strokeLinejoin="round" /></svg></a>
          </div>
        </section>
      </main>

      <footer>
        <div className="wrap">
          <p className="dis">{DISCLAIMER}</p>
          <nav>
            <Link to="/legal/terms">Terms</Link> · <Link to="/legal/privacy">Privacy</Link> ·{" "}
            <Link to="/track-record">Track record</Link>
          </nav>
        </div>
      </footer>
    </div>
  );
}
