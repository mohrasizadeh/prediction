// A placeholder screen for Emergent to build out. It names the spec, the routes, and shows the live answer of the
// main route so the wiring can be checked before any design work. Replace each Spec with the real screen.
import { useApi } from "../lib/useApi";
import { ErrorBox, Loading } from "./States";

export default function Spec({ title, docs, routes = [], probe, query, children }) {
  const live = useApi(probe, query);
  return (
    <section className="spec">
      <h1>{title}</h1>
      <p className="muted">To build. Spec: {docs}.</p>
      {routes.length > 0 && (
        <ul className="spec-routes">
          {routes.map((r) => <li key={r}><code>{r}</code></li>)}
        </ul>
      )}
      {children}
      {probe && (
        <details className="card">
          <summary>Live answer from <code>{probe}</code></summary>
          {live.loading ? <Loading /> : live.error ? <ErrorBox error={live.error} onRetry={live.reload} /> : <pre>{JSON.stringify(live.data, null, 2).slice(0, 4000)}</pre>}
        </details>
      )}
    </section>
  );
}
