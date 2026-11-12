// Admin home (docs/24 Admin): six health tiles (green, amber, red or off) and one "Needs you" list
// where every item carries its own buttons. Reads GET /api/admin/home.
import { useState } from "react";
import { Link } from "react-router-dom";
import { post } from "../lib/api";
import { useApi } from "../lib/useApi";
import { utc } from "../lib/time";
import Icon from "../components/Icon";
import { useToast } from "../components/Ui";
import { ErrorBox, Loading } from "../components/States";
import { Budget, PageHead, num } from "./parts";

const BADGE = { green: "OK", amber: "Look", red: "Fix", off: "Off" };
const at = (s) => {
  if (!s) return "never";
  const d = utc(s);
  const t = d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  return d.toDateString() === new Date().toDateString() ? t : `${d.toLocaleDateString([], { day: "numeric", month: "short" })} ${t}`;
};
const greet = () => { const h = new Date().getHours(); return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening"; };

function line(t) {
  switch (t.id) {
    case "data": return t.breaker_open ? "PitchAPI breaker is open" : `${t.provider} ${num(t.used)} of ${num(t.cap)} · sync ${at(t.last_sync)}`;
    case "live": return t.enabled ? `${t.provider} ${num(t.used)} of ${num(t.cap)} · ${num(t.live_now)} live` : `${t.provider} is off`;
    case "engine": return `Run ${at(t.last_run)} · ${num(t.forecasts)} forecasts · map ${t.map}${t.errors_24h ? ` · ${t.errors_24h} failed` : ""}`;
    case "images": return t.review ? `${num(t.review)} to review` : `Nothing to review · ${num(t.stored)} player photos`;
    case "users": return `${num(t.signups_today)} sign-up${t.signups_today === 1 ? "" : "s"} today · ${num(t.total)} member${t.total === 1 ? "" : "s"}`;
    case "money": return t.billing ? `Billing on (${t.mode})${t.past_due ? ` · ${t.past_due} past due` : ""}${t.webhook_errors_24h ? ` · ${t.webhook_errors_24h} webhook errors` : ""}` : "Billing off";
    default: return "";
  }
}

function Tile({ t, route }) {
  const body = (
    <>
      <span className="ah-tile-head"><b>{t.title}</b><span className={`ah-badge ah-badge--${t.tone}`} data-testid={`home-tile-${t.id}-state`}>{BADGE[t.tone]}</span></span>
      <span className="ah-line" data-testid={`home-tile-${t.id}-line`}>{line(t)}</span>
      {t.cap > 0 && (t.id === "data" || t.enabled) && <Budget used={t.used} cap={t.cap} reset={t.reset_at} byKind={t.by_kind} label={`${t.provider} calls today`} testid={`home-tile-${t.id}-budget`} />}
    </>
  );
  return route ? <Link to={route} className={`ah-tile ah-tile--${t.tone}`} data-testid={`home-tile-${t.id}`}>{body}</Link>
    : <div className={`ah-tile ah-tile--${t.tone}`} data-testid={`home-tile-${t.id}`}>{body}</div>;
}

function TwoTap({ label, onConfirm, testid }) {
  const [armed, setArmed] = useState(false);
  return <button type="button" className={`btn btn--sm ${armed ? "btn--danger" : "btn--ghost"}`} onClick={() => (armed ? onConfirm() : setArmed(true))} onBlur={() => setArmed(false)} data-testid={testid}>{armed ? "Tap again" : label}</button>;
}

function NeedItem({ n, onDone }) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const act = async (fn, msg) => { setBusy(true); try { await fn(); toast(msg); onDone(n.key); } catch (x) { toast(x.message || "Could not do that", "err"); setBusy(false); } };
  const tid = `need-${n.key}`;
  const tag = { match: "Match", image: "Image", job: "Job", alert: "Alert", issue: "Data", inbox: "Inbox" }[n.kind];
  let text, buttons;
  if (n.kind === "match") {
    // The SportAPI club-matching need is gone (admin_home.needs). Its three buttons posted to
    // /admin/sportapi/teams/{sid}, deleted with the provider, so each answered 404 and the item
    // could never be cleared. Kept as a readable row rather than silently dropped, in case an old
    // payload still carries one.
    text = <>Club matching for a retired provider. Nothing to do: this feed is no longer used.</>;
    buttons = null;
  } else if (n.kind === "image") {
    const c0 = n.candidates?.[0];
    text = <>New {n.image_kind === "team" ? "crest" : n.image_kind === "league" ? "logo" : "photo"} for <b>{n.name || `#${n.our_iid}`}</b>{c0 ? ` · best match ${c0.name} (${Math.round((c0.score || 0) * 100)}%)` : ""}</>;
    buttons = <>
      {c0 && <button type="button" className="btn btn--primary btn--sm" disabled={busy} onClick={() => act(() => post(`/admin/images/${n.image_kind}/${n.our_iid}/approve`, { af_id: c0.af_id }), "Approved")} data-testid={`${tid}-approve`}>Approve</button>}
      <TwoTap label="Reject" onConfirm={() => act(() => post(`/admin/images/${n.image_kind}/${n.our_iid}/reject`), "Rejected")} testid={`${tid}-reject`} />
    </>;
  } else if (n.kind === "job") {
    text = <>Job <b>{n.job}</b> failed at {at(n.at)}{n.error ? `: ${n.error}` : ""}</>;
    buttons = n.can_run ? <button type="button" className="btn btn--primary btn--sm" disabled={busy} onClick={() => act(() => post(`/admin/jobs/run?job=${encodeURIComponent(n.run_as)}`), "Queued for the next tick")} data-testid={`${tid}-run`}>Run again</button>
      : <Link to="/admin/data/jobs" className="btn btn--secondary btn--sm" data-testid={`${tid}-open`}>Open Jobs</Link>;
  } else if (n.kind === "alert") {
    text = n.text;
    buttons = <button type="button" className="btn btn--secondary btn--sm" disabled={busy} onClick={() => act(() => post(`/admin/alerts/${n.id}/resolve`), "Marked fixed")} data-testid={`${tid}-fixed`}>Mark fixed</button>;
  } else if (n.kind === "issue") {
    text = n.text;
    buttons = <button type="button" className="btn btn--secondary btn--sm" disabled={busy} onClick={() => act(() => post("/admin/issues/resolve-many", { ids: n.ids }), "Marked fixed")} data-testid={`${tid}-fixed`}>Mark fixed</button>;
  } else {
    text = <>{n.count} new message{n.count === 1 ? "" : "s"} from the contact form</>;
    buttons = <Link to="/admin/inbox" className="btn btn--secondary btn--sm" data-testid={`${tid}-open`}>Open inbox</Link>;
  }
  return (
    <li className="ah-need" data-testid={tid}>
      <span className={`ah-tag ah-tag--${n.kind}`}>{tag}</span>
      <span className="ah-need-text">{text}</span>
      <span className="ah-need-btns">{buttons}</span>
    </li>
  );
}

export function NeedsList({ q, limit }) {
  const [gone, setGone] = useState([]);
  const items = (q.data?.needs || []).filter((n) => !gone.includes(n.key));
  const shown = limit ? items.slice(0, limit) : items;
  return (
    <section className="ah-needs-wrap" data-testid="home-needs">
      <h2 className="ah-sec">Needs you · {items.length}</h2>
      {!items.length ? <p className="ah-clear card" data-testid="home-needs-empty"><Icon name="check" size={18} />Nothing needs you right now.</p> : (
        <ul className="ah-needs">{shown.map((n) => <NeedItem key={n.key} n={n} onDone={(k) => setGone((g) => [...g, k])} />)}</ul>
      )}
      {limit && items.length > limit && <Link to="/admin/needs" className="a-link-btn" data-testid="home-needs-all">See all {items.length}</Link>}
    </section>
  );
}

export function Needs() {
  const q = useApi("/admin/home");
  if (q.loading && !q.data) return <Loading rows={5} />;
  if (q.error) return <ErrorBox error={q.error} onRetry={q.reload} />;
  // On Home the list sits under the greeting, so its own heading is an h2. On its own page it needs a title of its
  // own, or the screen has no h1 at all -- the one screen in the admin that did not (docs/43).
  return (
    <div className="a-page" data-testid="admin-needs">
      <PageHead title="Needs you" lead="Everything waiting for a person: clubs to match, images to approve, failed jobs, alerts and ingest problems." />
      <NeedsList q={q} />
    </div>
  );
}

export default function AdminHome({ shell }) {
  const q = useApi("/admin/home");
  if (q.loading && !q.data) return <Loading rows={6} />;
  if (q.error) return <ErrorBox error={q.error} onRetry={q.reload} />;
  const route = (id) => shell?.modules?.find((m) => m.id === id)?.route;
  return (
    <div className="a-page ah" data-testid="admin-home">
      <header className="ah-head">
        <h1>{greet()}{q.data.name ? `, ${q.data.name}` : ""}</h1>
        <span className="a-muted" data-testid="home-now">{utc(q.data.now).toLocaleDateString([], { weekday: "short", day: "numeric", month: "short" })} · {at(q.data.now)}</span>
        <button type="button" className="btn btn--ghost btn--sm" onClick={q.reload} data-testid="home-refresh"><Icon name="refresh" size={16} />Refresh</button>
      </header>
      <div className="ah-tiles" data-testid="home-tiles">{q.data.tiles.map((t) => <Tile key={t.id} t={t} route={route(t.module)} />)}</div>
      <NeedsList q={q} limit={8} />
      {route("analytics") && <Link to={`${route("analytics")}/overview`} className="a-link-btn" data-testid="home-stats">Sign-ups, visitors and revenue charts</Link>}
    </div>
  );
}
