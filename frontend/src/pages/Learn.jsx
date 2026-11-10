// Learn (docs/24 §16): short reads, each with one picture that shows the idea first.
// The pictures are drawn examples, not live numbers. Unknown slugs fall back to the Markdown page.
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import MarkdownPage from "./Markdown";
import { useTitle } from "../components/Football";
import { ChipsRow, TierBadge } from "../components/ui";

// The likelihood is set like the likelihood on a real card: plain text colour (v2.css §3
// `.k-fc-p`). It was green here, which spends `--up` -- the product's word for "above this
// player's usual game" -- on a bare percentage, so the one picture teaching a reader to read a
// card taught them a colour the card does not use.
const PicCard = () => <div className="ln-mini"><span><b>2+ shots</b><b>78%</b></span><i><s style={{ width: "78%" }} /></i></div>;
const PicTiers = () => <div className="ln-tiers"><TierBadge tier="Strong" testid="ln-tier-strong" /><TierBadge tier="Solid" testid="ln-tier-solid" /><TierBadge tier="Watch" testid="ln-tier-watch" /></div>;
const PicLineup = () => <div className="ln-ba"><span><small>Before</small><b className="ln-solid">66%</b></span><span aria-hidden="true">→</span><span><small className="ln-up">Lineup in</small><b className="ln-up">78%</b></span></div>;
const PicScore = () => <svg className="ln-svg" viewBox="0 0 120 80" aria-hidden="true"><line x1="10" y1="70" x2="110" y2="10" /><polyline points="22,62 44,50 64,38 86,25 104,14" /><circle cx="44" cy="50" r="4" /><circle cx="64" cy="38" r="6" /><circle cx="86" cy="25" r="5" /></svg>;

export const ARTICLES = [
  { slug: "forecast-card", cat: "start", tag: "Start here", mins: 2, title: "How to read a forecast card", sub: "The big number, the tier, and the reasons.", Pic: PicCard, body: [
    "Each card is about one player or one team in one match, and one line, for example “2+ shots”.",
    "The big number is our estimate of how likely it is that the line is reached in that match. 78% means that, across many forecasts like this one, we expect it to happen about 78 times in 100.",
    "The badge (\u201cwell above usual\u201d, \u201cabove usual\u201d, \u201cnear usual\u201d) grades how much the forecast has to say \u2014 on a player card, the size of the gap between tonight and their usual game, not the percentage next to it. Tap the card to see the reasons, the last games on that line and the other lines for the same player or team.",
    "A forecast is a reading of the data, not a promise. Football is noisy, and even a high number will not happen every time."] },
  // docs/61: this page described ONE rule -- "Strong is 90% or more" (the old wording; docs/75) -- and the product has run two
  // grading systems since docs/52. Every badge on a player card is graded on the DEPARTURE from that
  // player's usual game, not on the number, so the old text told a reader who came here to check
  // that the screen in front of them could not exist. That is worse than saying nothing.
  { slug: "tiers", cat: "cards", tag: "Reading cards", mins: 2, title: "Well above usual, above usual, near usual", sub: "What the badge is grading.", Pic: PicTiers, body: [
    "The badge grades how much a forecast has to say. It does not grade the percentage beside it, and on a player card it is not about the percentage at all \u2014 which is why a 57% card can read \u201cnear usual\u201d while a 56% one reads \u201cabove usual\u201d. Those two cards are being asked different questions.",
    "The badge used to read Strong, Solid or Watch, and those words were doing harm: \u201cStrong\u201d sounds like a strong chance, so a reader met that 57% card and reasonably concluded something was broken. The grading never changed; the words now name the thing they measure.",
    "On a player or club line set at their own half-way mark, the badge grades the gap between what we expect tonight and what they usually do. Well above usual: a big gap, and the likely range sits clear of their usual. Above usual: a gap worth saying, but the range still reaches their usual. Near usual: a small gap. No badge at all means tonight looks like any other night for them, which is an honest answer and the commonest one.",
    "On every other line the badge grades the number itself: three dots at 90% or more, two at 80% or more, one below that and still worth a card. The card says which kind it is \u2014 a line graded on the gap always prints the gap, as \u201c8 points above his usual 48%\u201d.",
    "So the badge is never a second opinion about the number. Either it is the bar the number cleared, or it is the size of the gap. The card tells you which, and the two are never mixed on one card.",
    "Our own record can pull a tier down and can never raise one. If finished forecasts around that number came true less often than the number claimed, the card is marked down and says so \u2014 \u201cSimilar lines happened 71% of the time\u201d. This applies to lines graded on the number; a line graded on the gap is checked against the record on the Track record page instead.",
    "Whether the player starts is a different question again, with its own answers on the card: the lineup badge says \u201cConfirmed starter\u201d, \u201cLikely lineup\u201d, \u201cLineup not sure\u201d or \u201cOn the bench\u201d, and the minutes under each of his last ten games show you whether he is a regular. The number itself assumes he plays, which the card says too.",
    "A high number is not the same as a forecast worth reading: a line a player clears every week is very likely and tells you nothing. That is the whole reason the badge grades the gap rather than the number \u2014 and why the card does not always lead with the biggest number it holds.",
    "How often each kind came true is not something we claim. It is counted from finished matches and shown on the Track record page."] },
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
      <header className="v2-sec-head"><h2 className="k-sec v2-sec">Read next</h2></header>
      <ul className="ln-grid ln-grid--sm">{more.map((x) => <Tile key={x.slug} a={x} />)}</ul>
    </article>
  );
}
