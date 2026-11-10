// Blog (docs/72): the day's match posts, prepared from our own forecasts, reviewed here, then published.
//
// WHY THE PREVIEW IS AN IFRAME AND NOT A REACT RENDER. The post is real HTML served by the backend
// -- that is the whole point of it, because the app itself cannot be crawled or previewed in a chat
// (docs/71). Re-implementing the page in JSX for this screen would create a second renderer that
// disagrees with the published one, which is exactly the drift docs/61 was about. So the reviewer
// looks at the actual page, through /api/admin/blog/{slug}/preview, which serves a draft with
// no-store and X-Robots-Tag: noindex.
//
// WHAT A REVIEWER MAY CHANGE: the title, the search description and the opening paragraph. Not the
// numbers. If a figure is wrong the fix belongs in the engine and the post should be regenerated --
// an admin editing a percentage in a post would publish a forecast the product never made.
import { useState } from "react";
import { del, post, put } from "../lib/api";
import { useApi } from "../lib/useApi";
import { Confirm, Drawer, Field, FormError, useToast } from "../components/Ui";
import Icon from "../components/Icon";
import { Chip, DataState, PageHead, ResponsiveTable, when } from "./parts";

const today = () => new Date().toISOString().slice(0, 10);

function Review({ slug, onClose, onSaved }) {
  const q = useApi(`/admin/blog/${slug}`);
  const toast = useToast();
  const [f, setF] = useState(null);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  const p = q.data?.post;
  const form = f || (p ? { title: p.title || "", description: p.description || "", intro: p.intro || "" } : null);

  const act = async (fn, msg) => {
    setErr(null); setBusy(true);
    try { await fn(); toast(msg); onSaved(); onClose(); } catch (x) { setErr(x); } finally { setBusy(false); }
  };
  const save = () => act(() => put(`/admin/blog/${slug}`, form), "Saved");
  const publish = () => act(async () => { await put(`/admin/blog/${slug}`, form); await post(`/admin/blog/${slug}/publish`, {}); }, "Published");
  const unpublish = () => act(() => post(`/admin/blog/${slug}/unpublish`, {}), "Back to draft");

  return (
    <Drawer open onClose={onClose} title="Review post" testid="blog-drawer" footer={
      <>
        {p?.status === "published"
          ? <button className="btn btn--secondary" onClick={unpublish} disabled={busy} data-testid="blog-unpublish">Unpublish</button>
          : <button className="btn btn--primary" onClick={publish} disabled={busy || !form?.title?.trim()} data-testid="blog-publish">Publish</button>}
        <button className="btn btn--secondary" onClick={save} disabled={busy || !form} data-testid="blog-save">Save draft</button>
      </>}>
      <DataState q={q} empty="That post is gone.">{() => (
        <div className="a-stack">
          <p className="muted">
            {p.home?.name} v {p.away?.name} · {p.kickoff ? when(p.kickoff) : p.day}
            {p.status === "published" && <> · <a href={q.data.url} target="_blank" rel="noreferrer">{q.data.url}</a></>}
          </p>
          {/* The two counts a reviewer actually needs: how many forecasts the post shows, and which
              tiers it could not fill. A missing Strong is the ordinary case, not a fault. */}
          <p className="muted">
            {(p.items || []).length} forecasts
            {(p.missing || []).length > 0 && <> · no {p.missing.join(" or ")} forecast for this match</>}
          </p>
          <Field label={`Title (${(form.title || "").length}/70 — Google truncates past this)`} value={form.title}
                 maxLength={200} onChange={(e) => setF({ ...form, title: e.target.value })} testid="blog-title" />
          <Field label={`Search description (${(form.description || "").length}/155)`} as="textarea" rows={2} maxLength={400}
                 value={form.description} onChange={(e) => setF({ ...form, description: e.target.value })} testid="blog-desc" />
          <Field label="Opening paragraph" as="textarea" rows={3} maxLength={2000} value={form.intro}
                 onChange={(e) => setF({ ...form, intro: e.target.value })} testid="blog-intro" />
          <p className="muted">The forecasts, their reasons and the percentages are read off the engine and cannot be edited here. If one is wrong, fix it in the engine and prepare the posts again.</p>
          <FormError error={err} />
          <h4>Preview</h4>
          {/* Sandboxed: the page is ours, but it is assembled from provider names, so it is framed
              with no script and no same-origin access all the same. */}
          <iframe title="Post preview" src={`/api/admin/blog/${slug}/preview`} sandbox=""
                  style={{ width: "100%", height: "70vh", border: "1px solid var(--border)", borderRadius: 12, background: "var(--bg)" }}
                  data-testid="blog-preview" />
        </div>
      )}</DataState>
    </Drawer>
  );
}

export default function Blog() {
  const q = useApi("/admin/blog");
  const toast = useToast();
  const [open, setOpen] = useState(null);
  const [rm, setRm] = useState(null);
  const [day, setDay] = useState(today());
  const [busy, setBusy] = useState(false);

  const generate = async () => {
    setBusy(true);
    try {
      const r = await post("/admin/blog/generate", { day });
      const c = r.counts || {};
      toast(c.created || c.replaced
        ? `${c.created || 0} new, ${c.replaced || 0} refreshed${c.kept ? `, ${c.kept} published posts left alone` : ""}`
        : "Nothing to prepare for that day");
      q.reload();
    } catch (x) { toast(x?.message || "Could not prepare posts", "err"); } finally { setBusy(false); }
  };

  const cols = [
    { key: "title", label: "Post", primary: true },
    { key: "status", label: "State", render: (r) => (r.status === "published" ? <Chip tone="up">Published</Chip> : <Chip>Draft</Chip>) },
    { key: "kickoff", label: "Kick-off", render: (r) => (r.kickoff ? when(r.kickoff) : r.day || "—") },
    { key: "published_at", label: "Published", render: (r) => (r.published_at ? when(r.published_at) : "—") },
    { key: "x", label: "", render: (r) => <span onClick={(e) => e.stopPropagation()} role="presentation"><button className="a-icon-btn a-icon-btn--sm" aria-label="Delete" onClick={() => setRm(r)} data-testid={`blog-delete-${r.slug}`}><Icon name="trash" size={16} /></button></span> },
  ];

  return (
    <div className="a-page" data-testid="admin-blog">
      <PageHead title="Blog" lead="One post per match, written from our own forecasts. Nothing goes out until you publish it."
                actions={
                  <>
                    <input type="date" value={day} onChange={(e) => setDay(e.target.value)} aria-label="Day to prepare" data-testid="blog-day" />
                    <button className="btn btn--primary btn--sm" onClick={generate} disabled={busy} data-testid="blog-generate">
                      <Icon name="plus" size={16} />{busy ? "Preparing…" : "Prepare drafts"}
                    </button>
                  </>} />
      <DataState q={q} empty="No posts yet. Pick a day and press Prepare drafts.">{(d) => (
        <>
          {!d.enabled && <p className="muted" data-testid="blog-off">The blog is switched off in Settings, so visitors cannot reach any post. Drafts and published posts are kept.</p>}
          <ResponsiveTable columns={cols} rows={d.posts} onRow={(r) => setOpen(r.slug)} testid="blog-table" />
        </>
      )}</DataState>
      {open && <Review slug={open} onClose={() => setOpen(null)} onSaved={q.reload} />}
      <Confirm open={!!rm} danger title="Delete this post?" confirmLabel="Delete" onClose={() => setRm(null)} testid="blog-delete-confirm"
               onConfirm={async () => { await del(`/admin/blog/${rm.slug}`); toast("Post deleted"); setRm(null); q.reload(); }}>
        {rm?.status === "published"
          ? "This post is published. Deleting it means anyone holding the link gets a 404 — unpublish instead if you only want it hidden."
          : "The draft is removed. Preparing drafts again will rebuild it from the current forecasts."}
      </Confirm>
    </div>
  );
}
