// Content (docs/10 §3.13): Markdown pages with a preview. Rendered by react-markdown without raw HTML (docs/15).
import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import { get, put } from "../lib/api";
import { useApi } from "../lib/useApi";
import { Field, FormError, Tabs, useToast } from "../components/Ui";
import { ErrorBox, Loading } from "../components/States";
import Icon from "../components/Icon";
import { PageHead, when } from "./parts";

const STARTERS = ["terms", "privacy", "about", "faq", "learn"];

function Editor({ slug, onSaved }) {
  const toast = useToast();
  const [f, setF] = useState(null);
  const [err, setErr] = useState(null);
  const [view, setView] = useState("write");
  useEffect(() => {
    setF(null); setErr(null);
    get(`/public/pages/${slug}`).then((p) => setF({ title: p.title || "", body_md: p.body_md || "" })).catch(() => setF({ title: slug[0].toUpperCase() + slug.slice(1), body_md: "" }));
  }, [slug]);
  if (!f) return <Loading />;
  const save = async (e) => {
    e.preventDefault(); setErr(null);
    try { await put(`/admin/content/${slug}`, f); toast("Page saved"); onSaved(); } catch (x) { setErr(x); }
  };
  return (
    <form className="a-card a-form" onSubmit={save} data-testid="content-editor">
      <Field label="Title" value={f.title} maxLength={120} required onChange={(e) => setF({ ...f, title: e.target.value })} testid="content-title" />
      <Tabs tabs={[{ id: "write", label: "Write" }, { id: "preview", label: "Preview" }]} value={view} onChange={setView} testid="content-view" />
      {view === "write" ? (
        <textarea className="a-md" rows={18} value={f.body_md} onChange={(e) => setF({ ...f, body_md: e.target.value })} aria-label="Page text (Markdown)" data-testid="content-body" />
      ) : <article className="prose a-md-preview" data-testid="content-preview"><h1>{f.title}</h1><ReactMarkdown>{f.body_md}</ReactMarkdown></article>}
      <FormError error={err} />
      <div className="a-btns"><button className="btn btn--primary" data-testid="content-save">Save page</button><a className="btn btn--ghost" href={`/legal/${slug}`} target="_blank" rel="noopener noreferrer"><Icon name="external" size={16} />Open</a></div>
    </form>
  );
}

export default function Content() {
  const q = useApi("/admin/content");
  const [slug, setSlug] = useState("terms");
  const [custom, setCustom] = useState("");
  const pages = q.data?.pages || [];
  const slugs = [...new Set([...STARTERS, ...pages.map((p) => p.slug)])];
  return (
    <div className="a-page" data-testid="admin-content">
      <PageHead title="Pages" lead="Terms, Privacy, About, FAQ and Learn. Saving scans for words the rules forbid." />
      {q.loading && !q.data ? <Loading /> : q.error ? <ErrorBox error={q.error} onRetry={q.reload} /> : (
        <div className="a-split a-split--list">
          <nav className="a-card a-page-list" aria-label="Pages">
            {slugs.map((s) => { const p = pages.find((x) => x.slug === s); return (
              <button key={s} className={"a-page-item" + (slug === s ? " is-on" : "")} onClick={() => setSlug(s)} data-testid={`content-page-${s}`}><strong>{p?.title || s}</strong><small>{p ? `Saved ${when(p.updated_at)}` : "Not written yet"}</small></button>
            ); })}
            <form className="a-new-page" onSubmit={(e) => { e.preventDefault(); if (/^[a-z0-9-]{2,40}$/.test(custom)) { setSlug(custom); setCustom(""); } }}>
              <input placeholder="new-page-address" value={custom} onChange={(e) => setCustom(e.target.value.toLowerCase())} aria-label="New page address" data-testid="content-new-slug" />
              <button className="btn btn--secondary btn--sm" data-testid="content-new-add">Add</button>
            </form>
          </nav>
          <Editor slug={slug} onSaved={q.reload} />
        </div>
      )}
    </div>
  );
}
