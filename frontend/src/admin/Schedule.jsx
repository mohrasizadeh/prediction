// The posting queue (docs/64): what is going out, when, and what happened.
//
// One screen and one obvious action. The ad builder renders and queues a batch as DRAFTS; nothing
// leaves the building until someone approves it here. The three things an owner needs at a glance
// are whether the plumbing is connected, what is going out today, and what failed -- so those are
// the only three things on it.
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { del, post, put } from "../lib/api";
import { useApi } from "../lib/useApi";
import { sayError } from "../lib/errors";
import { Confirm, useToast } from "../components/Ui";
import { Empty } from "../components/States";
import Icon from "../components/Icon";
import { Card, Chip, DataState, PageHead } from "./parts";

const TONE = { draft: "muted", approved: "ok", sent: "info", posted: "ok", failed: "err", cancelled: "muted" };
// What each state means in the owner's terms, not the database's. "sent" is the one that needs
// saying out loud: it means handed over, and the tool may still be retrying.
const MEANS = {
  draft: "Waiting for you",
  approved: "Will go out at its time",
  sent: "Handed to your automation tool",
  posted: "Live",
  failed: "Did not go out",
  cancelled: "Cancelled",
};
const dayISO = (d) => new Date(d).toISOString().slice(0, 10);
const shift = (iso, n) => { const d = new Date(`${iso}T00:00:00`); d.setDate(d.getDate() + n); return dayISO(d); };
const clock = (s) => new Date(s).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", hour12: false });

/** The one thing to fix, if anything is unfixed. Shown only when it applies, because a permanent
 *  banner is wallpaper -- and it says the exact next step rather than "check your settings". */
function Setup({ o }) {
  if (!o) return null;
  if (!o.subscribed) {
    return (
      <Card title="Nothing is listening yet" className="a-card--warn" testid="sched-setup">
        <p>
          Approved posts are handed to a webhook. Add an endpoint subscribed to <code>post.due</code> —
          paste the catch URL from your Zap — and send it a test before you approve anything real.
        </p>
        <Link className="btn btn--primary btn--sm" to="/admin/integrations" data-testid="sched-go-int">Set up the webhook</Link>
      </Card>
    );
  }
  if (!o.enabled) {
    return (
      <Card title="Posting is switched off" className="a-card--warn" testid="sched-setup">
        <p>The queue fills and you can approve, but nothing is handed over. Turn on <b>Publish scheduled posts</b> once your webhook has been tested.</p>
        <Link className="btn btn--primary btn--sm" to="/admin/settings?q=social.enabled" data-testid="sched-go-set">Turn it on</Link>
      </Card>
    );
  }
  return null;
}

function Row({ p, onApprove, onUnapprove, onTime, onDrop, busy }) {
  const [time, setTime] = useState(clock(p.scheduled_at));
  const img = (p.media || [])[0];
  const editable = p.status === "draft" || p.status === "failed" || p.status === "approved";
  return (
    <li className="sch-row" data-testid={`sched-row-${p._id}`}>
      <span className="sch-time">
        {editable ? (
          <input type="time" value={time} aria-label="Time"
            onChange={(e) => setTime(e.target.value)}
            onBlur={() => time !== clock(p.scheduled_at) && onTime(p, time)} />
        ) : clock(p.scheduled_at)}
      </span>
      {img ? <img className="sch-thumb" src={img} alt="" loading="lazy" /> : <span className="sch-thumb sch-thumb--none" />}
      <span className="sch-body">
        <span className="sch-cap">{p.caption || <i>No caption</i>}</span>
        <span className="sch-meta">
          <Chip tone={TONE[p.status]} testid={`sched-status-${p._id}`}>{MEANS[p.status] || p.status}</Chip>
          {p.error && <span className="sch-err">{p.error}</span>}
          {p.permalink && <a href={p.permalink} target="_blank" rel="noreferrer">See the post</a>}
        </span>
      </span>
      <span className="sch-acts">
        {p.status === "draft" || p.status === "failed" ? (
          <button className="btn btn--primary btn--sm" disabled={busy} onClick={() => onApprove(p)} data-testid={`sched-approve-${p._id}`}>Approve</button>
        ) : p.status === "approved" ? (
          <button className="btn btn--sm" disabled={busy} onClick={() => onUnapprove(p)} data-testid={`sched-hold-${p._id}`}>Hold</button>
        ) : null}
        {p.status !== "posted" && (
          <button className="icon-btn" title="Remove" aria-label="Remove" disabled={busy}
            onClick={() => onDrop(p)} data-testid={`sched-drop-${p._id}`}><Icon name="trash" size={16} /></button>
        )}
      </span>
    </li>
  );
}

export default function Schedule() {
  const toast = useToast();
  const [day, setDay] = useState(() => dayISO(Date.now()));
  const [busy, setBusy] = useState(false);
  const [drop, setDrop] = useState(null);
  const tz = new Date().getTimezoneOffset() * -1;
  const q = useApi("/admin/social", { day, tz });
  const posts = useMemo(() => q.data?.posts || [], [q.data]);
  const o = q.data?.overview;
  const drafts = posts.filter((p) => p.status === "draft");

  const run = async (fn, ok) => {
    setBusy(true);
    try { await fn(); q.reload(); if (ok) toast(ok); }
    catch (e) { toast(sayError(e), "err"); }
    finally { setBusy(false); }
  };
  const approve = (p) => run(() => post(`/admin/social/${p._id}/approve`), "Approved");
  const unapprove = (p) => run(() => post(`/admin/social/${p._id}/unapprove`), "Back to a draft");
  const setTime = (p, t) => run(() => put(`/admin/social/${p._id}`, { scheduled_at: `${day}T${t}:00` }), "Time changed");
  // One call per post rather than one endpoint for all of them: approving twenty is rare enough
  // that it does not need its own route, and this way a single bad one does not block the rest.
  const approveAll = () => run(async () => {
    const r = await Promise.allSettled(drafts.map((p) => post(`/admin/social/${p._id}/approve`)));
    const bad = r.filter((x) => x.status === "rejected").length;
    if (bad) throw new Error(`${r.length - bad} approved, ${bad} could not be.`);
  }, `${drafts.length} approved`);

  return (
    <section className="sch" data-testid="schedule-page">
      <PageHead title="Schedule" testid="sched-head"
        lead="What is going out, when, and what happened. Posts arrive here as drafts from the ad builder; nothing is handed over until you approve it."
        actions={<Link className="btn btn--sm" to="/admin/ads" data-testid="sched-to-ads">Ad builder</Link>} />

      <Setup o={o} />

      {o && (
        <div className="sch-counts" data-testid="sched-counts">
          <span><b>{o.draft}</b> waiting for you</span>
          <span><b>{o.approved}</b> approved</span>
          <span><b>{o.posted}</b> live</span>
          {o.failed > 0 && <span className="sch-bad"><b>{o.failed}</b> did not go out</span>}
          {o.overdue > 0 && <span className="sch-bad"><b>{o.overdue}</b> overdue</span>}
        </div>
      )}

      <div className="sch-days" data-testid="sched-days">
        <button className="btn btn--sm" onClick={() => setDay(shift(day, -1))} aria-label="Previous day">‹</button>
        <input type="date" value={day} onChange={(e) => e.target.value && setDay(e.target.value)} aria-label="Day" data-testid="sched-day" />
        <button className="btn btn--sm" onClick={() => setDay(shift(day, 1))} aria-label="Next day">›</button>
        <button className="btn btn--sm" onClick={() => setDay(dayISO(Date.now()))}>Today</button>
        <button className="btn btn--sm" onClick={() => setDay(shift(dayISO(Date.now()), 1))}>Tomorrow</button>
      </div>

      <DataState q={q} empty="Nothing scheduled for this day.">
        {posts.length ? (
          <>
            <ul className="sch-list">
              {posts.map((p) => (
                <Row key={p._id} p={p} busy={busy} onApprove={approve} onUnapprove={unapprove}
                  onTime={setTime} onDrop={setDrop} />
              ))}
            </ul>
            {drafts.length > 0 && (
              <div className="sch-bar" data-testid="sched-bar">
                <span>{drafts.length} waiting for you</span>
                <button className="btn btn--primary" disabled={busy} onClick={approveAll} data-testid="sched-approve-all">
                  Approve all {drafts.length}
                </button>
              </div>
            )}
          </>
        ) : (
          <Empty icon="calendar" testid="sched-empty">
            Nothing scheduled for this day. Open the{" "}
            <Link to="/admin/ads">ad builder</Link>, check tomorrow&apos;s batch and press Schedule.
          </Empty>
        )}
      </DataState>

      <Confirm open={!!drop} title="Remove this post?"
        body="It will not go out. The image stays in the media library."
        confirmLabel="Remove" danger onClose={() => setDrop(null)}
        onConfirm={() => { const p = drop; setDrop(null); run(() => del(`/admin/social/${p._id}`), "Removed"); }} />
    </section>
  );
}
