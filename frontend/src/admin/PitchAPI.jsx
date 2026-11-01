// Admin > Football data > PitchAPI (docs/43): everything that talks to PitchAPI, in one screen.
// Its three tabs were three separate menu entries (Cache and usage, Data quality, Endpoint explorer), which left
// the owner hunting for the provider's controls in three places. The tab is in the URL, so links and Back work.
import { useNavigate, useParams } from "react-router-dom";
import { Tabs } from "../components/Ui";
import { PageHead } from "./parts";
import Cache from "./Cache";
import Quality from "./Quality";
import Explorer from "./Explorer";

const TABS = [{ id: "usage", label: "Usage and cache" }, { id: "quality", label: "Quality and mapping" }, { id: "explorer", label: "Endpoint explorer" }];

export default function PitchAPI() {
  const { tab } = useParams();
  const nav = useNavigate();
  const pick = TABS.some((t) => t.id === tab) ? tab : "usage";
  const Body = { usage: Cache, quality: Quality, explorer: Explorer }[pick];
  return (
    <div className="a-page" data-testid="admin-pitchapi">
      <PageHead title="PitchAPI" lead="History, season backfill and the depth analytics the forecasts are built from. Live scores and events come from SportAPI." />
      <Tabs tabs={TABS} value={pick} onChange={(t) => nav(`/admin/data/pitchapi/${t}`)} testid="pitchapi-tabs" />
      <Body head={false} />
    </div>
  );
}
