// Popup Maker (docs/16 §3): list with live state and results, templates, editor with live preview, status, duplicate, delete, stats, A/B.
import { useEffect, useState } from "react";
import { del, get, post, put } from "../lib/api";
import { useApi } from "../lib/useApi";
import { Confirm, Drawer, Field, Switch, Tabs, useToast } from "../components/Ui";
import { Empty, ErrorBox, Loading } from "../components/States";
import { PopupView } from "../components/Popups";
import { Bars, Card, Chip, DataState, PageHead, ResponsiveTable, StatTile } from "./parts";

const pct = (v) => (v == null ? "No data" : `${(v * 100).toFixed(1)}%`);
const TONE = { running: "up", draft: "muted", paused: "warn", scheduled: "info", ended: "muted" };
const KIND = { modal: "Centre popup", slide_in: "Corner slide-in", banner_top: "Top banner", banner_bottom: "Bottom banner" };
const setIn = (o, path, v) => { const [k, ...r] = path; return { ...o, [k]: r.length ? setIn(o[k] || {}, r, v) : v }; };
const lines = (a) => (a || []).join("\n");
const unlines = (s) => s.split("\n").map((x) => x.trim()).filter(Boolean);
const dIn = (v) => (v ? String(v).slice(0, 10) : "");

function Sel({ label, value, onChange, options, testid }) {
  return <Field as="select" label={label} value={value} onChange={(e) => onChange(e.target.value)} testid={testid}>{options.map((o) => <option key={o} value={o}>{o.replace(/_/g, " ")}</option>)}</Field>;
}

function Editor({ id, meta, onClose, onSaved }) {
  const toast = useToast();
  const [d, setD] = useState(null);
  const [tab, setTab] = useState("content");
  const [prob, setProb] = useState({});
  const [warn, setWarn] = useState([]);
  const [err, setErr] = useState(null);
  useEffect(() => { if (id) get(`/admin/popups/${id}`).then(setD).catch(setErr); else setD(null); }, [id]);
  if (!id) return null;
  const s = (path) => (v) => setD((x) => setIn(x, path, v));
  const ev = (path) => (e) => s(path)(e.target.value);
  const P = (k) => prob[k];
  const save = async () => {
    setProb({}); setErr(null);
    const { id: _i, state: _s, stats: _st, created_at: _c, updated_at: _u, created_by: _cb, updated_by: _ub, ...data } = d;
    Object.keys(data).forEach((k) => { if (!(k in meta.blank)) delete data[k]; });
    try { const r = await put(`/admin/popups/${id}`, { data }); setWarn(r.warnings || []); toast("Popup saved"); onSaved(); }
    catch (x) { const m = {}; (x.problems || []).forEach((p) => { m[p.path] = p.message; }); setProb(m); setErr(x.problems?.length ? "Some fields need fixing. Check each tab." : x); }
  };
  const c = d?.content || {};
  const btns = c.buttons || [];
  return (
    <Drawer open onClose={onClose} title={d?.name || "Popup"} testid="popup-editor" wide
            footer={d && <><button className="btn btn--secondary" onClick={onClose}>Close</button><button className="btn btn--primary" onClick={save} data-testid="popup-save">Save</button></>}>
      {!d ? (err ? <ErrorBox error={err} /> : <Loading />) : (
        <div className="a-stack">
          <div className="pop-stage" data-testid="popup-stage"><PopupView p={d} preview onClose={() => {}} onAct={() => {}} /></div>
          {err && <p className="form-error" role="alert" data-testid="popup-editor-error">{typeof err === "string" ? err : err.message}</p>}
          {warn.map((w) => <p key={w.message} className="a-warn" data-testid="popup-warning">{w.message}</p>)}
          <Tabs value={tab} onChange={setTab} testid="popup-tabs" tabs={[{ id: "content", label: "Content" }, { id: "form", label: "Form" }, { id: "look", label: "Look" }, { id: "when", label: "When" }, { id: "who", label: "Who and how often" }]} />
          {tab === "content" && <>
            <Field label="Name (only staff see it)" value={d.name} onChange={ev(["name"])} error={P("name")} maxLength={60} testid="popup-name" />
            <Sel label="Type" value={d.kind} onChange={s(["kind"])} options={meta.kinds} testid="popup-kind" />
            <Field label="Title" value={c.title} onChange={ev(["content", "title"])} error={P("content.title")} maxLength={80} testid="popup-title" />
            <Field as="textarea" label="Text" value={c.body} onChange={ev(["content", "body"])} error={P("content.body") || P("content")} maxLength={400} rows={3} testid="popup-body" hint="Plain text, up to 400 characters." />
            <Field label="Image address (optional)" value={c.image} onChange={ev(["content", "image"])} error={P("content.image")} hint="An uploaded Site Studio image (/api/site/assets/...) or an https address." testid="popup-image" />
            {c.image && <Field label="Describe the image" value={c.image_alt} onChange={ev(["content", "image_alt"])} error={P("content.image_alt")} testid="popup-image-alt" />}
            {btns.map((b, i) => (
              <div key={i} className="a-row-fields" data-testid={`popup-button-${i}`}>
                <Field label={`Button ${i + 1} label`} value={b.label} onChange={(e) => s(["content", "buttons"])(btns.map((x, j) => (j === i ? { ...x, label: e.target.value } : x)))} error={P(`content.buttons[${i}].label`)} maxLength={24} />
                <Sel label="Does" value={b.action} onChange={(v) => s(["content", "buttons"])(btns.map((x, j) => (j === i ? { ...x, action: v } : x)))} options={["link", "close"]} />
                {b.action === "link" && <Field label="Goes to" value={b.route} onChange={(e) => s(["content", "buttons"])(btns.map((x, j) => (j === i ? { ...x, route: e.target.value } : x)))} error={P(`content.buttons[${i}].route`)} />}
                <Sel label="Style" value={b.style} onChange={(v) => s(["content", "buttons"])(btns.map((x, j) => (j === i ? { ...x, style: v } : x)))} options={["primary", "secondary", "ghost"]} />
                <button className="btn btn--ghost btn--sm" onClick={() => s(["content", "buttons"])(btns.filter((_, j) => j !== i))} data-testid={`popup-button-remove-${i}`}>Remove button</button>
              </div>
            ))}
            {btns.length < 2 && <button className="btn btn--secondary btn--sm" onClick={() => s(["content", "buttons"])([...btns, { label: "Learn more", action: "link", route: "/pricing", style: "primary" }])} data-testid="popup-button-add">Add a button</button>}
          </>}
          {tab === "form" && <>
            <Switch label="Collect e-mail addresses" hint="Adds people to your e-mail list after they confirm by e-mail." checked={d.form.enabled} onChange={s(["form", "enabled"])} testid="popup-form-enabled" />
            {d.form.enabled && <>
              <Field label="Box hint" value={d.form.placeholder} onChange={ev(["form", "placeholder"])} error={P("form.placeholder")} maxLength={40} />
              <Field label="Button label" value={d.form.button_label} onChange={ev(["form", "button_label"])} error={P("form.button_label")} maxLength={24} />
              <Field as="textarea" label="What people agree to" value={d.form.consent_text} onChange={ev(["form", "consent_text"])} error={P("form.consent_text")} rows={2} testid="popup-consent-text" />
              <Field label="Thank-you text" value={d.form.success_text} onChange={ev(["form", "success_text"])} error={P("form.success_text")} maxLength={120} />
            </>}
          </>}
          {tab === "look" && <>
            <Sel label="Size" value={d.design.size} onChange={s(["design", "size"])} options={meta.sizes} />
            <Sel label="Colour" value={d.design.tone} onChange={s(["design", "tone"])} options={meta.tones} />
            <Sel label="Text alignment" value={d.design.align} onChange={s(["design", "align"])} options={["left", "center"]} />
            {d.kind === "slide_in" && <Sel label="Corner" value={d.design.position} onChange={s(["design", "position"])} options={["bottom_right", "bottom_left"]} />}
            <Switch label="Show the close button" checked={d.design.show_close} onChange={s(["design", "show_close"])} />
            <Switch label="Close when someone taps outside" checked={d.design.backdrop_close} onChange={s(["design", "backdrop_close"])} />
            {P("design.show_close") && <p className="form-error">{P("design.show_close")}</p>}
          </>}
          {tab === "when" && <>
            <Sel label="Show it" value={d.trigger.type} onChange={s(["trigger", "type"])} options={meta.triggers} testid="popup-trigger" />
            {d.trigger.type === "delay" && <Field type="number" label="Seconds after the page opens" value={d.trigger.delay_s} onChange={(e) => s(["trigger", "delay_s"])(Number(e.target.value))} error={P("trigger.delay_s")} />}
            {d.trigger.type === "scroll" && <Field type="number" label="After scrolling this % of the page" value={d.trigger.scroll_pct} onChange={(e) => s(["trigger", "scroll_pct"])(Number(e.target.value))} error={P("trigger.scroll_pct")} />}
            {d.trigger.type === "pageviews" && <Field type="number" label="After this many pages in one visit" value={d.trigger.pageviews} onChange={(e) => s(["trigger", "pageviews"])(Number(e.target.value))} error={P("trigger.pageviews")} />}
            {d.trigger.type === "click" && <p className="muted small">Opens when someone clicks an element with data-popup="{id}".</p>}
            <Field type="date" label="Start date (optional)" value={dIn(d.schedule.starts_at)} onChange={ev(["schedule", "starts_at"])} error={P("schedule.starts_at")} />
            <Field type="date" label="End date (optional)" value={dIn(d.schedule.ends_at)} onChange={ev(["schedule", "ends_at"])} error={P("schedule.ends_at")} />
            <Field type="number" label="Priority (0 to 100, higher shows first)" value={d.priority} onChange={(e) => s(["priority"])(Number(e.target.value))} error={P("priority")} />
          </>}
          {tab === "who" && <>
            <Field as="textarea" label="Show on these pages (one per line, * = anything)" value={lines(d.targeting.pages_include)} onChange={(e) => s(["targeting", "pages_include"])(unlines(e.target.value))} error={P("targeting.pages_include")} rows={3} testid="popup-pages" />
            <Field as="textarea" label="Never on these pages" value={lines(d.targeting.pages_exclude)} onChange={(e) => s(["targeting", "pages_exclude"])(unlines(e.target.value))} error={P("targeting.pages_exclude")} rows={2} hint={`Always skipped: ${meta.always_excluded.join(", ")}`} />
            <Sel label="Who" value={d.targeting.audience} onChange={s(["targeting", "audience"])} options={meta.audiences} testid="popup-audience" />
            <Sel label="Visitors" value={d.targeting.visitors} onChange={s(["targeting", "visitors"])} options={["all", "new", "returning"]} />
            <div className="a-row-fields">{["desktop", "mobile"].map((v) => <Switch key={v} label={v === "desktop" ? "Computers" : "Phones"} checked={d.targeting.devices.includes(v)} onChange={(on) => s(["targeting", "devices"])(on ? [...d.targeting.devices, v] : d.targeting.devices.filter((x) => x !== v))} />)}</div>
            {P("targeting.devices") && <p className="form-error">{P("targeting.devices")}</p>}
            <Sel label="How often" value={d.frequency.mode} onChange={s(["frequency", "mode"])} options={meta.frequencies} testid="popup-frequency" />
            {d.frequency.mode === "every_n_days" && <Field type="number" label="At most once every N days" value={d.frequency.n_days} onChange={(e) => s(["frequency", "n_days"])(Number(e.target.value))} error={P("frequency.n_days")} />}
            <Field type="number" label="Days to wait after someone signs up or clicks" value={d.frequency.after_action_days} onChange={(e) => s(["frequency", "after_action_days"])(Number(e.target.value))} error={P("frequency.after_action_days")} />
            <Field label="A/B group (optional)" value={d.ab.group} onChange={ev(["ab", "group"])} error={P("ab.group")} hint="Popups with the same group name compete; each visitor sees one." testid="popup-ab-group" />
            {d.ab.group && <Field type="number" label="Share of visitors (weight)" value={d.ab.weight} onChange={(e) => s(["ab", "weight"])(Number(e.target.value))} error={P("ab.weight")} />}
          </>}
        </div>
      )}
    </Drawer>
  );
}

function Stats({ p, onClose }) {
  const q = useApi(p ? `/admin/popups/${p.id}/stats` : null, { days: 30 });
  const ab = useApi(p?.ab?.group ? `/admin/popups-ab/${p.ab.group}` : null);
  return (
    <Drawer open={!!p} onClose={onClose} title={`Results: ${p?.name || ""}`} testid="popup-stats" wide>
      <DataState q={q}>{(d) => <div className="a-stack">
        <div className="a-tiles">
          <StatTile label="Views (30 days)" value={d.totals.view.toLocaleString()} testid="popup-stat-views" />
          <StatTile label="Click rate" value={pct(d.totals.click_rate)} />
          <StatTile label="Sign-up rate" value={pct(d.totals.submit_rate)} />
          <StatTile label="Closed" value={pct(d.totals.dismiss_rate)} />
        </div>
        <Bars title="Views per day" data={d.series} y="view" testid="popup-views-chart" />
        {p?.ab?.group && <Card title={`A/B group "${p.ab.group}"`} testid="popup-ab">
          {ab.loading ? <Loading rows={1} /> : ab.error ? <ErrorBox error={ab.error} /> : <>
            <p className="muted small">{ab.data.note}</p>
            <ResponsiveTable testid="popup-ab-table" rows={ab.data.variants} columns={[
              { key: "name", label: "Version", primary: true, render: (r) => <b>{r.name}{ab.data.leader === r.id ? " (leading)" : ""}</b> },
              { key: "weight", label: "Weight" }, { key: "view", label: "Views" },
              { key: "c", label: "Click rate", render: (r) => pct(r.click_rate) }, { key: "s", label: "Sign-up rate", render: (r) => pct(r.submit_rate) }]} />
          </>}
        </Card>}
      </div>}</DataState>
    </Drawer>
  );
}

export default function Popups() {
  const toast = useToast();
  const q = useApi("/admin/popups");
  const meta = useApi("/admin/popups/meta");
  const [edit, setEdit] = useState(null);
  const [stats, setStats] = useState(null);
  const [gone, setGone] = useState(null);
  const [tpl, setTpl] = useState("");
  const create = async (template) => {
    try { const r = await post("/admin/popups", template ? { template } : { data: {} }); toast("Popup created as a draft"); q.reload(); setEdit(r.id); }
    catch (x) { toast(x.message, "err"); }
  };
  const status = async (p, st) => {
    try { await post(`/admin/popups/${p.id}/status`, { status: st }); toast(st === "live" ? "Popup is live" : st === "paused" ? "Popup paused" : "Back to draft"); q.reload(); }
    catch (x) { toast(x.problems?.[0]?.message || x.message, "err"); }
  };
  const dup = async (p) => { try { await post(`/admin/popups/${p.id}/duplicate`); toast("Copy made"); q.reload(); } catch (x) { toast(x.message, "err"); } };
  const cols = [
    { key: "name", label: "Popup", primary: true, render: (r) => <span className="a-person"><b>{r.name}</b><small>{KIND[r.kind]}{r.ab?.group ? ` · A/B ${r.ab.group}` : ""}</small></span> },
    { key: "state", label: "State", render: (r) => <Chip tone={TONE[r.state] || "muted"} testid={`popup-state-${r.id}`}>{r.state}</Chip> },
    { key: "views", label: "Views", render: (r) => (r.stats?.view ?? 0).toLocaleString() },
    { key: "rate", label: "Click / sign-up", render: (r) => `${pct(r.stats?.click_rate)} / ${pct(r.stats?.submit_rate)}` },
    { key: "x", label: "", render: (r) => <span className="a-inline-actions" onClick={(e) => e.stopPropagation()} role="presentation">
      {r.status === "live" ? <button className="btn btn--secondary btn--sm" onClick={() => status(r, "paused")} data-testid={`popup-pause-${r.id}`}>Pause</button>
        : <button className="btn btn--primary btn--sm" onClick={() => status(r, "live")} data-testid={`popup-live-${r.id}`}>Go live</button>}
      <button className="btn btn--ghost btn--sm" onClick={() => setStats(r)} data-testid={`popup-results-${r.id}`}>Results</button>
      <button className="btn btn--ghost btn--sm" onClick={() => dup(r)} data-testid={`popup-dup-${r.id}`}>Copy</button>
      <button className="btn btn--ghost btn--sm" onClick={() => setGone(r)} data-testid={`popup-delete-${r.id}`}>Delete</button></span> },
  ];
  const g = q.data?.global;
  return (
    <div className="a-page" data-testid="admin-popups">
      <PageHead title="Popups" lead={g ? `${g["popups.enabled"] ? "Popups are on" : "Popups are switched off in Settings"}. At most ${g["popups.max_per_session"]} per visit, ${g["popups.min_gap_seconds"]} seconds apart.` : " "}
        actions={<div className="a-inline-actions">
          <select aria-label="Start from a template" value={tpl} onChange={(e) => setTpl(e.target.value)} data-testid="popup-template"><option value="">Start from a template</option>{(meta.data?.templates || []).map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}</select>
          <button className="btn btn--primary btn--sm" onClick={() => create(tpl || null)} data-testid="popup-new">{tpl ? "Use template" : "New popup"}</button></div>} />
      <DataState q={q} empty="No popups yet.">{(d) => (d.popups.length
        ? <ResponsiveTable columns={cols} rows={d.popups} onRow={(r) => setEdit(r.id)} testid="popups-table" />
        : <Empty icon="layers" testid="popups-empty">No popups yet. Start from a template above: the e-mail sign-up is a good first one.</Empty>)}</DataState>
      {meta.data && <Editor id={edit} meta={meta.data} onClose={() => setEdit(null)} onSaved={q.reload} />}
      <Stats p={stats} onClose={() => setStats(null)} />
      <Confirm open={!!gone} danger title="Delete this popup?" body="Its results are deleted too." confirmLabel="Delete" onClose={() => setGone(null)} testid="popup-delete-confirm"
               onConfirm={async () => { await del(`/admin/popups/${gone.id}`); toast("Popup deleted"); setGone(null); q.reload(); }} />
    </div>
  );
}
