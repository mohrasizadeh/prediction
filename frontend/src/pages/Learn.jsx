// Learn (docs/24 §16): short reads, each with one picture that shows the idea first.
// The pictures are drawn examples, not live numbers. Unknown slugs fall back to the Markdown page.
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import MarkdownPage from "./Markdown";
import { useTitle } from "../components/Football";
import { ChipsRow, TierBadge } from "../components/ui";

const PicCard = () => <div className="ln-mini"><span><b>2+ shots</b><b className="ln-up">78%</b></span><i><s style={{ width: "78%" }} /></i></div>;
const PicTiers = () => <div className="ln-tiers"><TierBadge tier="Strong" testid="ln-tier-strong" /><TierBadge tier="Solid" testid="ln-tier-solid" /><TierBadge tier="Watch" testid="ln-tier-watch" /></div>;
const PicLineup = () => <div className="ln-ba"><span><small>Before</small><b className="ln-solid">66%</b></span><span aria-hidden="true">→</span><span><small className="ln-up">Lineup in</small><b className="ln-up">78%</b></span></div>;
const PicScore = () => <svg className="ln-svg" viewBox="0 0 120 80" aria-hidden="true"><line x1="10" y1="70" x2="110" y2="10" /><polyline points="22,62 44,50 64,38 86,25 104,14" /><circle cx="44" cy="50" r="4" /><circle cx="64" cy="38" r="6" /><circle cx="86" cy="25" r="5" /></svg>;

export const ARTICLES = [
  { slug: "forecast-card", cat: "start", tag: "Start here", mins: 2, title: "How to read a forecast card", sub: "The big number, the tier, and the reasons.", Pic: PicCard, body: [
    "Each card is about one player or one team in one match, and one line, for example “2+ shots”.",
    "The big number is our estimate of how likely it is that the line is reached in that match. 78% means that, across many forecasts like this one, we expect it to happen about 78 times in 100.",
    "The tier badge (Strong, Solid or Watch) tells you how much the evidence behind the number agrees. Tap the card to see the reasons, the last games on that line and the other lines for the same player or team.",
    "A forecast is a reading of the data, not a promise. Football is noisy, and even a high number will not happen every time."] },
  { slug: "tiers", cat: "cards", tag: "Reading cards", mins: 2, title: "Strong, Solid and Watch", sub: "What each tier means, and how often it comes true.", Pic: PicTiers, body: [
    "Strong: the number is high and the signals behind it point the same way.",
    "Solid: a good reading with a little more doubt, for example a shorter run of games or a question over who starts.",
    "Watch: worth keeping an eye on, but the evidence is thinner.",
    "How often each tier came true is not something we claim. It is counted from finished matches and shown on the Track record page."] },
  { slug: "lineups", cat: "method", tag: "Our method", mins: 3, title: "Why lineups change the numbers", sub: "Who plays changes everything.", Pic: PicLineup, body: [
    "A player can only reach a line if he plays, so every player forecast carries a “chance he plays”.",
    "Before the teams are announced we estimate that chance from recent starts, minutes, injuries and how busy the schedule is.",
    "When the lineup is confirmed, that doubt goes away. A starter's numbers usually rise, and a player left on the bench drops out.",
    "Cards marked “Lineup confirmed” already use the announced teams."] },
  { slug: "how-we-score", cat: "method", tag: "Our method", mins: 2, title: "How we score our forecasts", sub: "Every finished forecast is checked against what happened.", Pic: PicScore, body: [
    "After each match we compare every forecast with the final numbers: did the player have 2+ shots, did the team reach the corner line?",
    "We then group forecasts by what we said, for example all the ones near 70%, and count how often they happened. If the 70% group happened about 70% of the time, the numbers are honest.",
    "The Track record page shows that chart, how often each tier came true, and filters by league and market. It only appears once enough forecasts have been scored to mean something.",
    "Players who did not play are left out, because the forecast was never tested."] },
];
const CATS = [{ id: "", label: "All" }, { id: "start", label: "Start here" }, { id: "cards", label: "Reading cards" }, { id: "method", label: "Our method" }];

function Tile({ a }) {
  return (
    <li><Link to={`/learn/${a.slug}`} className="ln-tile card" data-testid={`learn-tile-${a.slug}`}>
      <span className="ln-pic"><a.Pic /></span>
      <span className="ln-txt"><small className="k-sec">{a.mins} min · {a.tag}</small><b>{a.title}</b><span className="k-faint">{a.sub}</span></span>
    </Link></li>
  );
}

export function Learn() {
  const [cat, setCat] = useState("");
  useTitle("Learn");
  return (
    <section className="ln" data-testid="learn-page">
      <div className="ln-head"><div><h1>Learn</h1><p className="k-faint">Two-minute reads. One picture each.</p></div>
        <ChipsRow label="Topic" value={cat} onChange={setCat} options={CATS} testid="learn-cats" /></div>
      <ul className="ln-grid" data-testid="learn-list">{ARTICLES.filter((a) => !cat || a.cat === cat).map((a) => <Tile key={a.slug} a={a} />)}</ul>
    </section>
  );
}

export function LearnArticle() {
  const { slug } = useParams();
  const a = ARTICLES.find((x) => x.slug === slug);
  useTitle(a?.title || "Learn");
  if (!a) return <MarkdownPage />;
  const more = ARTICLES.filter((x) => x.slug !== slug).slice(0, 3);
  return (
    <article className="ln-art" data-testid={`learn-article-${slug}`}>
      <Link to="/learn" className="k-link" data-testid="learn-back">← Learn</Link>
      <div className="ln-pic ln-pic--big card"><a.Pic /></div>
      <small className="k-sec">{a.mins} min · {a.tag}</small>
      <h1>{a.title}</h1>
      {a.body.map((p) => <p key={p}>{p}</p>)}
      {slug === "how-we-score" && <Link to="/track-record" className="btn btn--secondary" data-testid="learn-to-track">See the track record</Link>}
      <h2 className="k-sec">Read next</h2>
      <ul className="ln-grid ln-grid--sm">{more.map((x) => <Tile key={x.slug} a={x} />)}</ul>
    </article>
  );
}
