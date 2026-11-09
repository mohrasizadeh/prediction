// Which pages are switched on (docs/67).
//
// ONE map, read by the navigation AND by the router. They used to be two lists that happened to
// agree; a page hidden from the nav but still answering on its URL is not hidden, it is just
// harder to find -- and the owner, looking at a nav without it, believes it is off.
//
// A page with no entry here has no switch and is always on: Today, a match, a player, a club,
// pricing, the account and the legal pages. Those are the product, not features of it.
export const PAGE_FLAGS = {
  "/likely": "likely",
  "/insights": "insights",
  "/finder": "finder",
  "/combos": "combos",
  "/explore": "explore",
  "/leagues": "explore",
  "/teams": "explore",
  "/compare": "compare",
  "/referees": "referees",
  "/referee": "referees",
  "/track-record": "track_record",
  "/learn": "learn",
  "/following": "following",
  "/search": "search",
  "/live": "live",
};

/** The flag governing a path, or null when the path is always on. Matches the first segment, so
 *  /learn/how-we-measure and /referee/Michael%20Oliver follow their section. */
export function flagFor(path) {
  const seg = `/${String(path || "").split("?")[0].split("/").filter(Boolean)[0] || ""}`;
  return PAGE_FLAGS[seg] || null;
}

/** Off only when the owner has explicitly switched it off. An unknown flag, a config that has not
 *  loaded yet, or a failed load all leave the page ON: a visitor seeing a page the owner meant to
 *  hide is a smaller failure than a blank site because one request did not land. */
export function pageOn(cfg, path) {
  const f = flagFor(path);
  return !f || cfg?.features?.[f] !== false;
}

export const featureOn = (cfg, name) => cfg?.features?.[name] !== false;
