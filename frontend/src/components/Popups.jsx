// Public popups (docs/16 §3.2): the server says which popups may show here; the browser applies trigger, frequency and limits.
import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { get, post } from "../lib/api";
import { useAuth } from "../lib/auth";
import { PRIVATE_PATHS, visitorId, visitorType } from "../lib/growth";
import Icon from "./Icon";
import { useEsc } from "./Ui";

const BASE = (process.env.REACT_APP_BACKEND_URL || "").replace(/\/$/, "");
const DAY = 864e5;
const mem = (id) => { try { return JSON.parse(localStorage.getItem("pop:" + id)) || {}; } catch { return {}; } };
const remember = (id, k) => localStorage.setItem("pop:" + id, JSON.stringify({ ...mem(id), [k]: Date.now() }));
const shownThisSession = () => JSON.parse(sessionStorage.getItem("pop_shown") || "[]");

function allowedByFrequency(p) {
  const m = mem(p.id);
  const f = p.frequency || {};
  if (m.acted && Date.now() - m.acted < (f.after_action_days || 90) * DAY) return false;
  if (f.mode === "once") return !m.seen;
  if (f.mode === "every_session") return !shownThisSession().includes(p.id);
  if (f.mode === "every_n_days") return !m.seen || Date.now() - m.seen > (f.n_days || 7) * DAY;
  return !m.acted;
}

function track(id, event) { post(`/popups/${id}/event`, { event }).catch(() => {}); }

function PopupForm({ p, onDone }) {
  const [email, setEmail] = useState("");
  const [ok, setOk] = useState(false);
  const [msg, setMsg] = useState(null);
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);
  const send = async (e) => {
    e.preventDefault();
    setBusy(true); setMsg(null);
    try { await post(`/popups/${p.id}/submit`, { email, consent: ok }); setSent(true); onDone(); }
    catch (x) { setMsg(x.message); }
    setBusy(false);
  };
  if (sent) return <p className="pop-success" role="status" data-testid="popup-form-success">{p.form.success_text}</p>;
  return (
    <form className="pop-form" onSubmit={send} data-testid="popup-form">
      <div className="pop-form-row">
        <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder={p.form.placeholder} aria-label="E-mail address" autoComplete="email" data-testid="popup-form-email" />
        <button className="btn btn--primary" disabled={busy || !ok} data-testid="popup-form-submit">{p.form.button_label}</button>
      </div>
      <label className="pop-consent"><input type="checkbox" checked={ok} onChange={(e) => setOk(e.target.checked)} data-testid="popup-form-consent" /><span>{p.form.consent_text}</span></label>
      {msg && <p className="form-error" role="alert">{msg}</p>}
    </form>
  );
}

export function PopupView({ p, onClose, onAct, preview }) {
  const ref = useRef(null);
  const c = p.content || {};
  const d = p.design || {};
  const modal = p.kind === "modal";
  useEsc(true, onClose);
  useEffect(() => { if (modal) ref.current?.querySelector("input,button,a")?.focus(); }, [modal]);
  const img = c.image ? (c.image.startsWith("/api/") ? BASE + c.image : c.image) : null;
  const body = (
    <div ref={ref} className={`pop pop--${p.kind} pop--${d.size || "md"} pop--tone-${d.tone || "default"} pop--${d.align || "left"} pop--${d.position || "bottom_right"}`}
         role={modal ? "dialog" : "region"} aria-modal={modal || undefined} aria-label={c.title || "Message"} data-testid={preview ? "popup-preview" : "popup"}>
      {d.show_close !== false && <button className="icon-btn icon-btn--sm pop-close" onClick={onClose} aria-label="Close" data-testid="popup-close"><Icon name="x" size={16} /></button>}
      {img && <img src={img} alt={c.image_alt || ""} className="pop-img" />}
      <div className="pop-text">
        {c.title && <h2>{c.title}</h2>}
        {c.body && <p>{c.body}</p>}
      </div>
      {p.form?.enabled && <PopupForm p={p} onDone={() => onAct("submit")} />}
      {!!c.buttons?.length && (
        <div className="pop-actions">
          {c.buttons.map((b, i) => (b.action === "close"
            ? <button key={i} className={`btn btn--${b.style} btn--sm`} onClick={onClose} data-testid={`popup-btn-${i}`}>{b.label}</button>
            : /^https:/.test(b.route)
              ? <a key={i} href={b.route} target="_blank" rel="noopener noreferrer" className={`btn btn--${b.style} btn--sm`} onClick={() => onAct("click")} data-testid={`popup-btn-${i}`}>{b.label}</a>
              : <Link key={i} to={b.route} className={`btn btn--${b.style} btn--sm`} onClick={() => onAct("click", true)} data-testid={`popup-btn-${i}`}>{b.label}</Link>))}
        </div>
      )}
    </div>
  );
  if (!modal || preview) return body;
  return <div className="overlay overlay--center pop-overlay" onMouseDown={(e) => e.target === e.currentTarget && d.backdrop_close !== false && onClose()}>{body}</div>;
}

function useTrigger(p, fire) {
  useEffect(() => {
    if (!p) return undefined;
    const t = p.trigger || {};
    if (t.type === "immediate") { fire(); return undefined; }
    if (t.type === "delay") { const h = setTimeout(fire, (t.delay_s || 0) * 1000); return () => clearTimeout(h); }
    if (t.type === "pageviews") { if (Number(sessionStorage.getItem("pv") || 0) >= (t.pageviews || 1)) fire(); return undefined; }
    if (t.type === "scroll") {
      const on = () => { const h = document.documentElement; if ((h.scrollTop + window.innerHeight) / h.scrollHeight * 100 >= (t.scroll_pct || 50)) fire(); };
      window.addEventListener("scroll", on, { passive: true }); return () => window.removeEventListener("scroll", on);
    }
    if (t.type === "exit_intent") {
      const on = (e) => { if (!e.relatedTarget && e.clientY <= 0) fire(); };
      document.addEventListener("mouseout", on); return () => document.removeEventListener("mouseout", on);
    }
    if (t.type === "click") {
      const on = (e) => { if (e.target.closest?.(`[data-popup="${p.id}"]`)) { e.preventDefault(); fire(); } };
      document.addEventListener("click", on); return () => document.removeEventListener("click", on);
    }
    return undefined;
  }, [p, fire]);
}

export default function PopupHost({ enabled }) {
  const { pathname } = useLocation();
  const { user } = useAuth();
  const [limits, setLimits] = useState(null);
  const [cand, setCand] = useState(null);
  const [open, setOpen] = useState(null);
  useEffect(() => {
    setCand(null);
    if (!enabled || PRIVATE_PATHS.test(pathname)) return undefined;
    const ac = new AbortController();
    const device = matchMedia("(max-width: 768px)").matches ? "mobile" : "desktop";
    get("/popups", { path: pathname, device, visitor: visitorType(), vid: visitorId() }, { signal: ac.signal })
      .then((r) => { setLimits(r.limits); setCand((r.popups || []).find(allowedByFrequency) || null); }).catch(() => {});
    return () => ac.abort();
  }, [pathname, enabled, user?.id]);
  const fire = useCallback(() => {
    if (!cand || open) return;
    const shown = shownThisSession();
    const last = Number(sessionStorage.getItem("pop_last") || 0);
    if (limits && (shown.length >= limits.max_per_session || Date.now() - last < limits.min_gap_seconds * 1000)) return;
    sessionStorage.setItem("pop_shown", JSON.stringify([...shown, cand.id]));
    sessionStorage.setItem("pop_last", String(Date.now()));
    remember(cand.id, "seen");
    track(cand.id, "view");
    setOpen(cand);
    setCand(null);
  }, [cand, open, limits]);
  useTrigger(cand, fire);
  if (!open) return null;
  const close = () => { track(open.id, "dismiss"); setOpen(null); };
  const act = (ev, leave) => { track(open.id, ev); remember(open.id, "acted"); if (leave) setOpen(null); };
  return <PopupView p={open} onClose={close} onAct={act} />;
}
