// Account area (docs/13 §2 tabs): Profile, Security, Devices, Notifications, Plan and billing, Privacy.
import { useCallback, useEffect, useState } from "react";
import { Link, Navigate, NavLink, Route, Routes, useSearchParams } from "react-router-dom";
import { del, get, patch, post } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useApi } from "../lib/useApi";
import { useSite } from "../lib/site";
import { utc } from "../lib/time";
import { Confirm, Field, FormError, PasswordField, Switch, useToast } from "../components/Ui";
import { Empty, ErrorBox, Loading } from "../components/States";
import Icon from "../components/Icon";
import { NewPasswordForm, TwoFactorSetup } from "./Auth";

const TABS = [
  ["profile", "Profile", "user"], ["security", "Security", "shield"], ["devices", "Devices", "phone"],
  ["notifications", "Notifications", "bell"], ["plan", "Plan and billing", "credit-card"], ["privacy", "Privacy", "padlock"],
];
const fmt = (s) => (s ? utc(s).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }) : "No data");
function device(ua = "") {
  const b = /Edg\//.test(ua) ? "Edge" : /Firefox\//.test(ua) ? "Firefox" : /Chrome\//.test(ua) ? "Chrome" : /Safari\//.test(ua) ? "Safari" : null;
  const o = /iPhone|iPad/.test(ua) ? "iOS" : /Android/.test(ua) ? "Android" : /Mac OS X/.test(ua) ? "macOS" : /Windows/.test(ua) ? "Windows" : /Linux/.test(ua) ? "Linux" : null;
  return b || o ? `${b || "Browser"}${o ? ` on ${o}` : ""}` : ua ? ua.slice(0, 60) : "Unknown device";
}
const fmtDate = (s) => (s ? utc(s).toLocaleDateString(undefined, { dateStyle: "medium" }) : "No data");

function Section({ title, lead, children, testid }) {
  return <section className="acc-section" data-testid={testid}><h2>{title}</h2>{lead && <p className="muted">{lead}</p>}{children}</section>;
}

function Profile() {
  const { user, setUser } = useAuth();
  const { setTheme } = useSite();
  const toast = useToast();
  const [f, setF] = useState({ display_name: user.display_name || "", tz: user.tz || "UTC", theme: user.theme || "system" });
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  const zones = typeof Intl.supportedValuesOf === "function" ? Intl.supportedValuesOf("timeZone") : [f.tz];
  const save = async (e) => {
    e.preventDefault(); setBusy(true); setErr(null);
    try { const r = await patch("/account/profile", f); setTheme(f.theme); setUser(r.user); toast("Profile saved"); } catch (x) { setErr(x); } finally { setBusy(false); }
  };
  return (
    <Section title="Profile" lead={`Signed in as ${user.email}`} testid="account-profile">
      <form className="form form--wide" onSubmit={save}>
        <Field label="Name" value={f.display_name} maxLength={60} autoComplete="name" onChange={(e) => setF({ ...f, display_name: e.target.value })} testid="profile-name" />
        <Field label="Time zone" as="select" value={f.tz} onChange={(e) => setF({ ...f, tz: e.target.value })} testid="profile-tz">
          {zones.includes(f.tz) ? null : <option value={f.tz}>{f.tz}</option>}
          {zones.map((z) => <option key={z} value={z}>{z}</option>)}
        </Field>
        <button type="button" className="btn btn--ghost btn--sm self-start" onClick={() => setF({ ...f, tz: Intl.DateTimeFormat().resolvedOptions().timeZone })} data-testid="profile-tz-detect">Use this device's time zone</button>
        <fieldset className="seg" data-testid="profile-theme"><legend>Theme</legend>
          {["system", "dark", "light"].map((t) => (
            <label key={t} className={"seg-opt" + (f.theme === t ? " is-on" : "")}><input type="radio" name="theme" value={t} checked={f.theme === t} onChange={() => setF({ ...f, theme: t })} data-testid={`profile-theme-${t}`} />{t[0].toUpperCase() + t.slice(1)}</label>
          ))}
        </fieldset>
        <FormError error={err} />
        <button className="btn btn--primary self-start" disabled={busy} data-testid="profile-save">Save</button>
      </form>
    </Section>
  );
}

function EmailChange() {
  const toast = useToast();
  const [f, setF] = useState({ new_email: "", password: "" });
  const [err, setErr] = useState(null);
  const submit = async (e) => {
    e.preventDefault(); setErr(null);
    try { await post("/account/email", f); setF({ new_email: "", password: "" }); toast("We sent a link to the new address"); } catch (x) { setErr(x); }
  };
  return (
    <form className="form form--wide" onSubmit={submit} data-testid="email-change-form">
      <Field label="New e-mail" type="email" autoComplete="email" required value={f.new_email} onChange={(e) => setF({ ...f, new_email: e.target.value })} testid="email-change-new" />
      <PasswordField label="Your password" autoComplete="current-password" required value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} testid="email-change-password" />
      <small className="field-hint">The link goes to the new address. Your old address is told about the change.</small>
      <FormError error={err} />
      <button className="btn btn--secondary self-start" data-testid="email-change-submit">Send confirmation link</button>
    </form>
  );
}

function TwoFactor() {
  const { user, refresh } = useAuth();
  const toast = useToast();
  const [setup, setSetup] = useState(false);
  const [f, setF] = useState({ password: "", code: "" });
  const [err, setErr] = useState(null);
  const staff = user.role !== "user";
  if (setup) return <TwoFactorSetup onFinished={async () => { setSetup(false); await refresh(); toast("Two-factor sign-in is on"); }} />;
  if (!user.two_factor) return <><p className="muted">Off. Add a code from an authenticator app to every sign-in.</p><button className="btn btn--primary self-start" onClick={() => setSetup(true)} data-testid="twofa-enable">Turn on</button></>;
  if (staff) return <p className="status-line" data-testid="twofa-status"><Icon name="check" size={16} />On. Staff accounts cannot turn it off.</p>;
  const off = async (e) => {
    e.preventDefault(); setErr(null);
    try { await post("/account/2fa/disable", f); await refresh(); toast("Two-factor sign-in is off"); } catch (x) { setErr(x); }
  };
  return (
    <form className="form form--wide" onSubmit={off} data-testid="twofa-disable-form">
      <p className="status-line"><Icon name="check" size={16} />On.</p>
      <PasswordField label="Password" autoComplete="current-password" required value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} testid="twofa-disable-password" />
      <Field label="Current code" inputMode="numeric" autoComplete="one-time-code" value={f.code} onChange={(e) => setF({ ...f, code: e.target.value })} testid="twofa-disable-code" />
      <FormError error={err} />
      <button className="btn btn--danger self-start" data-testid="twofa-disable-submit">Turn off</button>
    </form>
  );
}

function Security() {
  const toast = useToast();
  const [k, setK] = useState(0);
  return (
    <>
      <Section title="Password" lead="Changing it signs out your other devices." testid="account-password">
        <NewPasswordForm key={k} needCurrent testid="password-form" submitLabel="Change password" onSubmit={async (f) => { await post("/account/password", { current: f.current, new: f.a }); setK((x) => x + 1); toast("Password changed"); }} />
      </Section>
      <Section title="E-mail address" testid="account-email"><EmailChange /></Section>
      <Section title="Two-factor sign-in" testid="account-2fa"><TwoFactor /></Section>
    </>
  );
}

function Devices() {
  const s = useApi("/account/sessions");
  const toast = useToast();
  const act = async (fn, msg) => { try { await fn(); toast(msg); s.reload(); } catch (x) { toast(x.message || "Could not do that", "err"); } };
  return (
    <Section title="Devices" lead="Where your account is signed in." testid="account-devices">
      {s.loading ? <Loading /> : s.error ? <ErrorBox error={s.error} onRetry={s.reload} /> : !s.data?.sessions?.length ? <Empty>No sessions.</Empty> : (
        <>
          <ul className="rows">
            {s.data.sessions.map((x) => (
              <li key={x.sid} className="row-card" data-testid={`session-${x.sid}`}>
                <Icon name={/mobile|iphone|android/i.test(x.ua || "") ? "phone" : "monitor"} />
                <div className="row-main"><strong>{device(x.ua)}</strong><small>Last seen {fmt(x.last_seen)} · {x.ip || "No data"}</small></div>
                {x.current ? <span className="chip-tag chip-tag--brand">This device</span> :
                  <button className="btn btn--secondary btn--sm" onClick={() => act(() => del(`/account/sessions/${x.sid}`), "Signed out that device")} data-testid={`session-revoke-${x.sid}`}>Sign out</button>}
              </li>
            ))}
          </ul>
          <button className="btn btn--secondary self-start" onClick={() => act(() => post("/account/sessions/revoke-others"), "Other devices signed out")} data-testid="sessions-revoke-others">Sign out all other devices</button>
        </>
      )}
    </Section>
  );
}

function Notifications() {
  const { user, setUser } = useAuth();
  const toast = useToast();
  const p = user.prefs || {};
  const staff = user.role !== "user";
  const val = (k, d) => (p[k] === undefined ? d : p[k]);
  const set = async (k, v) => { try { const r = await patch("/account/profile", { prefs: { ...p, [k]: v } }); setUser(r.user); toast("Saved"); } catch (x) { toast(x.message || "Could not save", "err"); } };
  const rows = [
    ["product_emails", "Product e-mails", "News about features you use.", true],
    ["marketing_emails", "Marketing e-mails", "Occasional updates. Off unless you turn it on.", false],
    ["alert_emails", "Alert e-mails", "Alerts you set up for teams and players.", true],
  ];
  if (staff) rows.push(["admin_alerts", "E-mail me when something looks wrong", "Staff only.", ["owner", "admin"].includes(user.role)], ["admin_digest", "Weekly summary", "Staff only.", false]);
  return (
    <Section title="Notifications" testid="account-notifications">
      <div className="switch-list">{rows.map(([k, l, h, d]) => <Switch key={k} label={l} hint={h} checked={val(k, d)} onChange={(v) => set(k, v)} testid={`pref-${k}`} />)}</div>
      <p className="muted small">Receipts and security e-mails cannot be turned off.</p>
    </Section>
  );
}

function Confirming({ onDone }) {
  const [late, setLate] = useState(false);
  const { refresh } = useAuth();
  useEffect(() => {
    let n = 0;
    const t = setInterval(async () => {
      n += 1;
      try { const d = await get("/account/billing"); if (d.plan?.source === "subscription") { clearInterval(t); refresh(); onDone(); } } catch { /* keep polling */ }
      if (n >= 15) setLate(true);
    }, 2000);
    return () => clearInterval(t);
  }, [onDone, refresh]);
  return <p className="notice" data-testid="billing-confirming"><Icon name="refresh" size={16} />{late ? "Your payment is received. Access can take a minute to switch on." : "Confirming your payment…"}</p>;
}

function Plan() {
  const b = useApi("/account/billing");
  const toast = useToast();
  const [sp, setSp] = useSearchParams();
  const [busy, setBusy] = useState(false);
  const done = useCallback(() => { setSp({}); b.reload(); }, [setSp, b]);
  const portal = async () => { setBusy(true); try { const r = await post("/billing/portal"); window.location.assign(r.url); } catch (x) { toast(x.message || "Billing is not available right now", "err"); setBusy(false); } };
  if (b.loading && !b.data) return <Loading />;
  if (b.error) return <ErrorBox error={b.error} onRetry={b.reload} />;
  const d = b.data;
  const plan = d.plan || {};
  return (
    <Section title="Plan and billing" testid="account-plan">
      {sp.get("status") === "success" && <Confirming onDone={done} />}
      <div className="plan-hero">
        <div><small className="kicker">Current plan</small><strong data-testid="plan-name">{plan.plan_name || "Free"}</strong></div>
        <span className="chip-tag chip-tag--brand" data-testid="plan-status">{plan.source === "billing_off" ? "Included" : plan.status || "Active"}</span>
      </div>
      {!d.billing_enabled && <p className="notice" data-testid="billing-off-note"><Icon name="info" size={16} />Paid plans are not open yet. Every signed-in person gets the full plan for now.</p>}
      {d.comp && <p className="notice">Included until {fmtDate(d.comp.until || d.comp.ends_at)}.</p>}
      {plan.status === "past_due" && <p className="notice notice--warn"><Icon name="alert" size={16} />Your last payment did not go through.</p>}
      {plan.period_end && <p className="muted">{plan.cancel_at_period_end ? "Ends" : "Renews"} on {fmtDate(plan.period_end)}.</p>}
      <div className="btn-row">
        <button className="btn btn--secondary" disabled={!d.can_use_portal || busy} onClick={portal} title={d.can_use_portal ? "" : "Available once you have a paid plan"} data-testid="manage-billing">{busy ? "Opening…" : "Manage billing"}</button>
        {d.billing_enabled && <Link to="/pricing" className="btn btn--ghost" data-testid="change-plan">Change plan</Link>}
      </div>
      <h3>Invoices</h3>
      {d.payments?.length ? (
        <ul className="rows">{d.payments.map((p) => <li key={p.id || p.at} className="row-card"><div className="row-main"><strong>{(p.amount_cents / 100).toFixed(2)} {String(p.currency || "").toUpperCase()}</strong><small>{fmtDate(p.at || p.created_at)} · {p.status}</small></div>{p.invoice_url && <a href={p.invoice_url} target="_blank" rel="noopener noreferrer" className="btn btn--ghost btn--sm">Invoice</a>}</li>)}</ul>
      ) : <Empty icon="receipt">No invoices yet.</Empty>}
    </Section>
  );
}

function Privacy() {
  const { signOut } = useAuth();
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [pw, setPw] = useState("");
  const [err, setErr] = useState(null);
  const exportData = async () => {
    try {
      const data = await get("/account/export");
      const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
      const a = document.createElement("a"); a.href = url; a.download = "my-data.json"; a.click(); URL.revokeObjectURL(url);
    } catch (x) { toast(x.message || "Could not export", "err"); }
  };
  return (
    <>
      <Section title="Download my data" lead="A JSON file with everything we hold about you." testid="account-export">
        <button className="btn btn--secondary self-start" onClick={exportData} data-testid="export-data"><Icon name="download" size={16} />Download my data</button>
      </Section>
      <Section title="Delete my account" lead="Removes your account, follows, saved forecasts, notes, alerts, sessions and links. Payment records stay for tax law, unlinked from your name. Any subscription is cancelled first." testid="account-delete">
        <form className="form form--wide" onSubmit={(e) => { e.preventDefault(); setErr(null); setOpen(true); }}>
          <PasswordField label="Type your password" autoComplete="current-password" required value={pw} onChange={(e) => setPw(e.target.value)} testid="delete-password" />
          <FormError error={err} />
          <button className="btn btn--danger self-start" disabled={!pw} data-testid="delete-account">Delete my account</button>
        </form>
      </Section>
      <Confirm open={open} danger title="Delete your account?" body="This cannot be undone." confirmLabel="Delete for good" onClose={() => setOpen(false)} testid="delete-confirm"
               onConfirm={async () => { try { await del("/account", { password: pw }); setOpen(false); await signOut(); } catch (x) { setOpen(false); setErr(x); } }} />
    </>
  );
}

export default function Account() {
  const { user, loading } = useAuth();
  if (loading) return <Loading />;
  if (!user) return <Navigate to="/sign-in?next=/account" replace />;
  return (
    <div className="account" data-testid="account-page">
      <header className="page-head"><h1>Account</h1></header>
      <div className="account-grid">
        <nav className="acc-nav" aria-label="Account">
          {TABS.map(([id, label, icon]) => <NavLink key={id} to={`/account/${id}`} className="acc-link" data-testid={`account-tab-${id}`}><Icon name={icon} size={18} /><span>{label}</span></NavLink>)}
        </nav>
        <div className="acc-body">
          <Routes>
            <Route index element={<Navigate to="profile" replace />} />
            <Route path="profile" element={<Profile />} />
            <Route path="security" element={<Security />} />
            <Route path="devices" element={<Devices />} />
            <Route path="notifications" element={<Notifications />} />
            <Route path="plan" element={<Plan />} />
            <Route path="privacy" element={<Privacy />} />
            <Route path="*" element={<Navigate to="profile" replace />} />
          </Routes>
        </div>
      </div>
    </div>
  );
}
