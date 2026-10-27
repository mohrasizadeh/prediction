// Visitor id, first-party page-view beacon, and the consent-gated tag loader (docs/16 §6.3, §7).
import { useEffect } from "react";
import { post } from "./api";

const rid = () => Math.random().toString(36).slice(2) + Date.now().toString(36);
export function visitorId() {
  let v = localStorage.getItem("vid");
  if (!v) { v = rid(); localStorage.setItem("vid", v); }
  return v.slice(0, 40);
}
export function visitorType() {
  if (!sessionStorage.getItem("visit")) {
    sessionStorage.setItem("visit", localStorage.getItem("seen") ? "returning" : "new");
    localStorage.setItem("seen", "1");
  }
  return sessionStorage.getItem("visit");
}
export const consent = () => localStorage.getItem("consent");
export const setConsent = (v) => { localStorage.setItem("consent", v); window.dispatchEvent(new Event("consent-change")); };
const privacySignal = () => navigator.doNotTrack === "1" || navigator.globalPrivacyControl === true;
export const PRIVATE_PATHS = /^\/(admin|sign-in|sign-up|signin|signup|login|reset|verify|enroll-2fa|change-password|forgot-password|reset-password|confirm-email|account\/billing|checkout|newsletter\/confirm|unsubscribe)/;

function utmFromUrl() {
  const q = new URLSearchParams(window.location.search);
  const u = { source: q.get("utm_source"), medium: q.get("utm_medium"), campaign: q.get("utm_campaign") };
  return u.source || u.medium || u.campaign ? Object.fromEntries(Object.entries(u).map(([k, v]) => [k, (v || "").slice(0, 80)])) : null;
}

let lastBeacon = { path: null, at: 0 };
export function usePageBeacon(pathname) {
  useEffect(() => {
    if (PRIVATE_PATHS.test(pathname)) return;
    if (lastBeacon.path === pathname && Date.now() - lastBeacon.at < 1000) return;
    lastBeacon = { path: pathname, at: Date.now() };
    const utm = utmFromUrl();
    const ref = document.referrer && !document.referrer.startsWith(window.location.origin) ? document.referrer.slice(0, 300) : undefined;
    post("/analytics/collect", { name: "page_view", path: pathname.slice(0, 200), ref, ...(utm ? { utm } : {}) }).catch(() => {});
    sessionStorage.setItem("pv", String(Number(sessionStorage.getItem("pv") || 0) + 1));
  }, [pathname]);
}

const loaded = new Set();
function addScript(id, src) {
  if (loaded.has(id)) return;
  loaded.add(id);
  const s = document.createElement("script");
  s.async = true; s.src = src; s.id = id;
  document.head.appendChild(s);
}
function loadGoogle(ids) {
  addScript("gtag", `https://www.googletagmanager.com/gtag/js?id=${encodeURIComponent(ids[0])}`);
  window.dataLayer = window.dataLayer || [];
  window.gtag = window.gtag || function gtag() { window.dataLayer.push(arguments); };
  window.gtag("js", new Date());
  ids.forEach((id) => window.gtag("config", id));
}
function loadMeta(id) {
  if (window.fbq) return;
  const f = function fbq() { f.callMethod ? f.callMethod.apply(f, arguments) : f.queue.push(arguments); };
  f.queue = []; f.loaded = true; f.version = "2.0"; window.fbq = f; window._fbq = f;
  addScript("fbq", "https://connect.facebook.net/en_US/fbevents.js");
  window.fbq("init", id); window.fbq("track", "PageView");
}

// Loads owner-enabled tags only after "Allow optional" (unless the owner turned consent off), never with DNT/GPC or on private pages.
export function useTagLoader(tracking, pathname) {
  useEffect(() => {
    const run = () => {
      if (!tracking?.enabled || privacySignal() || PRIVATE_PATHS.test(pathname)) return;
      if (tracking.require_consent !== false && consent() !== "all") return;
      const g = [tracking.ga4_id, tracking.google_ads_id].filter(Boolean);
      if (g.length) loadGoogle(g);
      if (tracking.meta_pixel_id) loadMeta(tracking.meta_pixel_id);
    };
    run();
    window.addEventListener("consent-change", run);
    return () => window.removeEventListener("consent-change", run);
  }, [tracking, pathname]);
}
