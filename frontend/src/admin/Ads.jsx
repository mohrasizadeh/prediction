// Ad builder (docs/60): pick a claim, a size and a palette mode, and take away a PNG.
//
// Nothing is posted to a network. The export is a download, and the share sheet where the browser
// offers one, which was the owner's instruction and is also the only version that needs no
// per-network account. The drawing is in ads/templates.js; this screen is the controls, the preview
// and the saved list.
import { useEffect, useMemo, useRef, useState } from "react";
import { del, post, put } from "../lib/api";
import { useApi } from "../lib/useApi";
import { sayError } from "../lib/errors";
import { Confirm, Field, Tabs, useToast } from "../components/Ui";
import { Empty } from "../components/States";
import Icon from "../components/Icon";
import { Card, Chip, DataState, PageHead, when } from "./parts";
import { SIZES } from "./ads/sizes";
import { blobOf, buildData, ensureFonts, paint, saveZip, shareOrSave, slug } from "./ads/render";

const pct = (x) => (x == null ? "–" : `${Math.round(x * 100)}%`);
const PREVIEW_W = 420;

// Starting words per template, so the screen is never a set of empty boxes. Each one is a sentence
// the product can actually stand behind; the owner edits or replaces them.
const SEED = {
  card: { kicker: "Forecast", subhead: "" },
  run: { kicker: "The last ten", subhead: "Each bar is one game. The dashed column is this match." },
  table: { kicker: "Tonight", headline: "The five strongest forecasts tonight", subhead: "" },
  fixture: { kicker: "Leading forecast", headline: "", subhead: "" },
  finder: { kicker: "Forecast Finder", finder_q: "Players with 2+ shots in 7 of their last 10", subhead: "Ask it yourself. Every part of the sentence is yours to change." },
  stat: { stat_value: "72%", headline: "of our Strong forecasts happened", subhead: "Every forecast we publish is scored after the match, and the record is on the site." },
  quote: { kicker: "Why us", headline: "We show you the reason, not just the number", subhead: "", cta: "See today's forecasts" },
  cover: { kicker: "Today", headline: "Five players worth watching tonight", subhead: "", cta: "Swipe" },
};

function useBrandFonts(brand) {
  const [ready, setReady] = useState(false);
  useEffect(() => {
    let live = true;
    if (!brand) return undefined;
    ensureFonts(brand).then(() => live && setReady(true));
    return () => { live = false; };
  }, [brand]);
  return ready;
}

/** One canvas, repainted whenever anything it reads changes. Drawn at the size's real pixels and
 *  shown at CSS width, so what is on screen is what downloads. */
function Preview({ design, brand, card, cards, mode, accent, fontsReady, onCanvas }) {
  const ref = useRef(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    let live = true;
    (async () => {
      if (!ref.current || !brand) return;
      try {
        const data = await buildData({ design, brand, card, cards, mode });
        if (!live || !ref.current) return;
        paint(ref.current, { design, brand, data, mode, accent });
        onCanvas?.(ref.current);
        setErr("");
      } catch (e) { if (live) setErr(sayError(e)); }
    })();
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(design), brand, card?.fkey, (cards || []).map((c) => c.fkey).join(","), mode, accent, fontsReady]);
  const s = SIZES[design.size] || SIZES.square;
  return (
    <div className="ad-stage" data-testid="ad-preview">
      <canvas ref={ref} width={s.w} height={s.h} style={{ width: PREVIEW_W, height: (PREVIEW_W * s.h) / s.w }} aria-label="Ad preview" />
      {!fontsReady && <small className="muted">Loading the site typeface…</small>}
      {err && <p className="form-error" role="alert">{err}</p>}
    </div>
  );
}

export default function Ads() {
  const toast = useToast();
  const q = useApi("/admin/ads");
  const feed = useApi("/insights", { limit: 60, tiers: "Strong,Solid,Watch" });
  const leagues = useApi("/leagues");
  const [design, setDesign] = useState({ template: "card", size: "square", mode: "dark", name: "", headline: "", subhead: "", kicker: "", cta: "", footnote: "", finder_q: "", stat_value: "", accent: "" });
  const [picked, setPicked] = useState([]);           // fkeys, in the order chosen
  const [editing, setEditing] = useState(null);       // saved design id being replaced
  const [busy, setBusy] = useState("");
  const [gone, setGone] = useState(null);
  const [tab, setTab] = useState("build");
  const canvasRef = useRef(null);

  const brand = q.data?.brand;
  const cat = q.data?.catalogue;
  const fontsReady = useBrandFonts(brand);
  const mode = design.mode;

  // Cards, with the league mark attached: a forecast carries league_id but not the image.
  const cards = useMemo(() => {
    const byId = Object.fromEntries((leagues.data?.leagues || leagues.data || []).map((l) => [l.id, l]));
    return (feed.data || []).map((c) => ({ ...c, league_image: byId[c.league_id]?.image || null }));
  }, [feed.data, leagues.data]);
  const chosen = useMemo(() => picked.map((k) => cards.find((c) => c.fkey === k)).filter(Boolean), [picked, cards]);
  const needs = cat?.templates?.find((t) => t.id === design.template)?.needs || "none";
  const one = chosen[0] || (needs === "card" || needs === "cards" ? cards[0] : null);
  const many = chosen.length ? chosen : cards.slice(0, 8);

  const set = (patch) => setDesign((d) => ({ ...d, ...patch }));
  const pickTemplate = (id) => setDesign((d) => ({ ...d, template: id, ...SEED[id] }));
  // Seed the first template once the catalogue is in, so the screen opens on something drawn.
  useEffect(() => { if (cat && !design.headline && !design.kicker) setDesign((d) => ({ ...d, ...SEED[d.template] })); }, [cat]); // eslint-disable-line react-hooks/exhaustive-deps

  const file = `${slug(design.name || design.template)}-${design.size}`;
  const exportOne = async (how) => {
    setBusy(how);
    try {
      const blob = await blobOf(canvasRef.current);
      if (!blob) throw new Error("The browser could not make the image.");
      const r = await shareOrSave(blob, `${file}.png`, design.headline || brand?.name || "Ad");
      if (r !== "cancelled") toast(r === "shared" ? "Shared" : "Image saved");
    } catch (e) { toast(sayError(e), "err"); } finally { setBusy(""); }
  };

  // A carousel: the cover, then one slide per chosen forecast, then the closing headline. Every
  // slide is drawn on an off-screen canvas at full size, so the zip holds real exports and not
  // screenshots of the preview.
  const exportCarousel = async () => {
    setBusy("zip");
    try {
      const slides = [
        { ...design, template: "cover", size: "square" },
        ...many.slice(0, 8).map((c) => ({ ...design, template: design.template === "cover" || design.template === "quote" ? "card" : design.template, size: "square", _card: c })),
        { ...design, template: "quote", size: "square", headline: design.cta || "See every forecast, with its reasons", cta: "" },
      ];
      const off = document.createElement("canvas");
      const blobs = [];
      for (const s of slides) {
        const c = s._card || one;
        // eslint-disable-next-line no-await-in-loop
        const data = await buildData({ design: s, brand, card: c, cards: many, mode });
        paint(off, { design: s, brand, data, mode, accent: design.accent });
        // eslint-disable-next-line no-await-in-loop
        blobs.push(await blobOf(off));
      }
      await saveZip(blobs.filter(Boolean), slug(design.name || "carousel"));
      toast(`${blobs.length} slides saved as a zip`);
    } catch (e) { toast(sayError(e), "err"); } finally { setBusy(""); }
  };

  const save = async () => {
    setBusy("save-ad");
    try {
      const body = { ...design, fkeys: picked };
      const r = editing ? await put(`/admin/ads/${editing}`, body) : await post("/admin/ads", body);
      setEditing(r.id); toast("Ad saved"); q.reload();
    } catch (e) { toast(sayError(e), "err"); } finally { setBusy(""); }
  };

  const open = (d) => {
    setDesign({ ...design, ...d });
    setPicked(d.fkeys || []);
    setEditing(d.id);
    setTab("build");
  };

  const toggleCard = (fkey) => setPicked((ps) => {
    if (ps.includes(fkey)) return ps.filter((x) => x !== fkey);
    const cap = needs === "card" ? 1 : cat?.max_slides || 10;
    return [...ps, fkey].slice(-cap);
  });

  return (
    <div className="a-page" data-testid="admin-ads">
      <PageHead title="Ad builder" testid="ads-head"
        lead="Your palette, your typeface, your crests, and the product's own numbers. Pick a claim, pick a size, download the image. Nothing is posted anywhere."
        actions={<Tabs value={tab} onChange={setTab} testid="ads-tabs"
          tabs={[{ id: "build", label: "Build" }, { id: "saved", label: `Saved${q.data?.designs?.length ? ` (${q.data.designs.length})` : ""}` }]} />} />
      <DataState q={q}>{(d) => (tab === "saved" ? (
        !d.designs.length ? <Empty icon="image" testid="ads-empty">No saved ads yet. Build one and press Save.</Empty> : (
          <ul className="ad-saved" data-testid="ads-saved">
            {d.designs.map((x) => (
              <li key={x.id} className="a-card" data-testid={`ad-saved-${x.id}`}>
                <b className="a-wrap">{x.name}</b>
                <small className="muted">{d.catalogue.templates.find((t) => t.id === x.template)?.label} · {SIZES[x.size] ? `${SIZES[x.size].w}x${SIZES[x.size].h}` : x.size} · {when(x.at)}</small>
                <span className="a-inline-actions">
                  <button className="btn btn--secondary btn--sm" onClick={() => open(x)} data-testid={`ad-open-${x.id}`}>Open</button>
                  <button className="btn btn--danger btn--sm" onClick={() => setGone(x)} data-testid={`ad-del-${x.id}`}>Delete</button>
                </span>
              </li>
            ))}
          </ul>
        )
      ) : (
        <div className="ad-grid">
          <div className="ad-controls">
            <Card title="The claim" testid="ad-templates">
              <ul className="ad-tpl">
                {d.catalogue.templates.map((t) => (
                  <li key={t.id}>
                    <button type="button" className={"ad-tpl-btn" + (design.template === t.id ? " on" : "")} aria-pressed={design.template === t.id}
                            onClick={() => pickTemplate(t.id)} data-testid={`ad-tpl-${t.id}`}>
                      <b>{t.label}</b><small>{t.about}</small>
                    </button>
                  </li>
                ))}
              </ul>
            </Card>

            <Card title="Size and palette" testid="ad-size">
              <div className="ad-sizes">
                {d.catalogue.sizes.map((s) => (
                  <button key={s.id} type="button" className={"k-chip" + (design.size === s.id ? " on" : "")} aria-pressed={design.size === s.id}
                          onClick={() => set({ size: s.id })} title={s.about} data-testid={`ad-size-${s.id}`}>{s.label}</button>
                ))}
              </div>
              <div className="ad-sizes">
                {d.catalogue.modes.map((m) => (
                  <button key={m} type="button" className={"k-chip" + (mode === m ? " on" : "")} aria-pressed={mode === m}
                          onClick={() => set({ mode: m })} data-testid={`ad-mode-${m}`}>{m === "dark" ? "Dark" : "Light"}</button>
                ))}
                <span className="ad-accent">
                  <label htmlFor="ad-accent">Accent</label>
                  <input id="ad-accent" type="color" value={design.accent || brand?.colors?.[mode]?.accent || "#38D996"}
                         onChange={(e) => set({ accent: e.target.value })} data-testid="ad-accent" />
                  {design.accent && <button type="button" className="k-link" onClick={() => set({ accent: "" })}>Use the site accent</button>}
                </span>
              </div>
              <small className="muted">Both palettes come from Site Studio, so changing the site changes the ads. The accent here only overrides this one ad.</small>
            </Card>

            <Card title="Words" testid="ad-words">
              <Field label="Name this ad" value={design.name} onChange={(e) => set({ name: e.target.value })} placeholder={d.catalogue.templates.find((t) => t.id === design.template)?.label} testid="ad-name" />
              <Field label="Kicker" hint="The small line above, in the accent colour." value={design.kicker} onChange={(e) => set({ kicker: e.target.value })} testid="ad-kicker" />
              {needs === "finder" && <Field label="The question" as="textarea" rows={2} value={design.finder_q} onChange={(e) => set({ finder_q: e.target.value })} testid="ad-finderq" />}
              {(design.template === "stat" || needs === "finder") && <Field label="The number" value={design.stat_value} onChange={(e) => set({ stat_value: e.target.value })} testid="ad-stat" />}
              {design.template !== "card" && design.template !== "run" && <Field label="Headline" as="textarea" rows={2} value={design.headline} onChange={(e) => set({ headline: e.target.value })} testid="ad-headline" />}
              <Field label={design.template === "card" || design.template === "run" ? "Line under the strip" : "Sub-head"} as="textarea" rows={2} value={design.subhead} onChange={(e) => set({ subhead: e.target.value })} testid="ad-subhead" />
              {(design.template === "quote" || design.template === "cover") && <Field label="Button" value={design.cta} onChange={(e) => set({ cta: e.target.value })} testid="ad-cta" />}
              <small className="muted">The disclaimer is drawn on every ad and there is no switch for it. The words rules apply here exactly as they do on the site.</small>
            </Card>

            {needs !== "none" && (
              <Card title={needs === "card" ? "Which forecast" : "Which forecasts"} testid="ad-pick"
                    actions={picked.length ? <button className="k-link" onClick={() => setPicked([])} data-testid="ad-clear">Clear</button> : null}>
                {feed.error && <p className="form-error" role="alert">{sayError(feed.error)}</p>}
                {!feed.error && !cards.length && <p className="muted">No forecasts are waiting for a match right now, so there is nothing to put on a card. Run the engine first.</p>}
                <ul className="ad-pickers">
                  {cards.slice(0, 40).map((c) => (
                    <li key={c.fkey}>
                      <button type="button" className={"ad-pick-btn" + (picked.includes(c.fkey) ? " on" : "")} aria-pressed={picked.includes(c.fkey)}
                              onClick={() => toggleCard(c.fkey)} data-testid={`ad-pick-${c.fkey}`}>
                        <b>{c.player?.name || c.team?.name}</b>
                        <small>{[c.market, c.opp?.name && `vs ${c.opp.name}`].filter(Boolean).join(" · ")}</small>
                        <em>{pct(c.p)}</em>
                        {picked.includes(c.fkey) && <Icon name="check" size={16} />}
                      </button>
                    </li>
                  ))}
                </ul>
                {needs === "cards" && <small className="muted">Order matters: the list is drawn in the order you pick. Nothing picked uses the strongest first.</small>}
              </Card>
            )}
          </div>

          <div className="ad-side">
            <Card title="Preview" testid="ad-preview-card"
                  actions={<Chip tone="brand" testid="ad-px">{SIZES[design.size]?.w} x {SIZES[design.size]?.h}</Chip>}>
              <Preview design={design} brand={d.brand} card={one} cards={many} mode={mode} accent={design.accent} fontsReady={fontsReady} onCanvas={(c) => { canvasRef.current = c; }} />
              <div className="ad-actions">
                <button className="btn btn--primary btn--sm" disabled={!!busy} onClick={() => exportOne("save")} data-testid="ad-download">
                  <Icon name="download" size={16} />{busy === "save" ? "Making the image…" : "Download PNG"}</button>
                <button className="btn btn--secondary btn--sm" disabled={!!busy} onClick={() => exportOne("share")} data-testid="ad-share">
                  <Icon name="send" size={16} />Share</button>
                <button className="btn btn--secondary btn--sm" disabled={!!busy} onClick={exportCarousel} data-testid="ad-carousel">
                  <Icon name="layers" size={16} />{busy === "zip" ? "Rendering slides…" : "Carousel as a zip"}</button>
                <button className="btn btn--secondary btn--sm" disabled={!!busy} onClick={save} data-testid="ad-save">
                  {busy === "save-ad" ? "Saving…" : editing ? "Save changes" : "Save ad"}</button>
                {editing && <button className="k-link" onClick={() => setEditing(null)} data-testid="ad-new">Save as a new ad instead</button>}
              </div>
              <small className="muted">The carousel is the cover, a slide for each forecast you picked, and a closing panel, all square.</small>
            </Card>
          </div>
        </div>
      ))}</DataState>
      <Confirm open={!!gone} danger title="Delete this ad?" body="Only the saved settings go. Images you have already downloaded are yours." confirmLabel="Delete"
               onClose={() => setGone(null)} testid="ad-del-confirm"
               onConfirm={async () => { try { await del(`/admin/ads/${gone.id}`); toast("Ad deleted"); if (editing === gone.id) setEditing(null); q.reload(); } catch (e) { toast(sayError(e), "err"); } setGone(null); }} />
    </div>
  );
}
