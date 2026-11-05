// My combos (docs/28 §1 and §7, board 7): coming up with the chance now, finished with which lines were reached,
// and "How our combined chances did". The summary is worked out here from the saved combos; it is not stored.
import { useState } from "react";
import { Link } from "react-router-dom";
import { del } from "../lib/api";
import { useApi } from "../lib/useApi";
import { useAuth } from "../lib/auth";
import { useCombo } from "../lib/combo";
import { pct } from "../lib/copy";
import { lineWhen } from "../components/ComboHost";
import Icon from "../components/Icon";
import { Crest, PlayerAvatar } from "../components/Media";
import { EmptyState, ErrorState, ForecastCard, Segmented, Skeleton } from "../components/ui";
import { useTitle } from "../components/Football";

const Face = ({ l }) => (l.player ? <PlayerAvatar player={l.player} size={28} /> : <Crest team={l.team} size={28} />);

function Card({ c, onDelete }) {
  const done = c.status !== "upcoming";
  const live = c.status === "live";
  const r = c.result;
  return (
    <article className="cb-card card" data-testid={`combo-card-${c.id}`}>
      <header className="cb-card-h">
        <span className="cb-faces">{c.lines.slice(0, 4).map((l) => <span key={l.fkey}><Face l={l} /></span>)}</span>
        <span className="cb-card-t"><b>{c.label}</b><small>{lineWhen(c.kickoff)}</small></span>
        {!done ? <span className="cb-pill">Waiting</span>
          : live ? <span className="cb-pill cb-pill--live" data-testid={`combo-live-${c.id}`}><span className="k-livedot" aria-hidden="true" />{r.reached} of {r.of} so far</span>
          : c.status === "waiting" ? <span className="cb-pill">Counting up</span>
          : <span className={"cb-pill " + (r.all ? "cb-pill--yes" : "cb-pill--mid")}>{r.all ? `Reached all ${r.of}` : `Reached ${r.reached} of ${r.of}`}</span>}
      </header>
      {!done ? (
        <div className="cb-card-now">
          <div><small className="k-sec">Now</small><b className="cb-mid">{c.now ? pct(c.now.combined) : "–"}</b></div>
          <div className="cb-card-r"><small>When saved: {pct(c.combined)}</small><small>{c.now ? (c.now.state === "pre" ? "Lineups not out yet" : "Lineups are out") : "A line left the feed"}</small></div>
        </div>
      ) : (
        <ul className="cb-res">{c.lines.map((l) => {
          // reached === null means we do not know yet: a dash, never a cross (docs/03 section 4.6)
          const mark = l.reached === true ? "y" : l.reached === false ? "n" : "u";
          const says = l.reached === true ? "Happened" : l.reached === false ? "Did not happen" : "Not known yet";
          const note = l.played === false ? "Did not play"
            : l.actual != null ? `Had ${l.actual}`
            : l.current != null && l.needed != null ? `${l.current} of ${l.needed} so far`
            : live ? "Counting" : "";
          return (
            <li key={l.fkey}>
              <span className={"cb-tick " + mark} aria-label={says}>
                {l.reached === true ? <Icon name="check" size={12} /> : l.reached === false ? <Icon name="x" size={12} /> : "–"}
              </span>
              <span className="cb-res-t">{l.player?.name || l.team?.name} · {l.market}</span>
              <small className="muted">{note}</small>
            </li>
          );
        })}
          <li className="muted small">{live ? "Still being played. " : ""}Saved at {pct(c.combined)}</li>
        </ul>
      )}
      <footer className="cb-card-f">
        {c.match_id && <Link to={`/match/${c.match_id}`} className="btn btn--secondary btn--sm" data-testid={`combo-open-${c.id}`}>Open match</Link>}
        <button type="button" className="btn btn--ghost btn--sm" onClick={() => onDelete(c.id)} data-testid={`combo-delete-${c.id}`}><Icon name="trash" size={16} />Delete</button>
      </footer>
    </article>
  );
}

function Summary({ done }) {
  const settled = done.filter((c) => c.status === "settled");   // never a match still being played
  if (!settled.length) return null;
  const allHit = settled.filter((c) => c.result.all).length;
  const lines = settled.reduce((n, c) => n + c.result.of, 0);
  const hit = settled.reduce((n, c) => n + c.result.reached, 0);
  const expected = settled.reduce((n, c) => n + (c.combined || 0), 0);
  return (
    <section className="cb-sum" data-testid="combo-summary">
      <h2 className="h3">How our combined chances did</h2>
      <p className="small muted">Your {settled.length} finished combo{settled.length === 1 ? "" : "s"}. We work this out here from what you saved.</p>
      <div className="cb-sum-row"><div><b className="cb-mid">{allHit} of {settled.length}</b><small>combos reached every line</small></div><div className="cb-sum-r"><b>{hit} of {lines}</b><small>single lines reached</small></div></div>
      <p className="small muted">From our chances at the time of saving we expected about {expected.toFixed(1)} combo{expected.toFixed(1) === "1.0" ? "" : "s"}.{settled.length < 20 ? ` ${settled.length === 1 ? "One combo is" : `${settled.length} combos are`} a small sample.` : ""}</p>
    </section>
  );
}

// Signed out: show what the feature does with real lines, rather than only asking for an account.
function SignedOut() {
  const q = useApi("/insights", { limit: 3 });
  const rows = (q.data || []).slice(0, 3);
  return (
    <div data-testid="combos-signed-out">
      <p className="v2-say">
        Add lines from any card to build a combo, and we work out the combined chance.
        Keeping one for later needs an account.
      </p>
      {q.loading && !q.data ? <Skeleton shape="card" count={3} />
        : rows.length ? <div className="fgrid">{rows.map((f) => <ForecastCard key={f.id} f={f} testid={`combos-sample-${f.id}`} />)}</div>
        : null}
      <p className="v2-more"><Link className="btn btn--secondary" to="/sign-up">Create a free account</Link> <Link className="k-link" to="/insights">See all lines</Link></p>
    </div>
  );
}

export default function Combos() {
  useTitle("My combos");
  const { user } = useAuth();
  const { combo, count, setOpen } = useCombo();
  const q = useApi(user ? "/me/combos" : null);
  const [tab, setTab] = useState("up");
  const [gone, setGone] = useState([]);
  const items = (q.data?.items || []).filter((c) => !gone.includes(c.id));
  const up = items.filter((c) => c.status === "upcoming");
  const nowOn = items.filter((c) => c.status === "live");
  const done = items.filter((c) => c.status === "waiting" || c.status === "settled");
  const shown = tab === "up" ? up : tab === "live" ? nowOn : done;
  const remove = async (id) => { try { await del(`/me/combos/${id}`); setGone((g) => [...g, id]); } catch { q.reload(); } };
  return (
    <section data-testid="combos-page">
      <header className="cb-page-h"><h1>My combos</h1>{q.data && <small className="muted">{items.length} saved{q.data.limit >= 0 ? ` · room for ${q.data.limit}` : ""}</small>}</header>
      {count > 0 && (
        <button type="button" className="cb-open card" onClick={() => setOpen(true)} data-testid="combos-open-combo">
          <span><b>Your open combo</b><small>{count} line{count === 1 ? "" : "s"}{combo?.label ? ` · ${combo.label}` : ""}</small></span><span className="k-link">Review</span>
        </button>
      )}
      {/* CRITIQUE section 1: signed out, this page was a sign-up wall and nothing else, which made
          one of six primary destinations a dead end for most first-time readers. It was also not
          quite true: a combo is built locally, so a signed-out reader can use the feature now and
          only needs an account to KEEP one. So the page shows the feature working -- real lines
          from today, with the same add button -- and asks for the account second. */}
      {!user ? <SignedOut />
        : q.loading && !q.data ? <Skeleton shape="card" count={2} />
        : q.error ? <ErrorState message={q.error.message} onRetry={q.reload} />
        : !items.length ? <EmptyState icon="layers" title="No saved combos yet" testid="combos-empty">Open any match and tap + on the lines you like. <Link to="/">Find a match</Link></EmptyState>
        : (
          <>
            <Segmented
              options={[{ id: "up", label: `Coming up · ${up.length}` },
                        ...(nowOn.length ? [{ id: "live", label: `In play · ${nowOn.length}` }] : []),
                        { id: "done", label: `Finished · ${done.length}` }]}
              value={tab} onChange={setTab} label="Show" testid="combos-tabs" />
            {tab === "done" && <Summary done={done} />}
            <div className="cb-list">{shown.map((c) => <Card key={c.id} c={c} onDelete={remove} />)}
              {!shown.length && <p className="muted" data-testid="combos-none">{tab === "up" ? "Nothing coming up." : tab === "live" ? "No match under way." : "Nothing finished yet."}</p>}</div>
          </>
        )}
    </section>
  );
}
