// Small shared helpers for R7: days with games (date scroller dots) and "your leagues first" ordering.
import { useMemo } from "react";
import { useApi } from "./useApi";
import { useAuth } from "./auth";

const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

export function useGameDays(from = -1, count = 7) {
  const start = useMemo(() => { const d = new Date(); d.setDate(d.getDate() + from); return iso(d); }, [from]);
  const q = useApi("/match-days", { start, days: count, tz_offset_min: -new Date().getTimezoneOffset() });
  return useMemo(() => new Set(q.data?.days || []), [q.data]);
}

// Which leagues play on each day: { "2026-11-01": [{id, name, image, matches}, ...] }, most matches first.
export function useDayLeagues(from = -1, count = 7) {
  const start = useMemo(() => { const d = new Date(); d.setDate(d.getDate() + from); return iso(d); }, [from]);
  const q = useApi("/match-days", { start, days: count, tz_offset_min: -new Date().getTimezoneOffset() });
  return useMemo(() => q.data?.leagues || {}, [q.data]);
}

export function useFavLeagues() {
  const { user } = useAuth();
  return user?.prefs?.leagues || [];
}

export const favFirst = (rows, fav, idOf) => (fav.length ? [...rows].sort((a, b) => (fav.includes(idOf(b)) - fav.includes(idOf(a)))) : rows);
