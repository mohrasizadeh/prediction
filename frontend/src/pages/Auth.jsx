// Account screens (docs/13 §2 and §6): sign in + 2FA code, sign up + check inbox, verify, forgot, reset, confirm new e-mail,
// 2FA enrolment with recovery codes, and the forced first-password change. Tokens from e-mail links are read once from the URL.
import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { QRCodeSVG } from "qrcode.react";
import { post } from "../lib/api";
import { useAuth } from "../lib/auth";
import { Field, FormError, PasswordField } from "../components/Ui";
import Icon from "../components/Icon";

const safe = (n) => (n && n.startsWith("/") && !n.startsWith("//") ? n : "/");

function AuthCard({ title, lead, children, icon = "shield", testid }) {
  return (
    <div className="auth" data-testid={testid}>
      <div className="auth-card">
        <span className="auth-ico"><Icon name={icon} size={22} /></span>
        <h1>{title}</h1>
        {lead && <p className="auth-lead">{lead}</p>}
        {children}
      </div>
      <aside className="auth-aside" aria-hidden="true">
        <div className="pitch-lines" />
        <p className="aside-kicker">Forecasts with the reasons shown</p>
        <p className="aside-big">Likelihood, form and tactics. <span>Never a guess dressed up as a certainty.</span></p>
      </aside>
    </div>
  );
}

function useResend(path, email) {
  const [wait, setWait] = useState(0);
  useEffect(() => { if (wait <= 0) return undefined; const t = setTimeout(() => setWait((w) => w - 1), 1000); return () => clearTimeout(t); }, [wait]);
  const send = async () => { setWait(60); await post(path, { email }).catch(() => {}); };
  return { wait, send };
}

function ResendButton({ email, testid = "resend-verification" }) {
  const { wait, send } = useResend("/auth/resend-verification", email);
  return <button type="button" className="btn btn--secondary" disabled={wait > 0 || !email} onClick={send} data-testid={testid}>{wait > 0 ? `Send again in ${wait} s` : "Send the link again"}</button>;
}

export function SignIn() {
  const [params] = useSearchParams();
  const next = safe(params.get("next"));
  const nav = useNavigate();
  const { refresh } = useAuth();
  const [f, setF] = useState({ email: "", password: "" });
  const [challenge, setChallenge] = useState(null);
  const [code, setCode] = useState("");
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  const done = async (r) => {
    await refresh();
    if (r?.scope === "enroll_2fa") return nav("/enroll-2fa");
    if (r?.user?.must_change_password) return nav("/change-password");
    nav(next === "/" && r?.user?.role && r.user.role !== "user" ? "/admin" : next);
  };
  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setErr(null);
    try {
      const r = await post("/auth/login", f);
      if (r?.needs_2fa) setChallenge(r.challenge); else await done(r);
    } catch (x) { setErr(x); } finally { setBusy(false); }
  };
  const submit2fa = async (e, c = code) => {
    e?.preventDefault(); setBusy(true); setErr(null);
    try { const r = await post("/auth/login/2fa", { challenge, code: c }); await done(r); } catch (x) { setErr(x); if (x.code === "CHALLENGE_EXPIRED") setChallenge(null); } finally { setBusy(false); }
  };
  if (challenge) {
    return (
      <AuthCard title="Enter your code" lead="Open your authenticator app and type the 6-digit code. You can also use one of your recovery codes." icon="padlock" testid="signin-2fa">
        <form className="form" onSubmit={submit2fa}>
          <Field label="6-digit code or recovery code" value={code} autoComplete="one-time-code" inputMode="text" autoFocus testid="signin-2fa-code" maxLength={40}
                 onChange={(e) => { const v = e.target.value.trim(); setCode(v); if (/^\d{6}$/.test(v)) submit2fa(null, v); }} />
          <FormError error={err} />
          <button className="btn btn--primary btn--lg btn--block" disabled={busy || !code} data-testid="signin-2fa-submit">{busy ? "Checking…" : "Continue"}</button>
          <button type="button" className="btn btn--ghost btn--block" onClick={() => { setChallenge(null); setCode(""); }} data-testid="signin-2fa-back">Back to sign in</button>
        </form>
      </AuthCard>
    );
  }
  return (
    <AuthCard title="Sign in" lead="Welcome back. Follow teams, save forecasts and get more Finder searches." icon="user" testid="signin-page">
      <form className="form" onSubmit={submit} noValidate>
        <Field label="E-mail" type="email" autoComplete="email" required value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} testid="signin-email" />
        <PasswordField autoComplete="current-password" required value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} testid="signin-password" />
        <div className="form-row-end"><Link to="/forgot-password" data-testid="signin-forgot-link">Forgot password?</Link></div>
        <FormError error={err} />
        {err?.code === "EMAIL_NOT_VERIFIED" && <ResendButton email={f.email} />}
        <button className="btn btn--primary btn--lg btn--block" disabled={busy} data-testid="signin-submit">{busy ? "Signing in…" : "Sign in"}</button>
        <p className="form-foot">New here? <Link to="/sign-up" data-testid="signin-signup-link">Create an account</Link></p>
      </form>
    </AuthCard>
  );
}

export function SignUp() {
  // SignIn reads `next` and returns the reader to what they were doing; SignUp did not, so the
  // destination a reader was sent here FOR was dropped at the one moment they agreed to sign up.
  const [params] = useSearchParams();
  const next = safe(params.get("next"));
  const [f, setF] = useState({ email: "", password: "", display_name: "" });
  const [sent, setSent] = useState(false);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  const submit = async (e) => {
    e.preventDefault(); setErr(null); setBusy(true);
    try { await post("/auth/register", { ...f, tz: Intl.DateTimeFormat().resolvedOptions().timeZone }); setSent(true); } catch (x) { setErr(x); } finally { setBusy(false); }
  };
  if (sent) {
    return (
      <AuthCard title="Check your inbox" lead={`If that address can be used, we sent a link to ${f.email}. Open it to confirm your e-mail.`} icon="mail" testid="signup-sent">
        <div className="form"><ResendButton email={f.email} /><Link to={`/sign-in${next && next !== "/" ? `?next=${encodeURIComponent(next)}` : ""}`} className="btn btn--ghost btn--block" data-testid="signup-sent-signin">Go to sign in</Link></div>
      </AuthCard>
    );
  }
  return (
    <AuthCard title="Create an account" lead="E-mail and password. That is all we need." icon="user" testid="signup-page">
      <form className="form" onSubmit={submit}>
        <Field label="E-mail" type="email" autoComplete="email" required value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} testid="signup-email" />
        <PasswordField label="Password" autoComplete="new-password" required minLength={10} value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} testid="signup-password" />
        <small className="field-hint">At least 10 characters. A short phrase works well.</small>
        <Field label="Name (optional)" autoComplete="name" value={f.display_name} maxLength={60} onChange={(e) => setF({ ...f, display_name: e.target.value })} testid="signup-name" />
        <FormError error={err} />
        <button className="btn btn--primary btn--lg btn--block" disabled={busy} data-testid="signup-submit">{busy ? "Creating…" : "Create account"}</button>
        <p className="form-foot muted">By creating an account you accept the <Link to="/legal/terms">terms</Link> and <Link to="/legal/privacy">privacy policy</Link>. For adults 18+.</p>
        <p className="form-foot">Already have one? <Link to="/sign-in" data-testid="signup-signin-link">Sign in</Link></p>
      </form>
    </AuthCard>
  );
}

function TokenAction({ title, lead, path, okTitle, okBody, testid }) {
  const [params] = useSearchParams();
  const [state, setState] = useState("idle");
  const [err, setErr] = useState(null);
  const [email, setEmail] = useState("");
  const go = async () => {
    setState("busy");
    try { await post(path, { token: params.get("token") || "" }); setState("ok"); } catch (x) { setErr(x); setState("err"); }
  };
  if (state === "ok") return <AuthCard title={okTitle} icon="check" testid={`${testid}-ok`}><div className="form">{okBody}</div></AuthCard>;
  return (
    <AuthCard title={title} lead={lead} icon="mail" testid={testid}>
      <div className="form">
        {state === "err" ? (
          <>
            <FormError error={err} />
            {path === "/auth/verify-email" && (
              <><Field label="Your e-mail" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} testid="verify-resend-email" /><ResendButton email={email} testid="verify-resend" /></>
            )}
          </>
        ) : (
          <button className="btn btn--primary btn--lg btn--block" onClick={go} disabled={state === "busy" || !params.get("token")} data-testid={`${testid}-submit`}>{state === "busy" ? "Confirming…" : "Confirm"}</button>
        )}
      </div>
    </AuthCard>
  );
}

export const VerifyEmail = () => (
  <TokenAction title="Confirm your e-mail" lead="One click and your account is ready." path="/auth/verify-email" okTitle="You're in" testid="verify-page"
               okBody={<Link to="/sign-in" className="btn btn--primary btn--lg btn--block" data-testid="verify-signin">Sign in</Link>} />
);

export const ConfirmEmail = () => (
  <TokenAction title="Confirm your new e-mail" lead="This finishes the change you started in your account." path="/account/email/confirm" okTitle="E-mail changed" testid="confirm-email-page"
               okBody={<><p>Your new address is now the one you sign in with.</p><Link to="/account/security" className="btn btn--primary btn--block">Back to your account</Link></>} />
);

export function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  const submit = async (e) => {
    e.preventDefault(); setErr(null); setBusy(true);
    try { await post("/auth/forgot-password", { email }); setSent(true); } catch (x) { setErr(x); } finally { setBusy(false); }
  };
  if (sent) return <AuthCard title="Check your inbox" lead="If that address can be used, we sent a link. It works once, for 60 minutes." icon="mail" testid="forgot-sent"><div className="form"><Link to="/sign-in" className="btn btn--secondary btn--block">Back to sign in</Link></div></AuthCard>;
  return (
    <AuthCard title="Forgot your password?" lead="Enter your e-mail and we will send you a link to set a new one." icon="key" testid="forgot-page">
      <form className="form" onSubmit={submit}>
        <Field label="E-mail" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} testid="forgot-email" />
        <FormError error={err} />
        <button className="btn btn--primary btn--lg btn--block" disabled={busy} data-testid="forgot-submit">Send the link</button>
        <p className="form-foot"><Link to="/sign-in">Back to sign in</Link></p>
      </form>
    </AuthCard>
  );
}

function NewPasswordForm({ onSubmit, submitLabel, needCurrent, testid }) {
  const [f, setF] = useState({ current: "", a: "", b: "" });
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  const submit = async (e) => {
    e.preventDefault(); setErr(null);
    // The form carries `noValidate`, so these two rules are stated here rather than by the
    // browser. Reported: a short password raised a raw Chromium bubble -- grey-and-orange OS
    // chrome over a dark themed form -- and it covered the hint that says the rule.
    if (f.a.length < 10) return setErr("Use at least 10 characters.");
    if (f.a !== f.b) return setErr("The two passwords are not the same.");
    setBusy(true);
    try { await onSubmit(f); } catch (x) { setErr(x); } finally { setBusy(false); }
  };
  return (
    <form className="form" noValidate onSubmit={submit} data-testid={testid}>
      {needCurrent && <PasswordField label="Current password" autoComplete="current-password" required value={f.current} onChange={(e) => setF({ ...f, current: e.target.value })} testid={`${testid}-current`} />}
      <PasswordField label="New password" autoComplete="new-password" required minLength={10} value={f.a} onChange={(e) => setF({ ...f, a: e.target.value })} testid={`${testid}-new`} />
      <PasswordField label="New password again" autoComplete="new-password" required minLength={10} value={f.b} onChange={(e) => setF({ ...f, b: e.target.value })} testid={`${testid}-repeat`} />
      <small className="field-hint">At least 10 characters.</small>
      <FormError error={err} />
      <button className="btn btn--primary btn--lg btn--block" disabled={busy} data-testid={`${testid}-submit`}>{busy ? "Saving…" : submitLabel}</button>
    </form>
  );
}
export { NewPasswordForm };

// A dead reset link has one useful answer and it is not an error message: another link. The reader
// is already on the screen, already knows their address, and the resend path is the same one the
// forgot screen posts to -- so it is offered here instead of sending them back a step.
function DeadResetLink() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const { wait, send } = useResend("/auth/forgot-password", email);
  if (sent) return (
    <AuthCard title="Check your inbox" lead="If that address can be used, we sent a new link. It works once, for 60 minutes." icon="mail" testid="reset-resent">
      <div className="form"><Link to="/sign-in" className="btn btn--secondary btn--block">Back to sign in</Link></div>
    </AuthCard>
  );
  return (
    <AuthCard title="This link has expired" lead="A reset link works once and only for a short while. Ask for a new one and it will be in your inbox." icon="key" testid="reset-dead">
      <form className="form" noValidate onSubmit={(e) => { e.preventDefault(); if (!email) return; send(); setSent(true); }}>
        <Field label="Your e-mail" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} testid="reset-dead-email" />
        <button className="btn btn--primary btn--lg btn--block" disabled={wait > 0 || !email} data-testid="reset-dead-resend">Send a new link</button>
        <p className="form-foot"><Link to="/sign-in">Back to sign in</Link></p>
      </form>
    </AuthCard>
  );
}

export function ResetPassword() {
  const [params] = useSearchParams();
  const token = params.get("token") || "";
  const [ok, setOk] = useState(false);
  // Reported by the auth audit: with no token, an expired token or a spent token this screen drew a
  // complete, enabled, confident form. The reader invented a password, typed it twice, and *then*
  // learned the link was dead, on a screen with no way to ask for a new one. So the link is read
  // before anything is drawn. null = still asking, true = good, false = dead.
  const [live, setLive] = useState(token ? null : false);
  useEffect(() => {
    if (!token) return undefined;
    let gone = false;
    post("/auth/reset-password/check", { token })
      .then((r) => { if (!gone) setLive(!!r.valid); })
      .catch(() => { if (!gone) setLive(true); });   // our own fault, not the reader's: let the form try
    return () => { gone = true; };
  }, [token]);

  if (ok) return <AuthCard title="Password set" lead="Every device was signed out. Sign in with your new password." icon="check" testid="reset-ok"><div className="form"><Link to="/sign-in" className="btn btn--primary btn--lg btn--block" data-testid="reset-signin">Sign in</Link></div></AuthCard>;
  if (live === null) return (
    <AuthCard title="Set a new password" lead="Checking your link." icon="key" testid="reset-checking">
      <div className="form"><p className="form-foot">One moment.</p></div>
    </AuthCard>
  );
  if (!live) return <DeadResetLink />;
  return (
    <AuthCard title="Set a new password" lead="This link works once." icon="key" testid="reset-page">
      <NewPasswordForm testid="reset-form" submitLabel="Save password" onSubmit={async (f) => { await post("/auth/reset-password", { token, password: f.a }); setOk(true); }} />
    </AuthCard>
  );
}

export function ChangePasswordFirst() {
  const { user, refresh } = useAuth();
  const nav = useNavigate();
  if (!user) return <AuthCard title="Sign in first" icon="padlock" testid="change-pw-signin"><div className="form"><Link to="/sign-in" className="btn btn--primary btn--block">Sign in</Link></div></AuthCard>;
  return (
    <AuthCard title="Choose your own password" lead="You signed in with a first password. Replace it now; other devices will be signed out." icon="key" testid="change-pw-page">
      <NewPasswordForm needCurrent testid="change-pw-form" submitLabel="Save and continue"
                       onSubmit={async (f) => { await post("/account/password", { current: f.current, new: f.a }); await refresh(); nav(user.role !== "user" ? "/admin" : "/"); }} />
    </AuthCard>
  );
}

export function RecoveryCodes({ codes, onDone }) {
  const [saved, setSaved] = useState(false);
  const download = () => {
    const url = URL.createObjectURL(new Blob([codes.join("\n") + "\n"], { type: "text/plain" }));
    const a = document.createElement("a"); a.href = url; a.download = "recovery-codes.txt"; a.click(); URL.revokeObjectURL(url);
  };
  return (
    <div className="form" data-testid="recovery-codes">
      <p>Each code works once if you lose your phone. We show them only now. Keep them somewhere safe and offline.</p>
      <ol className="codes">{codes.map((c) => <li key={c}><code>{c}</code></li>)}</ol>
      <button type="button" className="btn btn--secondary btn--block" onClick={download} data-testid="recovery-download"><Icon name="download" size={16} />Download as a text file</button>
      <label className="check-row"><input type="checkbox" checked={saved} onChange={(e) => setSaved(e.target.checked)} data-testid="recovery-saved-check" /> I saved them</label>
      <button type="button" className="btn btn--primary btn--lg btn--block" disabled={!saved} onClick={onDone} data-testid="recovery-done">Continue</button>
    </div>
  );
}

export function TwoFactorSetup({ onFinished }) {
  const [begin, setBegin] = useState(null);
  const [code, setCode] = useState("");
  const [codes, setCodes] = useState(null);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { post("/account/2fa/begin").then(setBegin).catch(setErr); }, []);
  const confirm = async (e) => {
    e.preventDefault(); setBusy(true); setErr(null);
    try { const r = await post("/account/2fa/confirm", { code }); setCodes(r.recovery_codes || []); } catch (x) { setErr(x); } finally { setBusy(false); }
  };
  if (codes) return <RecoveryCodes codes={codes} onDone={onFinished} />;
  if (!begin) return err ? <FormError error={err} /> : <div className="skel" style={{ height: 200 }} />;
  return (
    <form className="form" onSubmit={confirm} data-testid="twofa-setup">
      <ol className="steps">
        <li>Open an authenticator app (Google Authenticator, 1Password, Authy…) and scan this code.</li>
      </ol>
      <div className="qr" data-testid="twofa-qr"><QRCodeSVG value={begin.otpauth_uri} size={176} bgColor="#FFFFFF" fgColor="#0A0E17" includeMargin /></div>
      <details className="manual-key"><summary>Can't scan? Type this key</summary><code data-testid="twofa-secret">{begin.secret.match(/.{1,4}/g).join(" ")}</code></details>
      <Field label="Then enter the 6-digit code it shows" inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} testid="twofa-code" />
      <FormError error={err} />
      <button className="btn btn--primary btn--lg btn--block" disabled={busy || code.length !== 6} data-testid="twofa-confirm">{busy ? "Checking…" : "Turn on two-factor sign-in"}</button>
    </form>
  );
}

export function Enroll2FA() {
  const { me, user, refresh } = useAuth();
  const nav = useNavigate();
  if (!user) return <AuthCard title="Sign in first" icon="padlock" testid="enroll-signin"><div className="form"><Link to="/sign-in" className="btn btn--primary btn--block">Sign in</Link></div></AuthCard>;
  if (user.two_factor && me?.scope !== "enroll_2fa") return <AuthCard title="Two-factor is on" icon="check" testid="enroll-done"><div className="form"><Link to={user.role !== "user" ? "/admin" : "/account/security"} className="btn btn--primary btn--block">Continue</Link></div></AuthCard>;
  const finished = async () => { const m = await refresh(); nav(m?.user?.must_change_password ? "/change-password" : user.role !== "user" ? "/admin" : "/account/security"); };
  return (
    <AuthCard title="Set up two-factor sign-in" lead={user.role !== "user" ? "Staff accounts must use a second step. It takes a minute." : "Add a second step to your sign-in."} icon="shield" testid="enroll-page">
      <TwoFactorSetup onFinished={finished} />
    </AuthCard>
  );
}
