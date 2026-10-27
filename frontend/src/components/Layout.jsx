// App frame drawn from the site config (docs/16 §2.7): header with Beta tag, desktop rail or top menu, phone bottom bar
// from nav.mobile_tabs plus More, announcements, footer with the disclaimer, cookie banner, maintenance page.
import { useCallback, useEffect, useRef, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../lib/auth";
import { useApi } from "../lib/useApi";
import { get, patch } from "../lib/api";
import { DISCLAIMER } from "../lib/copy";
import { utc } from "../lib/time";
import { audienceOk, route, useSite } from "../lib/site";
import Icon from "./Icon";
import { BrandLogo } from "./Media";
import { useEsc } from "./Ui";
import PopupHost from "./Popups";
import NewsletterForm from "./Newsletter";
import { setConsent, usePageBeacon, useTagLoader } from "../lib/growth";

function ago(iso) {
  if (!iso) return null;
  const h = Math.round((Date.now() - utc(iso).getTime()) / 36e5);
  return h < 1 ? "less than an hour ago" : h === 1 ? "1 hour ago" : h < 48 ? `${h} hours ago` : `${Math.round(h / 24)} days ago`;
}

const isExternal = (r) => /^https:\/\//.test(r || "");
function NavItem({ item, className, onClick, testid }) {
  const r = route(item.route);
  const body = <><Icon name={item.icon} size={20} /><span>{item.label}</span>{item.badge && <em className="nav-badge">{item.badge}</em>}</>;
  if (isExternal(r)) return <a href={r} className={className} target="_blank" rel="noopener noreferrer" data-testid={testid}>{body}</a>;
  return <NavLink to={r} end={r === "/"} className={className} onClick={onClick} data-testid={testid}>{body}</NavLink>;
}

function ThemeToggle() {
  const { cfg, setTheme } = useSite();
  const { user, setUser } = useAuth();
  if (cfg?.theme?.allow_toggle === false) return null;
  const now = document.documentElement.dataset.theme === "light" ? "light" : "dark";
  const flip = async () => {
    const next = now === "light" ? "dark" : "light";
    setTheme(next);
    if (user) patch("/account/profile", { theme: next }).then((r) => setUser(r.user)).catch(() => {});
  };
  return (
    <button className="icon-btn" onClick={flip} aria-label={now === "light" ? "Switch to dark" : "Switch to light"} data-testid="theme-toggle">
      <Icon name={now === "light" ? "moon" : "sun"} />
    </button>
  );
}

const NO_BANNER = /^\/(sign-in|sign-up|enroll-2fa|change-password|reset-password|forgot-password|verify-email|confirm-email)/;
function CookieBanner({ c }) {
  const [choice, setChoice] = useState(() => localStorage.getItem("consent"));
  const { pathname } = useLocation();
  if (!c?.banner || choice || NO_BANNER.test(pathname)) return null;
  const pick = (v) => { setConsent(v); setChoice(v); };
  return (
    <div className="cookie" role="region" aria-label="Privacy choices" data-testid="cookie-banner">
      <p>{c.text} {c.policy_route && <Link to={route(c.policy_route)}>Read more</Link>}</p>
      <div className="cookie-actions">
        <button className="btn btn--secondary btn--sm" onClick={() => pick("essential")} data-testid="cookie-reject">{c.reject_label || "No thanks"}</button>
        <button className="btn btn--primary btn--sm" onClick={() => pick("all")} data-testid="cookie-accept">{c.accept_label || "Allow optional"}</button>
      </div>
    </div>
  );
}

function Announcements() {
  const a = useApi("/announcements");
  const [hidden, setHidden] = useState([]);
  const items = (a.data?.items || []).filter((x) => !hidden.includes(x.id || x.text));
  return items.map((x) => (
    <div key={x.id || x.text} className={"announce announce--" + (x.level || "info")} role="status" data-testid="announcement">
      <div className="wrap announce-row"><Icon name={x.level === "warn" ? "alert" : "info"} size={16} /><p>{x.text}</p>
        <button className="icon-btn icon-btn--sm" aria-label="Hide message" onClick={() => setHidden((h) => [...h, x.id || x.text])} data-testid="announcement-close"><Icon name="x" size={16} /></button>
      </div>
    </div>
  ));
}

function MoreSheet({ open, onClose, items, user, signOut }) {
  const ref = useRef(null);
  useEsc(open, onClose);
  useEffect(() => { if (open) ref.current?.querySelector("a,button")?.focus(); }, [open]);
  if (!open) return null;
  return (
    <div className="overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div ref={ref} className="sheet" role="dialog" aria-modal="true" aria-label="More" data-testid="more-sheet">
        <header className="sheet-head"><h2>More</h2><button className="icon-btn" onClick={onClose} aria-label="Close" data-testid="more-sheet-close"><Icon name="x" /></button></header>
        <div className="sheet-grid">
          {items.map((i) => <NavItem key={i.id} item={i} className="tile" onClick={onClose} testid={`more-item-${i.id}`} />)}
          <NavLink to="/track-record" className="tile" onClick={onClose} data-testid="more-item-track-record"><Icon name="trending-up" /><span>Track record</span></NavLink>
          <NavLink to="/referees" className="tile" onClick={onClose} data-testid="more-item-referees"><Icon name="flag" /><span>Referees</span></NavLink>
          {user ? <NavLink to="/account" className="tile" onClick={onClose} data-testid="more-item-account"><Icon name="user" /><span>Account</span></NavLink>
                : <NavLink to="/sign-in" className="tile" onClick={onClose} data-testid="more-item-sign-in"><Icon name="user" /><span>Sign in</span></NavLink>}
        </div>
        <div className="sheet-foot"><ThemeToggle />{user && <button className="btn btn--secondary btn--sm" onClick={() => { onClose(); signOut(); }} data-testid="more-sign-out"><Icon name="log-out" size={16} />Sign out</button>}</div>
      </div>
    </div>
  );
}

function Footer({ cfg, updated, mode }) {
  const f = cfg?.footer || {};
  return (
    <footer className="footer" data-testid="site-footer">
      <div className="wrap">
        <NewsletterForm />
        <div className="footer-cols">
          <div className="footer-brand"><BrandLogo brand={cfg?.brand} mode={mode} /><strong>{cfg?.brand?.name || "Prediciotn"}</strong><p>{cfg?.brand?.tagline}</p></div>
          {(f.columns || []).map((c) => (
            <nav key={c.title} aria-label={c.title} className="footer-col"><h3>{c.title}</h3>
              {(c.links || []).map((l) => isExternal(l.route) ? <a key={l.label} href={l.route} target="_blank" rel="noopener noreferrer">{l.label}</a> : <Link key={l.label} to={route(l.route)}>{l.label}</Link>)}
            </nav>
          ))}
        </div>
        <p className="disclaimer" data-testid="footer-disclaimer">{cfg?.disclaimer || DISCLAIMER}</p>
        <div className="footer-meta">
          {updated && <span data-testid="data-updated">Data updated {updated}.</span>}
          {f.show_data_credit && cfg?.data_credit && <span>{cfg.data_credit}</span>}
          {f.legal_line && <span>{f.legal_line}</span>}
          {(f.social || []).map((s) => <a key={s.url} href={s.url} target="_blank" rel="noopener noreferrer">{s.kind}</a>)}
        </div>
      </div>
    </footer>
  );
}

// Follows the data-theme attribute that ThemeSync sets on <html>.
function useThemeMode() {
  const get = () => (document.documentElement.dataset.theme === "light" ? "light" : "dark");
  const [mode, setMode] = useState(get);
  useEffect(() => {
    const ob = new MutationObserver(() => setMode(get()));
    ob.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => ob.disconnect();
  }, []);
  return mode;
}

export function Maintenance({ message }) {
  return <div className="maint" data-testid="maintenance-page"><Icon name="clock" size={32} /><h1>Back shortly</h1><p>{message}</p></div>;
}

function BookingBell() {
  const { pathname } = useLocation();
  const [n, setN] = useState(0);
  useEffect(() => {
    const ac = new AbortController();
    get("/me/booking-risk", null, { signal: ac.signal }).then((r) => setN(r.rows?.length || 0)).catch(() => {});
    return () => ac.abort();
  }, [pathname]);
  const label = n ? `${n} followed player${n === 1 ? "" : "s"} may be booked this round` : "No booking alerts";
  return (
    <Link to="/following" className="icon-btn bell-btn" aria-label={label} title={label} data-testid="header-bell">
      <Icon name="bell" />{n > 0 && <span className="bell-badge" data-testid="header-bell-count">{n > 9 ? "9+" : n}</span>}
    </Link>
  );
}

export default function Layout({ children }) {
  const { user, me, signOut } = useAuth();
  const { cfg, preview } = useSite();
  const loc = useLocation();
  const status = useApi("/public/status");
  const updated = ago(status.data?.data_updated_at);
  const [more, setMore] = useState(false);
  const mode = useThemeMode();
  const closeMore = useCallback(() => setMore(false), []);
  const nav = cfg?.nav || {};
  const items = (nav.items || []).filter((i) => i.enabled !== false && audienceOk(i.audience, user, me));
  const tabs = (nav.mobile_tabs || []).map((id) => items.find((i) => i.id === id)).filter(Boolean).slice(0, 4);
  const rest = items.filter((i) => !tabs.includes(i));
  const cta = nav.header_cta?.enabled && audienceOk(nav.header_cta.audience, user, me) ? nav.header_cta : null;
  const rail = nav.desktop_layout !== "top";
  const staff = user && user.role !== "user";
  const maint = cfg?.maintenance?.on && !staff && !/^\/(sign-in|enroll-2fa|reset-password)/.test(loc.pathname);
  useEffect(() => { window.scrollTo(0, 0); }, [loc.pathname]);
  usePageBeacon(loc.pathname);
  useTagLoader(cfg?.tracking, loc.pathname);

  return (
    <div className={"app" + (rail ? " app--rail" : "")}>
      <a className="skip" href="#main">Skip to content</a>
      {preview && <div className="preview-bar" data-testid="preview-bar">Preview of the draft look. Visitors do not see this.</div>}
      <header className="header" data-testid="site-header">
        <div className="header-row">
          <Link to="/" className="brand" data-testid="brand-link"><BrandLogo brand={cfg?.brand} mode={mode} /><span className="brand-name">{cfg?.brand?.name || "Prediciotn"}</span></Link>
          <span className="beta" data-testid="beta-tag" title="Tested on simulated data only">Beta</span>
          {!rail && <nav className="top-nav" aria-label="Main">{items.map((i) => <NavItem key={i.id} item={i} testid={`top-nav-${i.id}`} />)}</nav>}
          <div className="header-actions">
            {nav.show_search !== false && <Link to="/search" className="icon-btn" aria-label="Search" data-testid="header-search"><Icon name="search" /></Link>}
            <span className="only-desk"><ThemeToggle /></span>
            {user ? (
              <>
                {staff && <Link to="/admin" className="btn btn--ghost btn--sm only-desk" data-testid="header-admin">Admin</Link>}
                <BookingBell />
                <Link to="/account" className="avatar-btn" aria-label="Account" data-testid="header-account">{(user.display_name || user.email || "?")[0].toUpperCase()}</Link>
              </>
            ) : (
              <>
                <Link to="/sign-in" className="btn btn--ghost btn--sm" data-testid="header-sign-in">Sign in</Link>
                {cta && <Link to={route(cta.route)} className="btn btn--primary btn--sm only-desk" data-testid="header-cta">{cta.label}</Link>}
              </>
            )}
          </div>
        </div>
      </header>
      <Announcements />
      <div className="body-row">
        {rail && (
          <aside className="rail" aria-label="Main">
            <nav>{items.map((i) => <NavItem key={i.id} item={i} className="rail-link" testid={`rail-${i.id}`} />)}
              <NavLink to="/track-record" className="rail-link" data-testid="rail-track-record"><Icon name="trending-up" size={20} /><span>Track record</span></NavLink>
              <NavLink to="/referees" className="rail-link" data-testid="rail-referees"><Icon name="flag" size={20} /><span>Referees</span></NavLink>
            </nav>
          </aside>
        )}
        <div className="page-col">
          <main id="main" className="wrap main">{maint ? <Maintenance message={cfg.maintenance.message} /> : children || <Outlet />}</main>
          <Footer cfg={cfg} updated={updated} mode={mode} />
        </div>
      </div>
      <nav className="bottom-tabs" aria-label="Main" data-testid="bottom-tabs">
        {tabs.map((t) => <NavItem key={t.id} item={t} className="btab" testid={`tab-${t.id}`} />)}
        {nav.mobile_more !== false && (
          <button className={"btab" + (more ? " active" : "")} onClick={() => setMore(true)} aria-haspopup="dialog" data-testid="tab-more"><Icon name="grid" size={20} /><span>More</span></button>
        )}
      </nav>
      <MoreSheet open={more} onClose={closeMore} items={rest} user={user} signOut={signOut} />
      <CookieBanner c={cfg?.cookies} />
      {!maint && !preview && <PopupHost enabled={!!cfg?.popups_enabled} waitForCookies={!!cfg?.cookies?.banner} />}
    </div>
  );
}
