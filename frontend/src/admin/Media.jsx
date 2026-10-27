// Images (docs/10, docs/16): uploaded site images for logos, popups and pages. Upload, copy the address, delete when unused.
import { useState } from "react";
import { del, post } from "../lib/api";
import { useApi } from "../lib/useApi";
import { sayError } from "../lib/errors";
import { Confirm, useToast } from "../components/Ui";
import { Empty } from "../components/States";
import { DataState, PageHead, when } from "./parts";

const BASE = (process.env.REACT_APP_BACKEND_URL || "").replace(/\/$/, "");
const kb = (b) => (b > 1e6 ? `${(b / 1e6).toFixed(1)} MB` : `${Math.round(b / 1e3)} KB`);

export default function Media() {
  const toast = useToast();
  const q = useApi("/admin/site/assets");
  const [busy, setBusy] = useState(false);
  const [gone, setGone] = useState(null);
  const pick = async (e) => {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (!f) return;
    if (q.data && f.size > q.data.max_bytes) { toast(`That file is over ${kb(q.data.max_bytes)}.`, "err"); return; }
    setBusy(true);
    try {
      const b64 = await new Promise((ok, no) => { const r = new FileReader(); r.onload = () => ok(String(r.result).split(",")[1]); r.onerror = no; r.readAsDataURL(f); });
      await post("/admin/site/assets", { name: f.name.slice(0, 80), data_b64: b64 });
      toast("Image uploaded"); q.reload();
    } catch (x) { toast(sayError(x), "err"); } finally { setBusy(false); }
  };
  const copy = async (a) => { try { await navigator.clipboard.writeText(a.url); toast("Address copied"); } catch { toast(a.url); } };
  return (
    <div className="a-page" data-testid="admin-media">
      <PageHead title="Images" lead={`Logos, popup and page images. PNG, JPEG, WebP or ICO${q.data ? `, up to ${kb(q.data.max_bytes)}` : ""}. Paste an image's address into Site Studio or a popup.`}
        actions={<label className="btn btn--primary btn--sm" data-testid="media-upload">{busy ? "Uploading…" : "Upload image"}<input type="file" accept="image/png,image/jpeg,image/webp,image/x-icon" hidden onChange={pick} disabled={busy} data-testid="media-file" /></label>} />
      <DataState q={q}>{(d) => (!d.assets.length ? <Empty icon="image" testid="media-empty">No images yet. Upload your logo first.</Empty> : (
        <ul className="media-grid" data-testid="media-grid">
          {d.assets.map((a) => (
            <li key={a.id} className="a-card media-item" data-testid={`media-${a.id}`}>
              <span className="media-thumb"><img src={BASE + a.url} alt={a.name} loading="lazy" /></span>
              <b className="a-wrap">{a.name}</b>
              <small className="muted">{kb(a.bytes)} · {when(a.at)}</small>
              <span className="a-inline-actions">
                <button className="btn btn--secondary btn--sm" onClick={() => copy(a)} data-testid={`media-copy-${a.id}`}>Copy address</button>
                <button className="btn btn--ghost btn--sm" onClick={() => setGone(a)} data-testid={`media-delete-${a.id}`}>Delete</button>
              </span>
            </li>
          ))}
        </ul>
      ))}</DataState>
      <Confirm open={!!gone} danger title="Delete this image?" body="Images still used in Site Studio can't be deleted." confirmLabel="Delete" onClose={() => setGone(null)} testid="media-delete-confirm"
               onConfirm={async () => { try { await del(`/admin/site/assets/${gone.id}`); toast("Image deleted"); q.reload(); } catch (x) { toast(sayError(x), "err"); } setGone(null); }} />
    </div>
  );
}
