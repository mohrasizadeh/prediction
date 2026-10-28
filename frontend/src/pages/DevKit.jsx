// Hidden page /dev/kit (docs/24): every shared component, light and dark side by side. Sample values are
// labelled examples for the kit only; real screens read the API.
import { useState } from "react";
import { useTitle } from "../components/Football";
import {
  BottomSheet, ChipsRow, DateScroller, EmptyState, ErrorState, FilterGroup, FilterSheet, ForecastCard,
  HitStrip, LiveCard, LivePill, RangeSlider, Segmented, Skeleton, TierBadge, WdlBar, isoDay,
} from "../components/ui";

const day = (o) => { const d = new Date(); d.setDate(d.getDate() + o); return isoDay(d); };
const SAMPLE_CARD = {
  id: "kit", fkey: "kit:1", scope: "player", stat: "sot", thr: 1.5, market: "2+ shots on target", p: 0.78, tier: "Strong",
  player: { id: "kit-player", name: "Example Player" }, team: { name: "Home FC" }, opp: { name: "Away FC" }, home_iid: 1, team_iid: 1, opp_iid: 2,
  reasons: ["Example reason: the opponent allows many shots on target away.", "Example: he averages 1.9 on target per 90 at home."],
  p_play: 0.91, lineup_confirmed: false,
  more_lines: [{ fkey: "kit:2", market: "1+ shot on target", p: 0.94, tier: "Strong" }, { fkey: "kit:3", market: "3+ shots", p: 0.69, tier: "Solid" }],
};
const SAMPLE_LIVE = { sid: 1, status: "LIVE", minute: "67'", league_name: "Example League", home: { name: "Home FC" }, away: { name: "Away FC" }, score: { home: 2, away: 1 } };
const SAMPLE_EVENTS = [{ type: "goal", side: "home", player_name: "Example", minute: "12'", minute_num: 12 }, { type: "yellow_card", side: "away", player_name: "Sample", minute: "40'", minute_num: 40 }, { type: "goal", side: "home", player_name: "Example", minute: "67'", minute_num: 67 }];

function Panel({ theme }) {
  const [d, setD] = useState(day(0));
  const [chip, setChip] = useState("all");
  const [seg, setSeg] = useState("l5");
  const [range, setRange] = useState([5, 15]);
  const [one, setOne] = useState(70);
  const [sheet, setSheet] = useState(false);
  const [filters, setFilters] = useState(false);
  const t = theme === "light" ? "Light" : "Dark";
  return (
    <section className={`kit-panel kit-${theme}`} data-testid={`kit-${theme}`}>
      <h2>{t}</h2>
      <div><h3 className="k-sec">Date scroller</h3><DateScroller value={d} onChange={setD} gameDays={new Set([day(-1), day(0), day(1), day(2)])} testid={`kit-${theme}-dates`} /></div>
      <div><h3 className="k-sec">Chips row · Segmented</h3>
        <div className="kit-row">
          <ChipsRow value={chip} onChange={setChip} label="Example chips" testid={`kit-${theme}-chips`} options={[{ id: "all", label: "All", count: 9 }, { id: "lg", label: "Leagues", count: 3, accent: true }, { id: "mk", label: "Market" }]} />
          <Segmented value={seg} onChange={setSeg} label="Window" testid={`kit-${theme}-seg`} options={[{ id: "l5", label: "Last 5" }, { id: "season", label: "Season" }]} />
        </div>
      </div>
      <div><h3 className="k-sec">Range slider</h3>
        <RangeSlider min={1} max={20} value={range} onChange={setRange} label="Games" format={(v, i) => (i === 1 ? `${v} games` : v)} testid={`kit-${theme}-range2`} />
        <RangeSlider min={50} max={95} value={one} onChange={setOne} label="Minimum likelihood" format={(v) => `${v}%`} testid={`kit-${theme}-range1`} />
      </div>
      <div className="kit-two">
        <div><h3 className="k-sec">Hit-rate strip</h3><HitStrip hits={[true, false, true, true, false, true, true, true, false, true]} label="Example" testid={`kit-${theme}-strip`} /></div>
        <div><h3 className="k-sec">Win / draw / loss</h3><WdlBar home={0.62} draw={0.22} away={0.16} testid={`kit-${theme}-wdl`} /></div>
      </div>
      <div><h3 className="k-sec">Tiers · colour + word + dots</h3>
        <div className="kit-row"><TierBadge tier="Strong" testid={`kit-${theme}-strong`} /><TierBadge tier="Solid" testid={`kit-${theme}-solid`} /><TierBadge tier="Watch" testid={`kit-${theme}-watch`} /><LivePill count={2} onClick={() => setSheet(true)} testid={`kit-${theme}-pill`} /></div>
      </div>
      <div><h3 className="k-sec">Buttons</h3>
        <div className="kit-row">
          <button type="button" className="btn btn--primary" onClick={() => setFilters(true)} data-testid={`kit-${theme}-open-filters`}>Primary</button>
          <button type="button" className="btn btn--secondary">Secondary</button>
          <button type="button" className="k-link">Text link →</button>
          <button type="button" className="btn btn--danger">Delete</button>
        </div>
      </div>
      <div><h3 className="k-sec">Forecast card (tap it for the sheet)</h3><ForecastCard f={SAMPLE_CARD} testid={`kit-${theme}-fc`} /></div>
      <div><h3 className="k-sec">Live card</h3><LiveCard f={SAMPLE_LIVE} events={SAMPLE_EVENTS} testid={`kit-${theme}-live`} /></div>
      <div><h3 className="k-sec">Loading · empty · error</h3>
        <div className="kit-page">
          <Skeleton shape="card" count={1} testid={`kit-${theme}-skel`} />
          <EmptyState title="No games today" testid={`kit-${theme}-empty`} action={<button type="button" className="btn btn--secondary btn--sm">See the next match day</button>}>There are no matches in your leagues on this day.</EmptyState>
          <ErrorState message="We could not load the fixtures." onRetry={() => {}} testid={`kit-${theme}-error`} />
        </div>
      </div>
      <BottomSheet open={sheet} onClose={() => setSheet(false)} title="Live now" testid={`kit-${theme}-sheet`}><LiveCard f={SAMPLE_LIVE} events={SAMPLE_EVENTS} testid={`kit-${theme}-sheet-live`} /></BottomSheet>
      <FilterSheet open={filters} onClose={() => setFilters(false)} onReset={() => setOne(70)} count={24} testid={`kit-${theme}-filters`}>
        <FilterGroup label="Minimum likelihood"><RangeSlider min={50} max={95} value={one} onChange={setOne} label="Minimum likelihood" format={(v) => `${v}%`} testid={`kit-${theme}-f-range`} /></FilterGroup>
        <FilterGroup label="Venue"><Segmented value={seg} onChange={setSeg} label="Venue" options={[{ id: "l5", label: "Home" }, { id: "season", label: "Away" }]} testid={`kit-${theme}-f-seg`} /></FilterGroup>
      </FilterSheet>
    </section>
  );
}

export default function DevKit() {
  useTitle("Component kit");
  return (
    <section className="kit-page" data-testid="dev-kit">
      <meta name="robots" content="noindex" />
      <h1>Component kit</h1>
      <p className="muted">Sample values for the kit only. Real screens read the API.</p>
      <div className="kit-cols"><Panel theme="light" /><Panel theme="dark" /></div>
    </section>
  );
}
