// Small data hook: {data, error, loading, reload}. Cancels on unmount or when the key changes.
import { useCallback, useEffect, useState } from "react";
import { get } from "./api";

export function useApi(path, query, opts) {
  const every = opts?.every || 0;                       // milliseconds; refreshes quietly while the tab is visible
  const key = path ? path + JSON.stringify(query || {}) : null;
  const [state, setState] = useState({ data: null, error: null, loading: !!path });
  const [n, setN] = useState(0);
  useEffect(() => {
    if (!path) return undefined;
    const ac = new AbortController();
    setState((s) => ({ ...s, loading: true, error: null }));
    get(path, query, { signal: ac.signal })
      .then((data) => setState({ data, error: null, loading: false }))
      .catch((error) => error.name !== "AbortError" && setState({ data: null, error, loading: false }));
    return () => ac.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, n]);
  useEffect(() => {
    if (!path || !every) return undefined;
    const tick = () => { if (document.visibilityState === "visible") get(path, query).then((data) => setState((s) => (s.error ? s : { data, error: null, loading: false }))).catch(() => {}); };
    const t = setInterval(tick, every);
    document.addEventListener("visibilitychange", tick);
    return () => { clearInterval(t); document.removeEventListener("visibilitychange", tick); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, every]);
  const reload = useCallback(() => setN((x) => x + 1), []);
  return { ...state, reload };
}
