// Small data hook: {data, error, loading, reload}. Cancels on unmount or when the key changes.
import { useCallback, useEffect, useState } from "react";
import { get } from "./api";

export function useApi(path, query) {
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
  const reload = useCallback(() => setN((x) => x + 1), []);
  return { ...state, reload };
}
