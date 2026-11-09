// Match events timeline (docs/23): goals, cards, substitutions from SportAPI, sorted by minute.
// Home events on the left, away on the right. Text labels as well as symbols, so colour never carries meaning alone.
import { EmptyState } from "./ui";
import { PlayerAvatar } from "./Media";

const KIND = {
  goal: { cls: "goal", label: "Goal" },
  own_goal: { cls: "goal", label: "Own goal" },
  penalty: { cls: "goal", label: "Penalty goal" },
  missed_penalty: { cls: "miss", label: "Penalty missed" },
  yellow_card: { cls: "yellow", label: "Yellow card" },
  red_card: { cls: "red", label: "Red card" },
  second_yellow: { cls: "red", label: "Second yellow" },
  substitution: { cls: "sub", label: "Substitution" },
};

export default function MatchEvents({ events = [], testid = "live-events" }) {
  if (!events.length) return <EmptyState icon="activity" title="No events yet" testid={`${testid}-empty`} />;
  return (
    <ol className="lev-list" aria-label="Match events" data-testid={testid}>
      {events.map((e, i) => {
        const k = KIND[e.type] || { cls: "other", label: (e.type || "Event").replace(/_/g, " ") };
        return (
          <li key={i} className={`lev lev--${e.side || "none"}`} data-testid={`${testid}-${i}`}>
            <span className="lev-min">{e.minute}</span>
            <span className={`lev-ico lev-ico--${k.cls}`} aria-hidden="true" />
            {/* The player an event is about wears the same round face he wears in every other list.
                The feed carries no id and no picture for him (sportapi.events_for), so the avatar
                falls back to his initials -- the shared fallback, not a hand-rolled one. His name is
                the tint key, so two players in one timeline do not come out the same colour. */}
            <span className="lev-txt"><b className="lev-who">{e.player_name && <PlayerAvatar player={{ id: e.player_name, name: e.player_name }} size={18} />}{e.player_name || ""}</b><small>{k.label}{e.extra && e.extra !== k.label ? ` · ${e.extra}` : ""}</small></span>
          </li>
        );
      })}
    </ol>
  );
}
