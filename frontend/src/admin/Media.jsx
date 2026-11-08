// Media library (docs/60): images and video the owner uploads, with a public address each.
//
// Uploading and deleting need `site.write`, so the owner and staff who have it. READING needs
// nothing, which is the whole point: the address has to work in a mail client, in a popup and on a
// page, none of which can sign in. The address shown is the absolute one -- scheme and host
// included -- because a relative path is broken in every e-mail client, which is how this screen
// came to be rewritten.
import { useMemo, useState } from "react";
import { del, putFile } from "../lib/api";
import { useApi } from "../lib/useApi";
import { sayError } from "../lib/errors";
import { Confirm, Tabs, useToast } from "../components/Ui";
import { Empty } from "../components/States";
import Icon from "../components/Icon";
import { Card, DataState, PageHead, when } from "./parts";

const BASE = (process.env.REACT_APP_BACKEND_URL || "").replace(/\/$/, "");
const size = (b) => (b >= 1048576 ? `${(b / 1048576).toFixed(1)} MB` : b < 1024 ? `${b} bytes` : `${Math.round(b / 1024)} KB`);
const IMG = "image/png,image/jpeg,image/webp,image/gif,image/x-icon";
const VID = "video/mp4,video/webm,video/quicktime";

// What to paste into an e-mail. An image is an <img> with a width, because a mail client needs the
// width in the markup. A video is NOT a <video>: Gmail, Outlook and Yahoo all strip that tag, so
// what actually reaches a reader is a poster image wrapped in a link to the file (docs/60).
function snippetFor(a, poster) {
  if (a.kind === "image") {
    return `<img src="${a.abs_url}" alt="" width="600" style="display:block;width:100%;max-width:600px;height:auto;border:0;" />`;
  }
  const img = poster ? poster.abs_url : "PASTE-A-POSTER-IMAGE-ADDRESS";
  return `<a href="${a.abs_url}" target="_blank" style="display:block;max-width:600px;">
  <img src="${img}" alt="Play the video" width="600" style="display:block;width:100%;max-width:600px;height:auto;border:0;" />
</a>`;
}

function Row({ a, poster, onCopy, onDelete }) {
  const [show, setShow] = useState(false);
  return (
    <li className="a-card media-item" data-testid={`media-${a.id}`}>
      <span className="media-thumb">
        {a.kind === "video"
          ? <video src={BASE + a.url} controls preload="metadata" playsInline />
          : <img src={BASE + a.url} alt={a.name} loading="lazy" />}
      </span>
      <b className="a-wrap">{a.name}</b>
      <small className="muted">{a.kind === "video" ? "Video" : "Image"} · {size(a.bytes)} · {when(a.at)}{a.by ? ` · ${a.by}` : ""}</small>
      <code className="a-mono media-url">{a.abs_url}</code>
      <span className="a-inline-actions">
        <button className="btn btn--secondary btn--sm" onClick={() => onCopy(a.abs_url, "Address copied")} data-testid={`media-copy-${a.id}`}>
          <Icon name="copy" size={14} />Copy address</button>
        <button className="btn btn--secondary btn--sm" onClick={() => setShow((x) => !x)} aria-expanded={show} data-testid={`media-embed-${a.id}`}>
          For an e-mail</button>
        <button className="btn btn--danger btn--sm" onClick={() => onDelete(a)} data-testid={`media-delete-${a.id}`}>Delete</button>
      </span>
      {show && (
        <div className="media-embed">
          {a.kind === "video" && (
            <p className="muted">Mail clients strip a video tag, so this is a poster image that links to the file. {poster
              ? <>The newest image in the library is used as the poster.</>
              : <>Upload an image first and it becomes the poster.</>}</p>
          )}
          <pre className="a-jt-wrap" data-testid={`media-snippet-${a.id}`}>{snippetFor(a, poster)}</pre>
          <button className="btn btn--secondary btn--sm" onClick={() => onCopy(snippetFor(a, poster), "Snippet copied")}>
            <Icon name="copy" size={14} />Copy the snippet</button>
        </div>
      )}
    </li>
  );
}

export default function Media() {
  const toast = useToast();
  const q = useApi("/admin/site/assets");
  const [busy, setBusy] = useState(false);
  const [gone, setGone] = useState(null);
  const [tab, setTab] = useState("all");

  const assets = useMemo(() => q.data?.assets || [], [q.data]);
  const shown = useMemo(() => assets.filter((a) => tab === "all" || a.kind === tab), [assets, tab]);
  const poster = useMemo(() => assets.find((a) => a.kind === "image") || null, [assets]);

  const copy = async (text, said) => {
    try { await navigator.clipboard.writeText(text); toast(said); }
    catch { toast("Your browser blocked the clipboard. Select the text and copy it.", "err"); }
  };

  const pick = async (e) => {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (!f) return;
    const vid = String(f.type || "").startsWith("video/");
    const cap = vid ? q.data?.max_video_bytes : q.data?.max_image_bytes;
    if (cap && f.size > cap) { toast(`That file is ${size(f.size)}. The limit for a ${vid ? "video" : "image"} is ${size(cap)}.`, "err"); return; }
    setBusy(true);
    try {
      // Raw bytes, not base64: a 25 MB video would be a 34 MB JSON body (docs/60).
      await putFile(`/admin/media/upload?name=${encodeURIComponent(f.name.slice(0, 80))}`, f);
      toast(vid ? "Video uploaded" : "Image uploaded");
      q.reload();
    } catch (x) { toast(sayError(x), "err"); } finally { setBusy(false); }
  };

  return (
    <div className="a-page" data-testid="admin-media">
      <PageHead title="Media" testid="media-head"
        lead={`Images and video with a public address each, for an e-mail, a popup, a page or an ad. ${q.data ? `Images up to ${size(q.data.max_image_bytes)}, video up to ${size(q.data.max_video_bytes)}, ${q.data.max_files} files in all.` : ""}`}
        actions={<>
          <label className="btn btn--primary btn--sm" data-testid="media-upload">{busy ? "Uploading…" : "Upload image"}
            <input type="file" accept={IMG} hidden onChange={pick} disabled={busy} data-testid="media-file" /></label>
          <label className="btn btn--secondary btn--sm" data-testid="media-upload-video">Upload video
            <input type="file" accept={VID} hidden onChange={pick} disabled={busy} data-testid="media-file-video" /></label>
        </>} />
      <DataState q={q}>{() => (
        <>
          <Tabs value={tab} onChange={setTab} testid="media-tabs"
            tabs={[{ id: "all", label: `All (${assets.length})` },
                   { id: "image", label: `Images (${assets.filter((a) => a.kind === "image").length})` },
                   { id: "video", label: `Video (${assets.filter((a) => a.kind === "video").length})` }]} />
          {!shown.length ? <Empty icon="image" testid="media-empty">Nothing here yet. Upload your logo first.</Empty> : (
            <ul className="media-grid" data-testid="media-grid">
              {shown.map((a) => <Row key={a.id} a={a} poster={poster} onCopy={copy} onDelete={setGone} />)}
            </ul>
          )}
          <Card title="Where these addresses work" testid="media-notes">
            <ul className="a-notes">
              <li><b>E-mail.</b> Paste the address into a template's HTML. It is absolute on purpose: a relative one resolves against the mail client and shows a broken image.</li>
              <li><b>Video in an e-mail.</b> Every major mail client strips a video tag. Use the snippet above, which is a poster image linking to the file, and the reader watches it in a browser.</li>
              <li><b>Site Studio, popups and pages.</b> Paste the same address. Anything in use cannot be deleted until it is replaced there.</li>
              <li><b>Caching.</b> A file is served with a one-year immutable cache, so replacing one means uploading the new file and swapping the address, not overwriting it.</li>
            </ul>
          </Card>
        </>
      )}</DataState>
      <Confirm open={!!gone} danger title="Delete this file?" confirmLabel="Delete" onClose={() => setGone(null)} testid="media-delete-confirm"
               body="Anywhere that points at this address will show nothing. A file used by the site, a popup, an e-mail template or a page cannot be deleted until it is replaced there."
               onConfirm={async () => { try { await del(`/admin/site/assets/${gone.id}`); toast("File deleted"); q.reload(); } catch (x) { toast(sayError(x), "err"); } setGone(null); }} />
    </div>
  );
}
