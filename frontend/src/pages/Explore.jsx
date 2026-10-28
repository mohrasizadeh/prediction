// Explore (docs/24 §6): everything people browse, in one place. Phase R5 restyles it; the league list is the
// existing Leagues screen.
import { Link } from "react-router-dom";
import Icon from "../components/Icon";
import { Leagues } from "./League";
import { useTitle } from "../components/Football";

const TILES = [
  { to: "/compare", icon: "users", label: "Compare", sub: "Two clubs side by side" },
  { to: "/live", icon: "clock", label: "Live scores", sub: "Every match today" },
  { to: "/referees", icon: "flag", label: "Referees", sub: "Cards and penalties" },
  { to: "/track-record", icon: "trending-up", label: "Track record", sub: "How our forecasts did" },
  { to: "/learn", icon: "book", label: "Learn", sub: "How to read a forecast" },
  { to: "/pricing", icon: "credit-card", label: "Plans", sub: "Free and Pro" },
];

export default function Explore() {
  useTitle("Explore");
  return (
    <section className="ex" data-testid="explore-page">
      <h1>Explore</h1>
      <ul className="ex-tiles">{TILES.map((t) => (
        <li key={t.to}><Link to={t.to} className="ex-tile" data-testid={`explore-${t.to.slice(1)}`}><span className="ex-ico"><Icon name={t.icon} size={20} /></span><span><b>{t.label}</b><small>{t.sub}</small></span></Link></li>
      ))}</ul>
      <Leagues />
    </section>
  );
}
