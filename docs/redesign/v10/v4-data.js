/* ===========================================================================
   THE VERB IS PART OF THE MARKET, NOT PART OF THE CARD.
   ---------------------------------------------------------------------------
   Asked directly: if the reader switches tackles to shots, does "makes" become
   "take"? It has to. "Marcus Linday makes 2+ shots" is not English -- a player
   TAKES shots, MAKES tackles, COMMITS fouls, WINS corners and SCORES goals.
   A sentence that only parses for the market it was written for is worse than
   no sentence, because it breaks exactly when the reader starts exploring.

   Two forms per market, because the subject changes number: a player is
   singular ("Linday makes") and a club is plural in the product's own voice
   ("their usual", "SC Heerenveen take"). That matches STAT_LABEL's existing
   (singular, plural) noun pairs, which is where this belongs -- see the note
   at the bottom of the brief.
   ========================================================================= */
const VERB = {
  tackles:           ['makes',     'make'],
  shots:             ['takes',     'take'],
  sot:               ['has',       'have'],      // "has 2+ shots on target"
  fouls:             ['commits',   'commit'],
  fouls_committed:   ['commits',   'commit'],
  saves:             ['makes',     'make'],
  corners:           ['wins',      'win'],
  goals:             ['scores',    'score'],
  goal_involvements: ['has',       'have'],      // "has 1+ goal or assist"
  yellow:            ['picks up',  'pick up'],
};
// The noun pairs the backend already ships on every market.
const NOUN = {
  tackles:['tackle','tackles'], shots:['shot','shots'], sot:['shot on target','shots on target'],
  fouls:['foul','fouls'], saves:['save','saves'], corners:['corner','corners'],
  goals:['goal','goals'], yellow:['yellow card','yellow cards'],
};
const sentence = (r) => {
  const v = VERB[r.stat][r.scope === 'team' ? 1 : 0];
  const n = NOUN[r.stat][r.n === 1 ? 0 : 1];     // "1+ tackle", "2+ tackles"
  return { v, n };
};

/* Four rows chosen to show the verb doing its job: the SAME player across two
   markets, a third market with a different verb again, and a club, which is
   plural. Switch the market token on any of them and the verb must follow. */
const ROWS4 = [
  { av:'ML', cls:'', name:'Marcus Linday', pos:'MID', scope:'player', fx:'vs Feyenoord', ko:'FT',
    stat:'tackles', n:2, p:64, lo:58, hi:71, tier:'solid', dep:+6, usual:58,
    games:[1,3,2,0,2,1,3,2,1,2], lu:'Starting', luCls:'', res:'done', got:3 },
  { av:'ML', cls:'', name:'Marcus Linday', pos:'MID', scope:'player', fx:'vs Feyenoord', ko:'FT',
    stat:'shots', n:2, p:61, lo:54, hi:68, tier:'watch', dep:+4, usual:57,
    games:[2,1,3,2,1,2,2,0,3,1], lu:'Starting', luCls:'', res:'done', got:1 },
  { av:'TB', cls:'b', name:'Thom van den Berg', pos:'MID', scope:'player', fx:'vs Feyenoord', ko:'FT',
    stat:'fouls', n:1, p:91, lo:86, hi:95, tier:'strong', dep:+26, usual:65,
    games:[1,2,0,1,1,2,1,0,2,1], lu:'Starting', luCls:'', res:null },
  { av:'', cls:'club', name:'SC Heerenveen', pos:'', scope:'team', fx:'vs Feyenoord', ko:'15:00',
    stat:'shots', n:11, p:66, lo:60, hi:72, tier:'watch', dep:+8, usual:58,
    games:[12,9,14,11,10,13,8,11,12,10], lu:'Club line', luCls:'club', res:null },
];
ROWS4.forEach((r) => { r.market = `${r.n}+ ${NOUN[r.stat][r.n === 1 ? 0 : 1]}`; });

const claimTok = (r) => { const { v, n } = sentence(r);
  return `<p class="claim claim--live"><b>${r.name}</b> <em>${v}</em>
    <button class="tok tok--n"><s>−</s><b>${r.n}+</b><s>+</s></button>
    <button class="tok tok--m">${n}${svg.chev}</button></p>`; };
const metaEl4 = (r) => `<span class="av ${r.cls}">${r.av || '◈'}</span>
  ${r.pos ? `<span class="pos">${r.pos}</span>` : ''}<span class="fx">${r.fx} · ${r.ko}</span>`;
