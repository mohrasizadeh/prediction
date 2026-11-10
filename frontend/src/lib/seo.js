// The document head (docs/71).
//
// WHAT WAS WRONG. Every URL on the site shared one title -- `<title>Forecast</title>`, left over
// from before the brand was Forecast Zone -- and there was no description, no canonical and no og:
// tag anywhere. So every link shared to WhatsApp, X or Slack previewed as a bare URL, and every
// page in a search result would have carried the same heading. Meanwhile seo.title_template,
// seo.description_template and seo.og_image had been in Site Studio and in /api/site/config from
// the start with nothing reading them: a screen that implied control it did not have (docs/67).
//
// WHAT THIS CANNOT DO, said plainly because it decides what step comes next. This is a
// client-rendered app: the HTML a crawler is handed is `<div id="root"></div>`. Writing tags here
// fixes the tab, the bookmark, and what Google sees on its SECOND, rendering pass. It does NOT fix
// the first pass, and it does not fix link previews at all -- Slack, WhatsApp, X and Facebook read
// the HTML they are served and never run JavaScript. The fallbacks in index.html are what those
// crawlers get, so they are the brand-level ones. Per-page previews need the public surface
// rendered somewhere we control; until then this is the half that is available.

const MARK = "data-seo";

function upsert(sel, make) {
  let el = document.head.querySelector(sel);
  if (!el) {
    el = make();
    el.setAttribute(MARK, "1");
    document.head.appendChild(el);
  }
  return el;
}

function meta(key, val, attr = "name") {
  const sel = `meta[${attr}="${key}"]`;
  if (!val) {
    const dead = document.head.querySelector(`${sel}[${MARK}]`);
    if (dead) dead.remove();
    return;
  }
  const el = upsert(sel, () => {
    const m = document.createElement("meta");
    m.setAttribute(attr, key);
    return m;
  });
  if (el.getAttribute("content") !== val) el.setAttribute("content", val);
}

function link(rel, href) {
  const sel = `link[rel="${rel}"]`;
  if (!href) {
    const dead = document.head.querySelector(`${sel}[${MARK}]`);
    if (dead) dead.remove();
    return;
  }
  const el = upsert(sel, () => {
    const l = document.createElement("link");
    l.setAttribute("rel", rel);
    return l;
  });
  if (el.getAttribute("href") !== href) el.setAttribute("href", href);
}

// A template is used only when the page can fill every placeholder it names. The shipped default is
// "{name}: {team1} vs {team2} forecasts" -- written for a match page -- and running it on the Finder
// would produce "Forecast Zone:  vs  forecasts". Returning null instead lets the caller fall back to
// a shape that always reads correctly, so one setting can serve the page it was written for without
// damaging the other twenty.
export function fill(tpl, vars) {
  if (!tpl || typeof tpl !== "string") return null;
  const keys = [...tpl.matchAll(/\{(\w+)\}/g)].map((m) => m[1]);
  if (keys.some((k) => !vars[k])) return null;
  return tpl.replace(/\{(\w+)\}/g, (_, k) => vars[k]).replace(/\s+/g, " ").trim() || null;
}

export function absolute(url) {
  if (!url) return "";
  if (/^https?:\/\//i.test(url)) return url;
  if (url.startsWith("/")) return window.location.origin + url;
  return "";
}

// The address this page should be indexed under: path only. Query and hash are dropped on purpose
// -- ?tab=, ?market= and a preview token are all the same page to a search engine, and leaving them
// on would split one page's standing across a dozen near-duplicate URLs.
export function canonicalUrl(pathname = window.location.pathname) {
  const p = pathname.length > 1 ? pathname.replace(/\/+$/, "") : pathname;
  return window.location.origin + (p || "/");
}

export function head({ title, description, image, type = "website", noindex = false, brand = "", pathname } = {}) {
  if (title && document.title !== title) document.title = title;
  const url = canonicalUrl(pathname);
  const img = absolute(image);

  meta("description", description || "");
  link("canonical", url);

  meta("og:title", title || "", "property");
  meta("og:description", description || "", "property");
  meta("og:url", url, "property");
  meta("og:type", type, "property");
  meta("og:site_name", brand || "", "property");
  meta("og:image", img, "property");

  // summary_large_image only pays off when there is an image to be large. Without one X renders an
  // empty banner, which looks worse than the small card.
  meta("twitter:card", img ? "summary_large_image" : "summary");
  meta("twitter:title", title || "");
  meta("twitter:description", description || "");
  meta("twitter:image", img);

  meta("robots", noindex ? "noindex,nofollow" : "");
}
