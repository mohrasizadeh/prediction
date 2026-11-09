// Ad builder (docs/60): pick a claim, a size and a palette mode, and take away a PNG.
//
// The export is a download, and the share sheet where the browser offers one. Since docs/64 a
// batch can also be SCHEDULED: the same full-resolution loop renders each ad, uploads the PNG to
// the media library for a public URL and queues it as a draft. Still nothing is posted from here --
// the queue hands approved posts to the owner's own automation tool, which does the last hop.
// The drawing is in ads/templates.js; this screen is the controls, the preview and the saved list.
import { useEffect, useMemo, useRef, useState } from "react";
import { del, post, put, putFile } from "../lib/api";
import { useApi } from "../lib/useApi";
import { sayError } from "../lib/errors";
import { Confirm, Field, Tabs, useToast } from "../components/Ui";
import { Empty } from "../components/States";
import Icon from "../components/Icon";
import { Card, Chip, DataState, PageHead, when } from "./parts";
import { SIZES } from "./ads/sizes";
import { blobOf, buildData, ensureFonts, paint, safeOverlay, saveZip, shareOrSave, slug } from "./ads/render";

const pct = (x) => (x == null ? "–" : `${Math.round(x * 100)}%`);
// Past the listed times a batch rolls into the next day rather than stacking: ad 5 of 4 slots goes
// to tomorrow's first slot, not on top of ad 1.
const addDays = (iso, n) => { const d = new Date(`${iso}T00:00:00`); d.setDate(d.getDate() + n); return d.toISOString().slice(0, 10); };
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
function Preview({ design, brand, card, cards, mode, accent, fontsReady, onCanvas, guide }) {
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
        // The guide is drawn AFTER onCanvas hands the canvas over, so a download taken from it is
        // the clean image: what is shaded here is the app's furniture, not part of the ad.
        if (guide) safeOverlay(ref.current, design.size);
        setErr("");
      } catch (e) { if (live) setErr(sayError(e)); }
    })();
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(design), brand, card?.fkey, (cards || []).map((c) => c.fkey).join(","), mode, accent, fontsReady, guide]);
  const s = SIZES[design.size] || SIZES.square;
  return (
    <div className="ad-stage" data-testid="ad-preview">
      <canvas ref={ref} width={s.w} height={s.h} style={{ width: PREVIEW_W, height: (PREVIEW_W * s.h) / s.w }} aria-label="Ad preview" />
      {!fontsReady && <small className="muted">Loading the site typeface…</small>}
      {err && <p className="form-error" role="alert">{err}</p>}
    </div>
  );
}

// The batch for tomorrow (docs/60 section 3). The server decides WHAT each ad says -- which player,
// which market, which league, so that twenty ads are not twenty forwards with a shots line -- and
// this draws them. Rendering twenty 1080px canvases at once is what the preview grid is for, so
// each tile paints at a thumbnail size and only the download re-paints at full resolution.
function DayAd({ ad, brand, byKey, cards, fontsReady, onPick, picked }) {
  const ref = useRef(null);
  useEffect(() => {
    let live = true;
    (async () => {
      if (!ref.current || !brand) return;
      const card = (ad.fkeys || []).map((k) => byKey[k]).filter(Boolean)[0] || null;
      const many = (ad.fkeys || []).map((k) => byKey[k]).filter(Boolean);
      const data = await buildData({ design: ad, brand, card, cards: many.length ? many : cards, mode: ad.mode });
      if (!live || !ref.current) return;
      paint(ref.current, { design: ad, brand, data, mode: ad.mode, accent: ad.accent });
    })();
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ad, brand, fontsReady]);
  const s = SIZES[ad.size] || SIZES.square;
  return (
    <li className={"ad-day-item" + (picked ? " on" : "")} data-testid={`ad-day-${ad.template}-${ad.size}`}>
      <label className="ad-day-pick">
        <input type="checkbox" checked={picked} onChange={onPick} aria-label={`Include this ${ad.template} ad`} />
        <canvas ref={ref} width={s.w} height={s.h} style={{ aspectRatio: `${s.w} / ${s.h}` }} />
      </label>
      <small className="muted">{ad.template} · {ad.size} · {ad.mode}</small>
    </li>
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
  const [tab, setTab] = useState("day");
  const canvasRef = useRef(null);
  const tz = -new Date().getTimezoneOffset();
  const [dayDate, setDayDate] = useState("");
  const dayQ = useApi(tab === "day" ? "/admin/ads/day" : null, { tz, ...(dayDate ? { date: dayDate } : {}) });
  const [skip, setSkip] = useState({});
  const [showSafe, setShowSafe] = useState(true);

  const d0 = q.data || {};
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

  const dayCards = useMemo(() => dayQ.data?.cards || [], [dayQ.data]);
  const byKey = useMemo(() => Object.fromEntries(dayCards.map((c) => [c.fkey, c])), [dayCards]);
  const dayAds = (dayQ.data?.ads || []).filter((_, i) => !skip[i]);
  const schedQ = useApi(tab === "day" ? "/admin/social" : null, {});
  const [prog, setProg] = useState(null);           // {i, n} while the batch renders

  // Every ad in the batch, re-painted at full resolution, in one zip. The preview tiles are
  // thumbnails; nothing downloaded is ever an upscale of one.
  const downloadDay = async () => {
    setBusy("day");
    try {
      const off = document.createElement("canvas");
      const blobs = [];
      for (const ad of dayAds) {
        const card = (ad.fkeys || []).map((k) => byKey[k]).filter(Boolean)[0] || null;
        const many = (ad.fkeys || []).map((k) => byKey[k]).filter(Boolean);
        // eslint-disable-next-line no-await-in-loop
        const data = await buildData({ design: ad, brand: dayQ.data.brand || q.data.brand, card, cards: many.length ? many : dayCards, mode: ad.mode });
        paint(off, { design: ad, brand: q.data.brand, data, mode: ad.mode, accent: ad.accent });
        // eslint-disable-next-line no-await-in-loop
        blobs.push(await blobOf(off));
      }
      await saveZip(blobs.filter(Boolean), `ads-${dayQ.data.day}`);
      toast(`${blobs.length} ads saved as a zip`);
    } catch (e) { toast(sayError(e), "err"); } finally { setBusy(""); }
  };

  // docs/64: a job firing at 09:10 has no browser, and ad_plan says plainly that the planner
  // decides what each ad SAYS while the browser still draws it. So the pixels have to exist before
  // the schedule does: this renders the batch exactly as the zip does, uploads each PNG to the
  // media library for its public URL, and queues the lot. Same loop, different destination -- a
  // second renderer on the server would drift from this one and nobody would see it happen.
  const scheduleDay = async () => {
    if (!dayAds.length) return;
    setBusy("sched");
    try {
      const times = schedQ.data?.times?.length ? schedQ.data.times : ["09:10", "13:40", "18:20", "20:50"];
      const off = document.createElement("canvas");
      const items = [];
      for (let i = 0; i < dayAds.length; i += 1) {
        const ad = dayAds[i];
        setProg({ i: i + 1, n: dayAds.length });
        const card = (ad.fkeys || []).map((k) => byKey[k]).filter(Boolean)[0] || null;
        const many2 = (ad.fkeys || []).map((k) => byKey[k]).filter(Boolean);
        // eslint-disable-next-line no-await-in-loop
        const data = await buildData({ design: ad, brand: dayQ.data.brand || q.data.brand, card, cards: many2.length ? many2 : dayCards, mode: ad.mode });
        paint(off, { design: ad, brand: q.data.brand, data, mode: ad.mode, accent: ad.accent });
        // eslint-disable-next-line no-await-in-loop
        const blob = await blobOf(off);
        if (!blob) throw new Error("The browser could not make one of the images.");
        const name = `${slug(ad.headline || ad.template)}-${dayQ.data.day}-${i + 1}.png`;
        // eslint-disable-next-line no-await-in-loop
        const up = await putFile(`/admin/media/upload?name=${encodeURIComponent(name)}`, blob);
        const t = times[i % times.length];
        // Spread past the listed times rather than stacking: ad 5 of 4 slots goes to the next day's
        // first slot, not on top of ad 1.
        const dayOffset = Math.floor(i / times.length);
        // fkeys travel with the post so the match-day e-mail can use the card about a player it
        // is actually naming as its header graphic (docs/69). Instagram never sees them.
        items.push({ media: [up.abs_url], caption: ad.caption || "", kind: "post", fkeys: ad.fkeys || [],
                     scheduled_at: `${addDays(dayQ.data.day, dayOffset)}T${t}:00` });
      }
      const r = await post("/admin/social/batch", items);
      setProg(null);
      toast(r.failed?.length
        ? `${r.queued} scheduled, ${r.failed.length} could not be: ${r.failed[0].error}`
        : `${r.queued} posts scheduled as drafts`, r.failed?.length ? "err" : "ok");
      schedQ.reload();
    } catch (e) { setProg(null); toast(sayError(e), "err"); } finally { setBusy(""); }
  };

  const file = `${slug(design.name || design.template)}-${design.size}`;
  const exportOne = async (how) => {
    setBusy(how);
    try {
      // Re-painted clean: the preview may be carrying the safe-area guide.
      const off = document.createElement("canvas");
      const data = await buildData({ design, brand: d0.brand, card: one, cards: many, mode });
      paint(off, { design, brand: d0.brand, data, mode, accent: design.accent });
      const blob = await blobOf(off);
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
          tabs={[{ id: "day", label: "Post tomorrow" }, { id: "build", label: "Build one" }, { id: "saved", label: `Saved${q.data?.designs?.length ? ` (${q.data.designs.length})` : ""}` }]} />} />
      <DataState q={q}>{(d) => (tab === "day" ? (
        <div className="ad-day" data-testid="ads-day">
          <Card title={dayQ.data ? `${dayQ.data.count} ads for ${dayQ.data.kicker}` : "Building the batch…"} testid="ad-day-head"
                actions={<span className="a-inline-actions">
                  <input type="date" value={dayDate || (dayQ.data?.day || "")} onChange={(e) => setDayDate(e.target.value)} aria-label="Match day" data-testid="ad-day-date" />
                  <button className="btn btn--primary btn--sm" disabled={!!busy || !dayAds.length} onClick={scheduleDay} data-testid="ad-day-schedule">
                    {busy === "sched" ? (prog ? `Rendering ${prog.i} of ${prog.n}…` : "Scheduling…") : `Schedule these ${dayAds.length}`}
                  </button>
                  <button className="btn btn--sm" disabled={!!busy || !dayAds.length} onClick={downloadDay} data-testid="ad-day-zip">
                    <Icon name="download" size={16} />{busy === "day" ? "Rendering…" : `Download ${dayAds.length} as a zip`}</button>
                </span>}>
            {dayQ.error && <p className="form-error" role="alert">{sayError(dayQ.error)}</p>}
            {dayQ.loading && <p className="muted">Picking players, markets and leagues…</p>}
            {dayQ.data && !dayQ.data.ads.length && (
              <p className="muted" data-testid="ad-day-empty">
                No forecasts for {dayQ.data.day}.{" "}
                {dayQ.data.next_day
                  ? <button className="k-link" onClick={() => setDayDate(dayQ.data.next_day)}>The next match day is {dayQ.data.next_day}.</button>
                  : "Run the engine, or pick another date."}
              </p>
            )}
            {dayQ.data?.ads?.length > 0 && (
              <p className="muted" data-testid="ad-day-mix">
                {dayQ.data.cards.length} forecasts across {dayQ.data.leagues.length} leagues and {dayQ.data.markets.length} markets.
                No player appears twice and no club more than twice. Square and vertical only; a story keeps its content
                clear of the app's own buttons. Untick anything you do not want before the zip.
              </p>
            )}
          </Card>
          {dayQ.data?.ads?.length > 0 && (
            <ul className="ad-day-grid" data-testid="ad-day-grid">
              {dayQ.data.ads.map((ad, i) => (
                <DayAd key={`${ad.template}-${i}`} ad={ad} brand={d.brand} byKey={byKey} cards={dayCards}
                       fontsReady={fontsReady} picked={!skip[i]}
                       onPick={() => setSkip((x) => ({ ...x, [i]: !x[i] }))} />
              ))}
            </ul>
          )}
        </div>
      ) : tab === "saved" ? (
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
              <Preview design={design} brand={d.brand} card={one} cards={many} mode={mode} accent={design.accent} fontsReady={fontsReady} guide={showSafe} onCanvas={(c) => { canvasRef.current = c; }} />
              {(design.size === "story") && (
                <label className="ad-guide"><input type="checkbox" checked={showSafe} onChange={(e) => setShowSafe(e.target.checked)} data-testid="ad-safe" />
                  Show what Instagram covers</label>
              )}
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
