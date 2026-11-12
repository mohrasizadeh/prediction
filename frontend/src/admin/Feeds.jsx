// Admin > Football data > Feeds (docs/43): both football feeds side by side -- what each one is for, whether it is
// working, and what it costs today. The two providers do different jobs, so the first question in any live problem
// is which feed is at fault; before this there was no screen that answered it.
import { Link } from "react-router-dom";
import { useApi } from "../lib/useApi";
import Icon from "../components/Icon";
import { Budget, Card, Chip, DataState, PageHead, num, when } from "./parts";

const TONE = { green: "up", amber: "warn", red: "down", off: "muted" };

function Provider({ p }) {
  const state = p.enabled ? (p.key_saved ? "On" : "No key") : "Off";
  return (
    <Card title={p.name} testid={`feed-${p.id}`}
          actions={<Chip tone={p.key_saved && p.enabled ? TONE[p.tone] : "warn"} testid={`feed-${p.id}-state`}>{state}</Chip>}>
      <ul className="a-checklist" data-testid={`feed-${p.id}-what`}>
        {p.feeds.map((f) => <li key={f} className="is-ok">{f}</li>)}
      </ul>
      <p className="muted small" data-testid={`feed-${p.id}-calls`}>{num(p.used)} of {num(p.cap)} calls today · last ran {p.last_at ? when(p.last_at) : "never"}</p>
      <Budget used={p.used} cap={p.cap} reset={p.reset_at} label={`${p.name} calls used today`} testid={`feed-${p.id}-budget`} />

      {/* A definition list, not stat tiles: these cards sit two to a row, and a tile grid clips its own labels there. */}
      <dl className="a-dl a-dl--tight" data-testid={`feed-${p.id}-numbers`}>
        {/* ONE FEED, so no branch on the provider id. This read `p.id === "pitchapi"`, and the
            payload has carried a single row with id "apifootball" since the move -- so the else
            branch always ran and the card showed "Clubs to review 0 · Fixtures reaching no page 0",
            three numbers the server now hard-codes to zero because nothing is matched by name any
            more. Meanwhile `queued` and `breaker_open`, the two an operator actually needs in a
            live problem, were fetched and thrown away. docs/89. */}
        <div><dt>Waiting to be ingested</dt><dd>{num(p.queued)}</dd></div>
        <div><dt>Breaker</dt><dd>{p.breaker_open ? "Open — no calls are being made" : "Closed — calls are allowed"}</dd></div>
        <div><dt>Being played now</dt><dd>{num(p.live_now)}</dd></div>
      </dl>

      {p.paused_reason && <p className="a-notice a-notice--warn" data-testid="feed-pitch-paused">Paused: {p.paused_reason}</p>}
      {/* `last_result` came from sportapi.status() and left the payload with the provider, so this
          banner could never appear: a failing tick had no surface here at all. `last_at` is what
          the row carries now, and a pull that has not happened for a long time is the signal. */}
      {p.last_at && <p className="a-muted small" data-testid="feed-last-at">Last pull: {when(p.last_at)}</p>}
      <Link to={p.route} className="btn btn--secondary btn--sm self-start" data-testid={`feed-${p.id}-open`}>Open {p.name}</Link>
    </Card>
  );
}

export default function Feeds() {
  const q = useApi("/admin/feeds", undefined, { every: 60000 });
  return (
    <DataState q={q}>{(d) => (
      <div className="a-page" data-testid="admin-feeds">
        <PageHead title="Football data feeds"
          lead="Two providers, two jobs. PitchAPI backfills history and the depth the forecasts are built from; SportAPI does everything live. Keys live under Keys, numbers under Settings."
          actions={<button className="btn btn--ghost btn--sm" onClick={q.reload} data-testid="feeds-refresh"><Icon name="refresh" size={16} />Refresh</button>} />
        <div className="a-grid2">{d.providers.map((p) => <Provider key={p.id} p={p} />)}</div>
        <Card title="Which feed to look at" testid="feeds-help">
          <dl className="a-dl">
            <div><dt>A score, the minute or a match event is wrong or late</dt><dd>SportAPI</dd></div>
            <div><dt>A forecast did not turn green while the match was on</dt><dd>SportAPI — its live statistics and events</dd></div>
            <div><dt>A match or player is missing, or a season has gaps</dt><dd>PitchAPI — Leagues for the season, then Jobs for the queue</dd></div>
            <div><dt>A statistic reads zero for everyone</dt><dd>PitchAPI — the field mapping on its Quality tab</dd></div>
            <div><dt>Forecasts look wrong but the data is there</dt><dd>Engine</dd></div>
          </dl>
        </Card>
      </div>
    )}</DataState>
  );
}
