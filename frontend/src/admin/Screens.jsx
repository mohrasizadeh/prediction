// Screens (docs/67): which screens visitors can reach.
//
// Named Screens, not Pages: "Pages" in this admin is already the CMS, and two menu items called
// the same thing is a trap for whoever is looking for the other one.
//
// These are the same `features.*` settings the Settings screen can edit, surfaced as a short list
// of switches with the page they govern named beside them. Settings is a search box over 270 keys;
// deciding what a visitor sees should not require knowing what a key is called.
//
// Turning one off removes the page from the navigation, from the footer and from its URL -- the
// nav and the router read one map (lib/features.js), so they cannot disagree.
import { useMemo, useState } from "react";
import { put } from "../lib/api";
import { useApi } from "../lib/useApi";
import { useSite } from "../lib/site";
import { sayError } from "../lib/errors";
import { Switch, useToast } from "../components/Ui";
import { Card, DataState, PageHead } from "./parts";

// Grouped by what a decision is actually about, not by where the key lives.
const GROUPS = [
  { title: "The main screens", lead: "What a visitor can reach from the navigation.", keys: [
    ["features.likely", "Most likely", "The ranked list of what is likeliest in the next few hours. The screen a new visitor should land on."],
    ["features.insights", "Insights", "The older feed, ranked by how far a line sits from a player's usual game. Two ranked feeds is one more than most people want."],
    ["features.finder", "Finder", "Search every line by player, market and run. A power feature."],
    ["features.combos", "Combos", "Build and track a combination of lines."],
    ["features.explore", "Explore", "The browse hub, and the leagues and clubs directories under it."],
    ["features.track_record", "Track record", "How the forecasts actually came out. The page that makes the rest believable."],
    ["features.learn", "Learn", "How the engine works, in plain words."],
  ] },
  { title: "Secondary screens", lead: "Reachable, but not part of the first impression.", keys: [
    ["features.compare", "Compare", "Two players or clubs side by side."],
    ["features.referees", "Referees", "Referee pages and the directory."],
    ["features.following", "Following", "A signed-in reader's followed players and clubs."],
    ["features.search", "Search", "The search overlay and its results page."],
    ["features.live", "Live", "In-play tracking. Leave off until the live feed is trusted."],
  ] },
  { title: "Inside the pages", lead: "Parts of a screen rather than a screen.", keys: [
    ["features.squad_grid", "Squad grid", "The per-player grid on a club page."],
    ["features.team_totals", "Team totals", "Club-level lines beside the player ones."],
    ["features.against", "Conceded stats", "What a club gives up, not only what it does."],
    ["features.leaderboards", "Leaderboards", "Ranked tables on club and league pages."],
    ["features.show_xg", "Show xG", "Expected goals where they appear."],
    ["features.show_lineups", "Show lineups", "Announced elevens on the match page."],
    ["features.show_tactics", "Show tactics", "Tactic chips on cards and match pages."],
    ["features.show_match_probs", "Show match result", "The win / draw / loss bar."],
    ["features.beta_tag", "Beta tag", "The beta marker. Take it off when the record speaks for itself."],
  ] },
];

export default function Screens() {
  const toast = useToast();
  const { reload: reloadSite } = useSite();
  const q = useApi("/admin/settings");
  const [busy, setBusy] = useState("");
  const rows = useMemo(() => {
    const by = {};
    (Array.isArray(q.data) ? q.data : []).forEach((r) => { by[r.key] = r; });
    return by;
  }, [q.data]);

  const flip = async (key, value) => {
    setBusy(key);
    try {
      await put(`/admin/settings/${encodeURIComponent(key)}`, { value });
      q.reload();
      reloadSite();                 // the public config is cached; a switch should take effect now
      toast(value ? "Switched on" : "Switched off");
    } catch (e) { toast(sayError(e), "err"); } finally { setBusy(""); }
  };

  return (
    <section className="pg" data-testid="screens-page">
      <PageHead title="Screens" testid="screens-head"
        lead="Which screens visitors can reach. Switching one off removes it from the navigation, from the footer and from its address — a page hidden from the menu but still answering on its URL is not hidden." />
      <DataState q={q}>
        {GROUPS.map((g) => (
          <Card key={g.title} title={g.title} testid={`screens-group-${g.title.replace(/\s+/g, "-").toLowerCase()}`}>
            <p className="pg-lead">{g.lead}</p>
            <ul className="pg-list">
              {g.keys.map(([key, label, help]) => {
                const r = rows[key];
                const on = r ? !!r.value : true;
                return (
                  <li key={key} className="pg-row">
                    <span className="pg-text">
                      <b>{label}</b>
                      <small>{help}</small>
                    </span>
                    <Switch checked={on} disabled={busy === key || !r} onChange={(v) => flip(key, v)}
                      label={`${label} on`} testid={`screens-switch-${key}`} />
                  </li>
                );
              })}
            </ul>
          </Card>
        ))}
      </DataState>
    </section>
  );
}
