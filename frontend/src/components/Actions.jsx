// Signed-in actions: Save a forecast, Follow a team / player / league. Signed-out visitors are sent to sign in.
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { del, get, put } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useToast } from "./Ui";
import Icon from "./Icon";

function useGate() {
  const { user } = useAuth();
  const nav = useNavigate();
  return [user, () => nav(`/sign-in?next=${encodeURIComponent(window.location.pathname)}`)];
}

// One /me/saved read shared by every star on the page; dropped after any change.
let cache = null;
let cacheFor = null;
const savedKeys = (uid) => {
  if (cacheFor !== uid) { cache = null; cacheFor = uid; }
  cache = cache || get("/me/saved").then((d) => new Set(d.items.map((i) => i.fkey))).catch(() => { cache = null; return new Set(); });
  return cache;
};

export function SaveButton({ fkey }) {
  const [user, signIn] = useGate();
  const toast = useToast();
  const [on, setOn] = useState(false);
  useEffect(() => {
    if (!user) return undefined;
    let live = true;
    savedKeys(user.id).then((s) => { if (live) setOn(s.has(fkey)); });
    return () => { live = false; };
  }, [user, fkey]);
  const go = async () => {
    if (!user) return signIn();
    try {
      if (on) { await del("/me/saved", { fkey }); setOn(false); toast("Removed from saved"); }
      else { await put("/me/saved", { fkey }); setOn(true); toast("Saved. Find it in Following."); }
      cache = null;
    } catch (x) { toast(x.message || "Could not save that", "err"); }
  };
  return <button type="button" className={"icon-btn icon-btn--sm" + (on ? " is-on" : "")} aria-pressed={on} aria-label={on ? "Remove from saved" : "Save forecast"} onClick={go} data-testid={`save-${fkey}`}><Icon name="star" size={18} /></button>;
}

export function FollowButton({ kind, refId, name }) {
  const [user, signIn] = useGate();
  const toast = useToast();
  const [on, setOn] = useState(false);
  useEffect(() => {
    if (!user) return undefined;
    let live = true;
    get("/me/follows").then((d) => { if (live) setOn(d.items.some((i) => i.kind === kind && i.id === refId)); }).catch(() => {});
    return () => { live = false; };
  }, [user, kind, refId]);
  const go = async () => {
    if (!user) return signIn();
    try {
      if (on) { await del("/me/follows", { kind, ref_id: refId }); setOn(false); toast(`Stopped following ${name}`); }
      else { await put("/me/follows", { kind, ref_id: refId }); setOn(true); toast(`Following ${name}`); }
      window.dispatchEvent(new Event("follows-change"));
    } catch (x) { toast(x.message || "Could not do that", "err"); }
  };
  return <button type="button" className={"btn btn--sm " + (on ? "btn--secondary" : "btn--primary")} onClick={go} aria-pressed={on} data-testid={`follow-${kind}`}><Icon name={on ? "check" : "plus"} size={16} />{on ? "Following" : "Follow"}</button>;
}
