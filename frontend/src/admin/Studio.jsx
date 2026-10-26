// Site Studio (docs/16 §2): edit a draft section by section, live preview (Desktop/Phone, Dark/Light), preview link,
// publish with conflict check, versions and rollback. Server problems are shown beside their fields.
import { useEffect, useMemo, useState } from "react";
import { post, put } from "../lib/api";
import { useApi } from "../lib/useApi";
import { sayError } from "../lib/errors";
import { Confirm, Drawer, Switch, Tabs, useToast } from "../components/Ui";
import { ErrorBox, Loading, Empty } from "../components/States";
import Icon from "../components/Icon";
import { Chip, PageHead, when } from "./parts";
import { BrandLogo } from "../components/Media";

const LABEL = { brand: "Brand", theme: "Look", buttons: "Buttons", nav: "Menus", footer: "Footer", seo: "SEO", cookies: "Cookie banner", home: "Home page", custom_css: "Custom CSS" };
const ENUMS = { default_mode: ["system", "light", "dark"], radius: ["sharp", "default", "round"], density: ["comfortable", "compact"], shadows: ["none", "soft", "strong"], motion: ["full", "reduced"],
  shadow: ["none", "soft"], hover: ["lift", "darken", "none"], desktop_layout: ["rail", "top"], audience: ["all", "signed_out", "signed_in", "free", "paid"] };
const isHex = (v) => typeof v === "string" && /^#[0-9a-fA-F]{6}$/.test(v);
const setIn = (o, path, v) => {
  const [k, ...rest] = path;
  const c = Array.isArray(o) ? [...o] : { ...o };
  c[k] = rest.length ? setIn(o[k], rest, v) : v;
  return c;
};

const IMAGE_KEYS = ["logo_light", "logo_dark", "favicon", "og_image"];

// Upload goes to POST /admin/site/assets (PNG, JPEG, WebP, ICO; checked on the server); the field keeps the returned address.
function ImageInput({ id, value, onChange }) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const pick = async (e) => {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (!f) return;
    setBusy(true);
    try {
      const b64 = await new Promise((ok, no) => { const r = new FileReader(); r.onload = () => ok(String(r.result).split(",")[1]); r.onerror = no; r.readAsDataURL(f); });
      const r = await post("/admin/site/assets", { name: f.name.slice(0, 80), data_b64: b64 });
      onChange(r.url);
      toast("Image uploaded. Save to draft to keep it.");
    } catch (x) { toast(sayError(x), "err"); } finally { setBusy(false); }
  };
  return (
    <div className="a-img-input">
      <span className="a-img-thumb"><BrandLogo brand={{ logo_dark: value }} mode="dark" /></span>
      <input id={id} value={value ?? ""} placeholder="No image" onChange={(e) => onChange(e.target.value)} data-testid={id} />
      <label className="btn btn--secondary btn--sm" data-testid={`${id}-upload`}>{busy ? "Uploading…" : "Upload"}<input type="file" accept="image/png,image/jpeg,image/webp,image/x-icon" hidden onChange={pick} disabled={busy} /></label>
      {value && <button type="button" className="btn btn--ghost btn--sm" onClick={() => onChange("")} data-testid={`${id}-clear`}>Remove</button>}
    </div>
  );
}

function Leaf({ path, value, onChange, meta, problems }) {
  const key = path[path.length - 1];
  const id = "f-" + path.join("-");
  const msg = problems[path.join(".")];
  const fonts = (meta.fonts || []).map((f) => f.id);
  const opts = key === "font_body" || key === "font_heading" ? fonts : key === "icon" ? meta.icons : key === "style" ? meta.button_styles : ENUMS[key];
  let input;
  if (typeof value === "boolean") input = <Switch label={value ? "On" : "Off"} checked={value} onChange={onChange} testid={id} />;
  else if (isHex(value)) input = <span className="a-color"><input type="color" value={value} onChange={(e) => onChange(e.target.value.toUpperCase())} aria-label={key} data-testid={id} /><input value={value} onChange={(e) => onChange(e.target.value)} aria-label={`${key} hex`} maxLength={7} /></span>;
  else if (opts) input = <select id={id} value={value} onChange={(e) => onChange(e.target.value)} data-testid={id}>{opts.includes(value) ? null : <option>{value}</option>}{opts.map((o) => <option key={o}>{o}</option>)}</select>;
  else if (typeof value === "number") input = <input id={id} type="number" value={value} onChange={(e) => onChange(e.target.value === "" ? "" : Number(e.target.value))} data-testid={id} />;
  else if (key === "css") input = <textarea id={id} rows={12} spellCheck={false} value={value || ""} onChange={(e) => onChange(e.target.value)} data-testid={id} />;
  else if (IMAGE_KEYS.includes(key)) input = <ImageInput id={id} value={value} onChange={onChange} />;
  else input = <input id={id} value={value ?? ""} onChange={(e) => onChange(e.target.value)} data-testid={id} />;
  return <div className={"a-leaf" + (msg ? " has-err" : "")}><label htmlFor={id}>{key.replace(/_/g, " ")}</label>{input}{msg && <small className="field-err" role="alert">{msg}</small>}</div>;
}

function Node({ path, value, onChange, meta, problems }) {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return (
      <fieldset className={"a-node" + (path.length ? "" : " a-node--root")}>
        {path.length > 0 && <legend>{String(path[path.length - 1]).replace(/_/g, " ")}</legend>}
        <div className={Object.values(value).every(isHex) ? "a-color-grid" : "a-node-body"}>
          {Object.entries(value).map(([k, v]) => <Node key={k} path={[...path, k]} value={v} meta={meta} problems={problems} onChange={(nv) => onChange(setIn(value, [k], nv))} />)}
        </div>
      </fieldset>
    );
  }
  if (Array.isArray(value)) {
    const simple = value.every((x) => typeof x !== "object");
    return (
      <fieldset className="a-node a-node--list">
        <legend>{String(path[path.length - 1]).replace(/_/g, " ")} ({value.length})</legend>
        {simple ? <textarea rows={3} value={value.join("\n")} onChange={(e) => onChange(e.target.value.split("\n").filter(Boolean))} aria-label={String(path[path.length - 1])} />
          : value.map((item, i) => (
            <div key={i} className="a-list-item">
              <div className="a-list-tools">
                <span>#{i + 1}</span>
                <button type="button" className="a-icon-btn a-icon-btn--sm" disabled={i === 0} onClick={() => { const c = [...value]; [c[i - 1], c[i]] = [c[i], c[i - 1]]; onChange(c); }} aria-label="Move up"><Icon name="chevron-left" size={16} className="rot90" /></button>
                <button type="button" className="a-icon-btn a-icon-btn--sm" onClick={() => onChange(value.filter((_, j) => j !== i))} aria-label="Remove"><Icon name="trash" size={16} /></button>
              </div>
              <Node path={[...path, i]} value={item} meta={meta} problems={problems} onChange={(nv) => onChange(setIn(value, [i], nv))} />
            </div>
          ))}
        {!simple && value.length > 0 && <button type="button" className="btn btn--ghost btn--sm" onClick={() => onChange([...value, JSON.parse(JSON.stringify(value[value.length - 1]))])}><Icon name="plus" size={16} />Add a copy of the last one</button>}
      </fieldset>
    );
  }
  return <Leaf path={path} value={value} onChange={onChange} meta={meta} problems={problems} />;
}

function Preview({ draft, mode, device }) {
  const c = draft.theme?.colors?.[mode] || {};
  const vars = Object.fromEntries(Object.entries(c).map(([k, v]) => ["--p-" + k.replace(/_/g, "-"), v]));
  const items = (draft.nav?.items || []).filter((i) => i.enabled);
  const tabs = (draft.nav?.mobile_tabs || []).map((id) => items.find((i) => i.id === id)).filter(Boolean);
  const r = { sharp: 2, default: 12, round: 20 }[draft.theme?.radius] ?? 12;
  return (
    <div className={"a-prev a-prev--" + device} style={{ ...vars, "--p-r": r + "px" }} data-testid="studio-preview" aria-label="Live preview">
      <div className="p-head"><b>{draft.brand?.name}</b><span className="p-beta">Beta</span>{device === "desktop" && <span className="p-nav">{items.slice(0, 5).map((i) => <span key={i.id}>{i.label}</span>)}</span>}</div>
      <div className="p-body">
        <p className="p-tag">{draft.brand?.tagline}</p>
        <div className="p-card"><small>Insight</small><strong>2+ shots on target</strong><span className="p-tier">Strong ●●● <em>74% (66 to 81)</em></span><span className="p-text2">Reached in 8 of the last 10.</span></div>
        <div className="p-btns"><span className="p-btn p-btn--primary">Primary</span><span className="p-btn p-btn--secondary">Secondary</span><span className="p-btn p-btn--danger">Danger</span></div>
        <p className="p-disc">Statistical analysis for information and entertainment. Not betting advice.</p>
      </div>
      {device === "phone" && <div className="p-bar">{tabs.map((t) => <span key={t.id}><Icon name={t.icon} size={18} />{t.label}</span>)}{draft.nav?.mobile_more !== false && <span><Icon name="grid" size={18} />More</span>}</div>}
    </div>
  );
}

function Versions({ open, onClose, onDone }) {
  const q = useApi(open ? "/admin/site/versions" : null);
  const toast = useToast();
  const [v, setV] = useState(null);
  return (
    <Drawer open={open} onClose={onClose} title="Versions" testid="studio-versions">
      {q.loading ? <Loading /> : q.error ? <ErrorBox error={q.error} onRetry={q.reload} /> : !q.data?.versions?.length ? <Empty>Nothing published yet.</Empty> : (
        <ul className="a-rows">{q.data.versions.map((x) => (
          <li key={x.v} className="a-card a-ver"><div><strong>Version {x.v}</strong>{x.v === q.data.live_v && <Chip tone="up">Live</Chip>}<small>{when(x.at)} · {x.by}{x.note ? ` · ${x.note}` : ""}</small></div>
            {x.v !== q.data.live_v && <button className="btn btn--secondary btn--sm" onClick={() => setV(x.v)} data-testid={`rollback-${x.v}`}>Roll back</button>}</li>
        ))}</ul>
      )}
      <Confirm open={!!v} title={`Publish version ${v} again?`} body="It becomes the newest version. History is kept." confirmLabel="Roll back" onClose={() => setV(null)}
               onConfirm={async () => { await post(`/admin/site/rollback/${v}`); setV(null); toast("Rolled back"); q.reload(); onDone(); }} testid="rollback-confirm" />
    </Drawer>
  );
}

export default function Studio() {
  const q = useApi("/admin/site/draft");
  const toast = useToast();
  const [section, setSection] = useState("brand");
  const [local, setLocal] = useState(null);
  const [problems, setProblems] = useState({});
  const [mode, setMode] = useState("dark");
  const [device, setDevice] = useState("phone");
  const [pub, setPub] = useState(null);
  const [vers, setVers] = useState(false);
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (q.data) setLocal(q.data.draft); }, [q.data]);
  const sections = useMemo(() => (q.data?.meta?.sections || []).filter((s) => s !== "custom_css" || q.data.can_edit_css), [q.data]);
  if (q.loading && !q.data) return <Loading rows={6} />;
  if (q.error) return <ErrorBox error={q.error} onRetry={q.reload} />;
  if (!local) return <Loading />;
  const d = q.data;
  const changed = JSON.stringify(local[section]) !== JSON.stringify(d.draft[section]);
  const fail = (x) => {
    const pr = {};
    (x.problems || []).forEach((p) => { pr[p.path.replace(/^[a-z_]+\./, "")] = p.message; });
    setProblems(pr);
    toast(x.problems?.length ? "Some fields need fixing." : sayError(x), "err");
  };
  const save = async () => {
    setBusy(true); setProblems({});
    try { await put(`/admin/site/draft/${section}`, { data: local[section] }); toast(`${LABEL[section]} saved to the draft`); q.reload(); } catch (x) { fail(x); } finally { setBusy(false); }
  };
  const act = async (fn, msg) => { try { await fn(); toast(msg); q.reload(); } catch (x) { fail(x); } };
  const previewLink = async () => { try { const r = await post("/admin/site/preview-token"); window.open(new URL(r.url).pathname + new URL(r.url).search, "_blank", "noopener"); } catch (x) { fail(x); } };
  const publish = async (note, force = false) => {
    try { const r = await post("/admin/site/publish", { note, force }); setPub(null); toast(`Published version ${r?.v ?? ""}`); q.reload(); }
    catch (x) { if (x.code === "PUBLISH_CONFLICT") setPub({ conflict: true, note }); else { setPub(null); fail(x); } }
  };
  return (
    <div className="a-page" data-testid="admin-studio">
      <PageHead title="Site Studio" lead="Edit a draft. Visitors see nothing until you publish." />
      <div className="a-publishbar" data-testid="studio-publish-bar">
        <span className="a-pub-state">{d.dirty ? <Chip tone="warn">Unsaved draft</Chip> : <Chip tone="up">Live: version {d.live_v}</Chip>}{d.dirty && d.updated_by && <small>by {d.updated_by}, {when(d.updated_at)}</small>}</span>
        <div className="a-btns">
          <button className="btn btn--ghost btn--sm" onClick={() => setVers(true)} data-testid="studio-versions-btn">Versions</button>
          {d.dirty && <button className="btn btn--ghost btn--sm" onClick={() => act(() => post("/admin/site/draft/discard"), "Draft discarded")} data-testid="studio-discard">Discard</button>}
          <button className="btn btn--secondary btn--sm" onClick={previewLink} data-testid="studio-preview-link"><Icon name="external" size={16} />Preview link</button>
          <button className="btn btn--primary btn--sm" disabled={!d.dirty} title={d.dirty ? "" : "Nothing to publish"} onClick={() => setPub({})} data-testid="studio-publish">Publish</button>
        </div>
      </div>
      <Tabs tabs={sections.map((s) => ({ id: s, label: LABEL[s] || s }))} value={section} onChange={(s) => { setSection(s); setProblems({}); }} testid="studio-tabs" />
      <div className="a-editor">
        <div className="a-editor-form">
          {section === "theme" && (
            <div className="a-presets" data-testid="studio-presets"><span>Start from</span>
              {(d.meta.presets || []).map((p) => <button key={p.id} className="a-preset" title={p.description} onClick={() => act(() => post("/admin/site/draft/preset", { key: p.id }), `${p.label} applied`)} data-testid={`preset-${p.id}`}>{p.label}</button>)}
            </div>
          )}
          {section === "footer" && <p className="a-notice"><Icon name="info" size={16} />The disclaimer is always shown and is not edited here.</p>}
          <Node path={[]} value={local[section]} meta={d.meta} problems={problems} onChange={(nv) => setLocal({ ...local, [section]: nv })} />
          <div className="a-sticky-save">
            <button className="btn btn--primary" disabled={!changed || busy} onClick={save} data-testid="studio-save">Save to draft</button>
            <button className="btn btn--ghost" disabled={!changed} onClick={() => { setLocal({ ...local, [section]: d.draft[section] }); setProblems({}); }} data-testid="studio-undo">Undo changes</button>
            <button className="btn btn--ghost" onClick={() => act(() => post(`/admin/site/draft/${section}/reset`, { to: "default" }), "Section back to default")} data-testid="studio-reset">Reset section</button>
          </div>
        </div>
        <div className="a-editor-preview">
          <div className="a-prev-tools">
            <div className="a-seg" role="group" aria-label="Device">{["desktop", "phone"].map((x) => <button key={x} aria-pressed={device === x} onClick={() => setDevice(x)} data-testid={`preview-${x}`}><Icon name={x === "phone" ? "phone" : "monitor"} size={16} />{x === "phone" ? "Phone" : "Desktop"}</button>)}</div>
            <div className="a-seg" role="group" aria-label="Mode">{["dark", "light"].map((x) => <button key={x} aria-pressed={mode === x} onClick={() => setMode(x)} data-testid={`preview-${x}`}><Icon name={x === "dark" ? "moon" : "sun"} size={16} />{x === "dark" ? "Dark" : "Light"}</button>)}</div>
          </div>
          <Preview draft={local} mode={mode} device={device} />
        </div>
      </div>
      <Confirm open={!!pub} title={pub?.conflict ? "Someone published a newer version" : "Publish the draft?"} body={pub?.conflict ? "Review, then override if you are sure." : "It becomes the next version. You can roll back."}
               reason={pub?.conflict ? undefined : "Note (what changed)"} confirmLabel={pub?.conflict ? "Override and publish" : "Publish"} danger={pub?.conflict}
               onClose={() => setPub(null)} onConfirm={(t) => publish(pub?.conflict ? pub.note : t, !!pub?.conflict)} testid="publish-confirm" />
      <Versions open={vers} onClose={() => setVers(false)} onDone={q.reload} />
    </div>
  );
}
