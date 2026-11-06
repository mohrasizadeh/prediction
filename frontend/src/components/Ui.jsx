// Shared form and overlay parts: fields, password field, switch, tabs, sheet, confirm dialog, toasts.
import { createContext, useCallback, useContext, useEffect, useId, useRef, useState } from "react";
import Icon from "./Icon";
import { sayError } from "../lib/errors";

export function Field({ label, hint, error, testid, as = "input", children, ...p }) {
  const id = useId();
  const Tag = as;
  return (
    <div className={"field" + (error ? " field--error" : "")}>
      <label htmlFor={id}>{label}</label>
      <Tag id={id} data-testid={testid} aria-invalid={!!error} aria-describedby={error ? id + "-e" : hint ? id + "-h" : undefined} {...p}>{as === "input" ? undefined : children}</Tag>
      {hint && !error && <small id={id + "-h"} className="field-hint">{hint}</small>}
      {error && <small id={id + "-e"} className="field-err" role="alert">{error}</small>}
    </div>
  );
}

export function PasswordField({ label = "Password", testid, ...p }) {
  const id = useId();
  const [show, setShow] = useState(false);
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <div className="pw-wrap">
        <input id={id} type={show ? "text" : "password"} data-testid={testid} {...p} />
        <button type="button" className="pw-toggle" onClick={() => setShow((s) => !s)} aria-label={show ? "Hide password" : "Show password"} data-testid={testid ? testid + "-toggle" : undefined}>
          <Icon name={show ? "eye-off" : "eye"} size={18} />
        </button>
      </div>
    </div>
  );
}

export function Switch({ checked, onChange, label, hint, disabled, testid }) {
  return (
    <label className={"switch-row" + (disabled ? " is-disabled" : "")}>
      <span className="switch-text"><span>{label}</span>{hint && <small>{hint}</small>}</span>
      <input type="checkbox" role="switch" className="switch" checked={!!checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} data-testid={testid} />
    </label>
  );
}

export function Tabs({ tabs, value, onChange, testid = "tabs", className = "" }) {
  return (
    <div className={`tabs ${className}`.trim()} role="tablist" data-testid={testid}>
      {tabs.map((t) => (
        <button key={t.id} role="tab" type="button" aria-selected={value === t.id} className={"tab" + (value === t.id ? " is-on" : "")} onClick={() => onChange(t.id)} data-testid={`${testid}-${t.id}`}>
          {t.icon && <Icon name={t.icon} size={16} />}{t.label}{t.badge != null && <em className="tab-badge">{t.badge}</em>}
        </button>
      ))}
    </div>
  );
}

export const FormError = ({ error }) => (error ? <p className="form-error" role="alert" data-testid="form-error"><Icon name="alert" size={16} />{typeof error === "string" ? error : sayError(error)}</p> : null);

export function useEsc(on, fn) {
  useEffect(() => {
    if (!on) return undefined;
    const h = (e) => e.key === "Escape" && fn();
    document.addEventListener("keydown", h);
    return () => document.removeEventListener("keydown", h);
  }, [on, fn]);
}

export function useFocusTrap(ref, open) {
  useEffect(() => {
    if (!open || !ref.current) return undefined;
    const prev = document.activeElement;
    const el = ref.current;
    const q = () => [...el.querySelectorAll("button,[href],input,select,textarea,[tabindex]:not([tabindex='-1'])")].filter((x) => !x.disabled);
    const first = el.querySelector("[data-autofocus]") || q()[0];
    first?.focus();
    const onKey = (e) => {
      if (e.key !== "Tab") return;
      const f = q();
      if (!f.length) return;
      if (e.shiftKey && document.activeElement === f[0]) { e.preventDefault(); f[f.length - 1].focus(); }
      else if (!e.shiftKey && document.activeElement === f[f.length - 1]) { e.preventDefault(); f[0].focus(); }
    };
    el.addEventListener("keydown", onKey);
    document.body.classList.add("no-scroll");
    return () => { el.removeEventListener("keydown", onKey); document.body.classList.remove("no-scroll"); prev?.focus?.(); };
  }, [open, ref]);
}

// Side drawer at >=1025 px, full-screen sheet below (docs/17 §5).
export function Drawer({ open, onClose, title, children, footer, testid = "drawer", wide }) {
  const ref = useRef(null);
  useEsc(open, onClose);
  useFocusTrap(ref, open);
  if (!open) return null;
  return (
    <div className="overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div ref={ref} className={"drawer" + (wide ? " drawer--wide" : "")} role="dialog" aria-modal="true" aria-label={title} data-testid={testid}>
        <header className="drawer-head">
          <button className="icon-btn" onClick={onClose} aria-label="Close" data-testid={`${testid}-close`}><Icon name="chevron-left" className="only-phone" /><Icon name="x" className="only-desk" /></button>
          <h2>{title}</h2>
        </header>
        <div className="drawer-body">{children}</div>
        {footer && <footer className="drawer-foot">{footer}</footer>}
      </div>
    </div>
  );
}

// Centred on computers, bottom sheet on phones. Danger button on the right, never focused first.
export function Confirm({ open, title, body, confirmLabel = "Confirm", danger, reason, typed, busy, onConfirm, onClose, testid = "confirm" }) {
  const ref = useRef(null);
  const [text, setText] = useState("");
  const [err, setErr] = useState(null);
  useEsc(open, onClose);
  useFocusTrap(ref, open);
  useEffect(() => { if (open) { setText(""); setErr(null); } }, [open]);
  if (!open) return null;
  const blocked = (reason && !text.trim()) || (typed && text !== typed);
  const go = async (e) => {
    e.preventDefault();
    try { await onConfirm(text.trim()); } catch (x) { setErr(x); }
  };
  return (
    <div className="overlay overlay--center" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <form ref={ref} className="dialog" role="alertdialog" aria-modal="true" aria-label={title} onSubmit={go} data-testid={testid}>
        <h2>{title}</h2>
        {body && <div className="dialog-body">{body}</div>}
        {(reason || typed) && (
          <Field label={typed ? `Type ${typed} to confirm` : reason} value={text} onChange={(e) => setText(e.target.value)} testid={`${testid}-input`} data-autofocus maxLength={200} />
        )}
        <FormError error={err} />
        <div className="dialog-actions">
          <button type="button" className="btn btn--secondary" onClick={onClose} data-testid={`${testid}-cancel`} data-autofocus={!reason && !typed ? true : undefined}>Cancel</button>
          <button type="submit" className={"btn " + (danger ? "btn--danger" : "btn--primary")} disabled={blocked || busy} data-testid={`${testid}-ok`}>{confirmLabel}</button>
        </div>
      </form>
    </div>
  );
}

const ToastCtx = createContext(() => {});
export function ToastProvider({ children }) {
  const [items, setItems] = useState([]);
  const push = useCallback((msg, kind = "ok") => {
    const id = Math.random().toString(36).slice(2);
    setItems((x) => [...x, { id, msg, kind }]);
    setTimeout(() => setItems((x) => x.filter((t) => t.id !== id)), 4200);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {items.map((t) => <div key={t.id} className={"toast toast--" + t.kind} data-testid="toast"><Icon name={t.kind === "err" ? "alert" : "check"} size={16} />{t.msg}</div>)}
      </div>
    </ToastCtx.Provider>
  );
}
export const useToast = () => useContext(ToastCtx);
