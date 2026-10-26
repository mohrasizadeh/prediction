// Admin shell (docs/17): left rail >=1025 px; below, a bottom app bar (4 tabs + More) and a full-screen "All tools" sheet.
// The menu comes from GET /api/admin/shell. Hiding a module is a convenience; the server checks every route.
import { Component, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, NavLink, Route, Routes, useLocation } from "react-router-dom";
import { get, put } from "../lib/api";
import { useAuth } from "../lib/auth";
import Icon from "../components/Icon";
import { ErrorBox, Loading } from "../components/States";
import { useEsc, useToast } from "../components/Ui";
import { Chip } from "./parts";
import Dashboard from "./Dashboard";
import Users from "./Users";
import Staff from "./Staff";
import Settings from "./Settings";
import Keys from "./Keys";
import Logs from "./Logs";
import { Health, Security } from "./SecurityHealth";
import Studio from "./Studio";
import Content from "./Content";
import Inbox from "./Inbox";
import Announcements from "./Announcements";
import Plans from "./Plans";

const SCREENS = { dashboard: Dashboard, users: Users, staff: Staff, settings: Settings, keys: Keys, logs: Logs, security: Security, health: Health,
  studio: Studio, pages: Content, inbox: Inbox, announcements: Announcements, plans: Plans };
const SHORT = { "Site Studio": "Studio", "E-mail templates": "Templates", "E-mail list": "List", "Blocked addresses": "Blocked", "Endpoint explorer": "Explorer", "Cache and usage": "Cache", "Data quality": "Quality", Announcements: "News" };

export function useAdminShell() {
  const [s, setS] = useState({ data: null, error: null, loading: true });
  const load = useCallback(() => get("/admin/shell").then((data) => setS({ data, error: null, loading: false })).catch((error) => setS({ data: null, error, loading: false })), []);
  useEffect(() => { load(); }, [load]);
  return { ...s, reload: load, setTabs: (t) => setS((x) => ({ ...x, data: { ...x.data, mobile_tabs: t } })) };
}

function Soon({ m }) {
  return (
    <div className="a-soon" data-testid={`coming-soon-${m.id}`}>
      <span className="a-soon-ico"><Icon name={m.icon} size={28} /></span>
      <h1>{m.label}</h1>
      <p>Coming in the next phase.</p>
    </div>
  );
}

class Boundary extends Component {
  constructor(p) { super(p); this.state = { err: null }; }
  static getDerivedStateFromError(err) { return { err }; }
  componentDidUpdate(prev) { if (prev.path !== this.props.path && this.state.err) this.setState({ err: null }); }
  render() {
    if (!this.state.err) return this.props.children;
    return <div className="a-soon" role="alert" data-testid="admin-crash"><h1>This screen hit a problem</h1><p>Other tools still work. Reload to try again.</p><button className="btn btn--secondary" onClick={() => window.location.reload()}>Reload</button></div>;
  }
}

const sub = (route) => route.replace(/^\/admin\/?/, "");

function MoreSheet({ open, onClose, shell, onTabs, theme, setTheme, signOut }) {
  const toast = useToast();
  const ref = useRef(null);
  const [q, setQ] = useState("");
  const [edit, setEdit] = useState(false);
  const { pathname } = useLocation();
  useEsc(open, onClose);
  useEffect(() => {
    if (!open) return undefined;
    setQ(""); setEdit(false);
    document.body.classList.add("no-scroll");
    setTimeout(() => ref.current?.querySelector("input")?.focus(), 0);
    return () => document.body.classList.remove("no-scroll");
  }, [open]);
  if (!open) return null;
  const tabs = shell.mobile_tabs || [];
  const mods = shell.modules.filter((m) => m.label.toLowerCase().includes(q.toLowerCase()));
  const pin = async (id) => {
    let next = tabs.includes(id) ? tabs.filter((t) => t !== id) : [...tabs, id];
    if (next.length > 4) return toast("Bottom bar holds 4. Unpin one first.", "err");
    if (next.length < 2) return toast("Keep at least 2 in the bar.", "err");
    try { const r = await put("/admin/shell/tabs", { ids: next }); onTabs(r.mobile_tabs); } catch (x) { toast(x.message || "Could not save", "err"); }
  };
  return (
    <div className="a-sheet" role="dialog" aria-modal="true" aria-label="All tools" ref={ref} data-testid="admin-more-sheet">
      <header className="a-sheet-head">
        <h2>All tools</h2>
        <button className={"btn btn--sm " + (edit ? "btn--primary" : "btn--secondary")} onClick={() => setEdit((e) => !e)} data-testid="customize-bar">{edit ? "Done" : "Customize bar"}</button>
        <button className="a-icon-btn" onClick={onClose} aria-label="Close" data-testid="admin-more-close"><Icon name="x" /></button>
      </header>
      <div className="a-sheet-search"><Icon name="search" size={18} /><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search tools" aria-label="Search tools" data-testid="admin-more-search" /></div>
      <div className="a-sheet-body">
        {mods.length === 0 && <p className="a-muted" data-testid="admin-more-nothing">Nothing matches.</p>}
        {shell.groups.map((g) => {
          const list = mods.filter((m) => m.group === g);
          if (!list.length) return null;
          return (
            <section key={g} className="a-sheet-group">
              <h3>{g}</h3>
              <div className="a-tiles">
                {list.map((m) => (
                  <div key={m.id} className={"a-tilelink-wrap" + (pathname === m.route ? " is-current" : "")}>
                    <Link to={m.route} className="a-tilelink" onClick={onClose} data-testid={`admin-more-tile-${m.id}`}><Icon name={m.icon} size={26} /><span>{m.label}</span></Link>
                    {edit && <button className={"a-pin" + (tabs.includes(m.id) ? " is-on" : "")} onClick={() => pin(m.id)} aria-pressed={tabs.includes(m.id)} aria-label={`Pin ${m.label} to the bar`} data-testid={`pin-${m.id}`}><Icon name="pin" size={16} /></button>}
                  </div>
                ))}
              </div>
            </section>
          );
        })}
      </div>
      <footer className="a-sheet-foot">
        <button className="btn btn--secondary btn--sm" onClick={() => setTheme(theme === "dark" ? "light" : "dark")} data-testid="admin-more-theme"><Icon name={theme === "dark" ? "sun" : "moon"} size={16} />{theme === "dark" ? "Light" : "Dark"}</button>
        <Link to="/" className="btn btn--ghost btn--sm">View site</Link>
        <button className="btn btn--ghost btn--sm" onClick={signOut} data-testid="admin-more-signout"><Icon name="log-out" size={16} />Sign out</button>
      </footer>
    </div>
  );
}

function adminTheme() {
  const s = localStorage.getItem("admin-theme");
  return s === "light" || s === "dark" ? s : window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

export default function AdminApp() {
  const shell = useAdminShell();
  const { user, signOut } = useAuth();
  const { pathname } = useLocation();
  const [theme, setThemeS] = useState(adminTheme);
  const [more, setMore] = useState(false);
  const closeMore = useCallback(() => setMore(false), []);
  const setTheme = (t) => { localStorage.setItem("admin-theme", t); setThemeS(t); };
  const d = shell.data;
  const current = useMemo(() => d?.modules.find((m) => (m.route === "/admin" ? pathname === "/admin" || pathname === "/admin/" : pathname.startsWith(m.route))), [d, pathname]);
  useEffect(() => { document.title = `${current?.label || "Admin"} · Admin`; }, [current]);

  if (shell.loading) return <div className="admin" data-admin-theme={theme}><Loading /></div>;
  if (shell.error) return <div className="admin" data-admin-theme={theme}><div className="a-main"><ErrorBox error={shell.error} onRetry={shell.reload} /></div></div>;
  const tabs = (d.mobile_tabs || []).map((id) => d.modules.find((m) => m.id === id)).filter(Boolean).slice(0, 4);
  const inBar = tabs.includes(current);

  return (
    <div className="admin" data-admin-theme={theme} data-testid="admin-shell">
      <aside className="a-rail" aria-label="Admin" data-testid="admin-rail">
        <Link to="/admin" className="a-brand"><span className="a-brand-mark" />Control room</Link>
        <nav>
          {d.groups.map((g) => {
            const list = d.modules.filter((m) => m.group === g);
            if (!list.length) return null;
            return (
              <div key={g} className="a-rail-group">
                <h3>{g}</h3>
                {list.map((m) => (
                  <NavLink key={m.id} to={m.route} end={m.route === "/admin"} className="a-rail-link" data-testid={`admin-rail-${m.id}`}>
                    <Icon name={m.icon} size={18} /><span>{m.label}</span>
                    {m.id === "health" && d.open_alerts > 0 && <em className="a-badge">{d.open_alerts}</em>}
                  </NavLink>
                ))}
              </div>
            );
          })}
        </nav>
      </aside>
      <div className="a-col">
        <header className="a-top" data-testid="admin-topbar">
          <button className="a-icon-btn only-tab" onClick={() => setMore(true)} aria-label="All tools" data-testid="admin-menu-btn"><Icon name="menu" /></button>
          <strong className="a-top-title">{current?.label || "Admin"}</strong>
          <div className="a-top-actions">
            <Chip tone={d.billing_mode === "live" ? "down" : "warn"} testid="billing-mode-chip">{d.billing_mode === "live" ? "LIVE" : "TEST"} billing</Chip>
            <Chip tone="brand" testid="role-chip">{user?.role}</Chip>
            <button className="a-icon-btn only-wide" onClick={() => setTheme(theme === "dark" ? "light" : "dark")} aria-label={theme === "dark" ? "Switch to light" : "Switch to dark"} data-testid="admin-theme-toggle"><Icon name={theme === "dark" ? "sun" : "moon"} /></button>
            <Link to="/" className="a-icon-btn only-wide" aria-label="View site" data-testid="admin-view-site"><Icon name="external" /></Link>
            <button className="a-icon-btn only-wide" onClick={signOut} aria-label="Sign out" data-testid="admin-signout"><Icon name="log-out" /></button>
          </div>
        </header>
        <main className="a-main" id="main">
          <Boundary path={pathname}>
          <Routes>
            {d.modules.map((m) => {
              const C = SCREENS[m.id];
              return <Route key={m.id} path={sub(m.route) || "/"} element={C ? <C shell={d} /> : <Soon m={m} />} />;
            })}
            <Route path="*" element={<div className="a-soon" data-testid="admin-not-found"><h1>Not here</h1><p>This tool does not exist or your role cannot use it.</p></div>} />
          </Routes>
          </Boundary>
        </main>
      </div>
      <nav className="a-bar" aria-label="Admin tools" data-testid="admin-bottom-bar">
        {tabs.map((m) => (
          <NavLink key={m.id} to={m.route} end={m.route === "/admin"} className="a-bar-btn" data-testid={`admin-tab-${m.id}`}>
            <span className="a-bar-ico"><Icon name={m.icon} size={24} />{m.id === "dashboard" && d.open_alerts > 0 && <em className="a-dot">{d.open_alerts}</em>}</span>
            <span>{SHORT[m.label] || m.label}</span>
          </NavLink>
        ))}
        <button className={"a-bar-btn" + (!inBar || more ? " active" : "")} aria-current={!inBar ? "page" : undefined} onClick={() => setMore(true)} data-testid="admin-tab-more">
          <span className="a-bar-ico"><Icon name="grid" size={24} /></span><span>More</span>
        </button>
      </nav>
      <MoreSheet open={more} onClose={closeMore} shell={d} onTabs={shell.setTabs} theme={theme} setTheme={setTheme} signOut={signOut} />
    </div>
  );
}
