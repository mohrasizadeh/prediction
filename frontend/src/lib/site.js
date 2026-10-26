// Site config loader (docs/16 §2.7): fetch GET /api/site/config before first paint, inject its CSS and fonts,
// set the light/dark mode, revalidate every 60 s and on focus. The CSS string is only ever used as <style> text.
import { createContext, createElement, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { get } from "./api";

const SiteCtx = createContext(null);
const THEME_KEY = "theme-pref";

function styleEl(id) {
  let el = document.getElementById(id);
  if (!el) {
    el = document.createElement("style");
    el.id = id;
    document.head.appendChild(el);
  }
  return el;
}

function applyCss(cfg) {
  styleEl("site-theme").textContent = cfg?.theme?.css || "";
  const fonts = (cfg?.theme?.fonts || [])
    .filter((f) => /^\/fonts\/[a-z0-9-]+\.woff2$/.test(f.url || ""))
    .map((f) => `@font-face{font-family:'${String(f.family).replace(/'/g, "")}';src:url(${f.url}) format('woff2');font-weight:${f.weight || "100 900"};font-display:${f.display || "swap"};}`);
  styleEl("site-fonts").textContent = fonts.join("\n");
}

const systemMode = () => (window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark");

export function resolveMode(saved, cfg) {
  const allow = cfg?.theme?.allow_toggle !== false;
  const pick = allow && (saved === "light" || saved === "dark") ? saved : cfg?.theme?.default_mode;
  return pick === "light" || pick === "dark" ? pick : systemMode();
}

export function SiteProvider({ children }) {
  const preview = useMemo(() => new URLSearchParams(window.location.search).get("preview") || "", []);
  const [cfg, setCfg] = useState(null);
  const [failed, setFailed] = useState(false);
  const [pref, setPref] = useState(() => localStorage.getItem(THEME_KEY) || "system");

  const load = useCallback(async () => {
    try {
      const c = await get("/site/config", preview ? { preview } : undefined);
      setCfg(c);
      setFailed(false);
    } catch {
      setFailed(true);
    }
  }, [preview]);

  useEffect(() => {
    load();
    const t = setInterval(load, 60000);
    const onFocus = () => load();
    window.addEventListener("focus", onFocus);
    return () => { clearInterval(t); window.removeEventListener("focus", onFocus); };
  }, [load]);

  useEffect(() => {
    if (cfg) applyCss(cfg);
  }, [cfg]);

  const setTheme = useCallback((mode) => {
    localStorage.setItem(THEME_KEY, mode);
    setPref(mode);
  }, []);

  const value = { cfg, ready: !!cfg || failed, failed, preview: !!cfg?.preview, pref, setTheme, reload: load };
  return createElement(SiteCtx.Provider, { value }, children);
}

export const useSite = () => useContext(SiteCtx);

export function audienceOk(aud, user, me) {
  if (!aud || aud === "all") return true;
  if (aud === "signed_out") return !user;
  if (aud === "signed_in") return !!user;
  const paid = me?.plan && me.plan.plan_key !== "free" && me.plan.source !== "billing_off";
  if (aud === "paid") return !!user && paid;
  if (aud === "free") return !!user && !paid;
  return true;
}

// Old config routes -> our routes.
const ALIAS = { "/signup": "/sign-up", "/signin": "/sign-in", "/terms": "/legal/terms", "/privacy": "/legal/privacy", "/about": "/legal/about" };
export const route = (r) => ALIAS[r] || r;
