// App frame drawn from the site config (docs/16 §2.7): header with Beta tag, desktop rail or top menu, phone bottom bar
// from nav.mobile_tabs plus More, announcements, footer with the disclaimer, cookie banner, maintenance page.
import { useCallback, useEffect, useState } from "react";
import { Link, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../lib/auth";
import { useApi } from "../lib/useApi";
import { get, patch } from "../lib/api";
import { DISCLAIMER } from "../lib/copy";
import { utc } from "../lib/time";
import { audienceOk, route, useSite } from "../lib/site";
import Icon from "./Icon";
import { BrandLogo, Crest, LeagueMark, PlayerAvatar } from "./Media";
import PopupHost from "./Popups";
import NewsletterForm from "./Newsletter";
import SearchOverlay from "./SearchOverlay";
import { LiveSheet, useLiveNow } from "./LiveSheet";
import { LivePill } from "./ui";
import { setConsent, usePageBeacon, useTagLoader } from "../lib/growth";

// Five sections, each a verb people already have in mind (docs/24 "Navigation").
const NAV5 = [
  { id: "today", label: "Today", icon: "calendar", to: "/", end: true },
  { id: "insights", label: "Insights", icon: "sparkles", to: "/insights" },
  { id: "finder", label: "Finder", icon: "target", to: "/finder" },
  { id: "explore", label: "Explore", icon: "compass", to: "/explore", also: /^\/(explore|leagues?|teams?|compare|referees?|track-record|learn|pricing|live)\b/ },
  { id: "you", label: "You", icon: "user", to: "/following", also: /^\/(following|account|saved)\b/ },
];
const FOOT_LINKS = [["Learn", "/learn"], ["Track record", "/track-record"], ["Plans", "/pricing"], ["Teams", "/teams"], ["Referees", "/referees"], ["Compare", "/compare"]];

function Nav5Item({ item, className, testid }) {
  const { pathname } = useLocation();
  const on = item.end ? pathname === "/" : pathname.startsWith(item.to) || (item.also && item.also.test(pathname));
  return (
    <Link to={item.to} className={className + (on ? " active" : "")} aria-current={on ? "page" : undefined} data-testid={testid}>
      <Icon name={item.icon} size={20} /><span>{item.label}</span>
    </Link>
  );
}

function RailFollowing() {
  const q = useApi("/me/follows");
  const { reload } = q;
  useEffect(() => {
    window.addEventListener("follows-change", reload);
    return () => window.removeEventListener("follows-change", reload);
  }, [reload]);
  const items = (q.data?.items || []).slice(0, 6);
  if (!items.length) return null;
  return (
    <div className="rail-follow" data-testid="rail-following">
      <h2 className="k-sec">Following</h2>
      {items.map((f) => <Link key={`${f.kind}-${f.id}`} to={`/${f.kind}/${f.id}`} className="rail-follow-item" data-testid={`rail-follow-${f.id}`}>
        {f.kind === "player" ? <PlayerAvatar player={f} size={24} /> : f.kind === "league" ? <LeagueMark league={f} size={22} /> : <Crest team={f} size={24} />}<span>{f.name}</span></Link>)}
    </div>
  );
}

function useHeaderShrink() {
  const [small, setSmall] = useState(false);
  useEffect(() => {
    let last = window.scrollY;
    const on = () => { const y = window.scrollY; setSmall(y > 80 && y > last); last = y; };
    window.addEventListener("scroll", on, { passive: true });
    return () => window.removeEventListener("scroll", on);
  }, []);
  return small;
}

function ago(iso) {
  if (!iso) return null;
  const h = Math.round((Date.now() - utc(iso).getTime()) / 36e5);
  return h < 1 ? "less than an hour ago" : h === 1 ? "1 hour ago" : h < 48 ? `${h} hours ago` : `${Math.round(h / 24)} days ago`;
}

const isExternal = (r) => /^https:\/\//.test(r || "");

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

function Footer({ cfg, updated, mode }) {
  const f = cfg?.footer || {};
  const extra = (f.columns || []).flatMap((c) => c.links || []).map((l) => [l.label, l.route]);
  const links = [...FOOT_LINKS, ...extra].filter(([, r], i, a) => a.findIndex((x) => x[1] === r) === i && r !== "/");
  return (
    <footer className="footer" data-testid="site-footer">
      <div className="wrap">
        <NewsletterForm />
        <div className="foot2">
          <div className="foot2-brand"><BrandLogo brand={cfg?.brand} mode={mode} /><strong>{cfg?.brand?.name || "Prediciotn"}</strong><span>Football stats and forecasts, for information.</span></div>
          <nav aria-label="Footer" className="foot2-links" data-testid="footer-links">
            {links.map(([label, r]) => isExternal(r) ? <a key={r} href={r} target="_blank" rel="noopener noreferrer">{label}</a> : <Link key={r} to={route(r)} data-testid={`footer-link-${label.toLowerCase().replace(/\s+/g, "-")}`}>{label}</Link>)}
          </nav>
          <ThemeToggle />
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
    const on = () => get("/me/booking-risk").then((r) => setN(r.rows?.length || 0)).catch(() => {});
    window.addEventListener("follows-change", on);
    return () => { ac.abort(); window.removeEventListener("follows-change", on); };
  }, [pathname]);
  const label = n ? `${n} followed player${n === 1 ? "" : "s"} may be booked this round` : "No booking alerts";
  return (
    <Link to="/following" className="icon-btn bell-btn" aria-label={label} title={label} data-testid="header-bell">
      <Icon name="bell" />{n > 0 && <span className="bell-badge" data-testid="header-bell-count">{n > 9 ? "9+" : n}</span>}
    </Link>
  );
}

export default function Layout({ children }) {
  const { user, me } = useAuth();
  const { cfg, preview } = useSite();
  const loc = useLocation();
  const status = useApi("/public/status");
  const updated = ago(status.data?.data_updated_at);
  const [search, setSearch] = useState(false);
  const [liveOpen, setLiveOpen] = useState(false);
  const closeSearch = useCallback(() => setSearch(false), []);
  const closeLive = useCallback(() => setLiveOpen(false), []);
  const live = useLiveNow(liveOpen);
  const small = useHeaderShrink();
  const mode = useThemeMode();
  const nav = cfg?.nav || {};
  const cta = nav.header_cta?.enabled && audienceOk(nav.header_cta.audience, user, me) ? nav.header_cta : null;
  const rail = nav.desktop_layout !== "top";
  const staff = user && user.role !== "user";
  const maint = cfg?.maintenance?.on && !staff && !/^\/(sign-in|enroll-2fa|reset-password)/.test(loc.pathname);
  useEffect(() => { window.scrollTo(0, 0); setSearch(false); }, [loc.pathname]);
  useEffect(() => {
    const k = (e) => { if (e.key === "/" && !/input|textarea|select/i.test(e.target.tagName) && !e.target.isContentEditable) { e.preventDefault(); setSearch(true); } };
    document.addEventListener("keydown", k);
    return () => document.removeEventListener("keydown", k);
  }, []);
  usePageBeacon(loc.pathname);
  useTagLoader(cfg?.tracking, loc.pathname);

  return (
    <div className={"app" + (rail ? " app--rail" : "")}>
      <a className="skip" href="#main">Skip to content</a>
      {preview && <div className="preview-bar" data-testid="preview-bar">Preview of the draft look. Visitors do not see this.</div>}
      <header className={"header" + (small ? " header--small" : "")} data-testid="site-header">
        <div className="header-row">
          <Link to="/" className="brand" data-testid="brand-link"><BrandLogo brand={cfg?.brand} mode={mode} /><span className="brand-name">{cfg?.brand?.name || "Prediciotn"}</span></Link>
          <span className="beta" data-testid="beta-tag" title="Tested on simulated data only">Beta</span>
          {!rail && <nav className="top-nav" aria-label="Main">{NAV5.map((i) => <Nav5Item key={i.id} item={i} className="" testid={`top-nav-${i.id}`} />)}</nav>}
          {nav.show_search !== false && <button type="button" className="hsearch only-desk" onClick={() => setSearch(true)} data-testid="header-search-field"><Icon name="search" size={18} /><span>Search players, teams, leagues</span><kbd aria-hidden="true">/</kbd></button>}
          <div className="header-actions">
            {nav.show_search !== false && <button type="button" className="icon-btn only-phone" onClick={() => setSearch(true)} aria-label="Search" data-testid="header-search"><Icon name="search" /></button>}
            <span className="only-desk"><LivePill count={live?.live_count} onClick={() => setLiveOpen(true)} testid="header-live-pill" /></span>
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
            <nav>{NAV5.map((i) => <Nav5Item key={i.id} item={i} className="rail-link" testid={`rail-${i.id}`} />)}</nav>
            {user && <RailFollowing />}
          </aside>
        )}
        <div className="page-col">
          <main id="main" className="wrap main">{maint ? <Maintenance message={cfg.maintenance.message} /> : children || <Outlet />}</main>
          <Footer cfg={cfg} updated={updated} mode={mode} />
        </div>
      </div>
      <nav className="bottom-tabs" aria-label="Main" data-testid="bottom-tabs">
        {NAV5.map((t) => <Nav5Item key={t.id} item={t} className="btab" testid={`tab-${t.id}`} />)}
      </nav>
      <span className="only-phone"><LivePill count={live?.live_count} floating onClick={() => setLiveOpen(true)} testid="live-pill" /></span>
      <LiveSheet open={liveOpen} onClose={closeLive} data={live} />
      <SearchOverlay open={search} onClose={closeSearch} />
      <CookieBanner c={cfg?.cookies} />
      {!maint && !preview && <PopupHost enabled={!!cfg?.popups_enabled} waitForCookies={!!cfg?.cookies?.banner} />}
    </div>
  );
}
