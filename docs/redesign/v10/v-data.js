// The same three rows in every variant, so the comparison is about layout and nothing else.
// A settled hit, a settled miss on a near-certain line, and a club line still to play.
const ROWS = [
  { av:'ML', cls:'', name:'Marcus Linday', pos:'MID', fx:'vs Feyenoord', ko:'FT',
    market:'2+ tackles', n:2, p:64, lo:58, hi:71, tier:'solid', dep:+6, usual:58,
    games:[1,3,2,0,2,1,3,2,1,2], lu:'Starting', luCls:'', res:'Happened — 3', resNo:false },
  { av:'TB', cls:'b', name:'Thom van den Berg', pos:'MID', fx:'vs Feyenoord', ko:'FT',
    market:'2+ tackles', n:2, p:91, lo:86, hi:95, tier:'strong', dep:+33, usual:58,
    games:[3,2,4,2,3,2,2,3,2,4], lu:'Starting', luCls:'', res:'Did not happen — 0', resNo:true },
  { av:'', cls:'club', name:'SC Heerenveen', pos:'', fx:'vs Feyenoord', ko:'15:00',
    market:'11+ shots', n:11, p:66, lo:60, hi:72, tier:'watch', dep:+8, usual:58,
    games:[12,9,14,11,10,13,8,11,12,10], lu:'Club line', luCls:'club', res:null, resNo:false },
];

const RH = 28;
const svg = {
  chev:'<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9l6 6 6-6"/></svg>',
  star:'<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2l3.1 6.3 6.9 1-5 4.9 1.2 6.8L12 17.8 5.8 21l1.2-6.8-5-4.9 6.9-1z"/></svg>',
  plus:'<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>',
  chevd:'<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9l6 6 6-6"/></svg>',
};

// The strip. The scale is PER ROW: `mx` is this row's own ceiling, so a bar's height says
// "how big for him", not "how big against everyone". That makes the bar-vs-line comparison
// inside a row exact and the height comparison BETWEEN rows meaningless -- see the note in
// the brief. Every variant draws it identically so the choice can be judged on its own.
function strip(g, n, h = RH) {
  const mx = Math.max(n, ...g);
  const y = Math.max(1, Math.round((n / mx) * h));
  const cleared = g.filter((v) => v >= n).length;
  const bars = g.map((v) => {
    const bh = Math.max(2, Math.round((v / mx) * h));
    const hit = v >= n;
    const fill = hit
      ? `linear-gradient(to top, var(--brand) 0 ${Math.min(bh, y)}px, var(--tier-strong) ${Math.min(bh, y)}px 100%)`
      : 'var(--lk-rule)';
    return `<i style="height:${bh}px;background:${fill}"></i>`;
  }).join('');
  return { y, cleared, html:
    `<span class="runbox"><span class="need" style="bottom:${y - 1}px">${n}</span>
      <span class="run" style="height:${h}px"><span class="rule" style="bottom:${y}px"></span>${bars}</span></span>` };
}

const tierEl = (t) => {
  if (!t) return '';
  const n = { strong:3, solid:2, watch:1 }[t];
  const w = { strong:'Strong', solid:'Solid', watch:'Watch' }[t];
  const dots = [1,2,3].map((i) => `<s class="${i <= n ? 'on' : ''}"></s>`).join('');
  return `<span class="tier ${t}"><i>${dots}</i>${w}</span>`;
};
const figEl = (p) => `<span class="fig num">${p}<u>%</u></span>`;
const rgEl = (r) => `<span class="rg num">${r.lo}–${r.hi}%</span>`;
const depEl = (r) => `<span class="dep ${r.dep >= 0 ? 'up' : 'dn'}"><i>${r.dep >= 0 ? '▲' : '▼'}</i><b>${Math.abs(r.dep)} pts</b>
  <em>vs usual ${r.usual}%</em></span>`;
const mktEl = (r) => `<button class="mkt">${r.market}${svg.chev}</button>`;
const stepEl = (r) => `<span class="step"><button>−</button><b class="num">${r.n}+</b><button>+</button></span>`;
const luEl = (r) => `<span class="lu ${r.luCls}"><s></s>${r.lu}</span>`;
const resEl = (r) => r.res ? `<span class="res ${r.resNo ? 'no' : ''}">${r.resNo ? '' : '✓ '}${r.res}</span>` : '';
const actsEl = () => `<span class="acts"><button class="why">Why${svg.chevd}</button>
  <button class="ico">${svg.star}</button><button class="ico">${svg.plus}</button></span>`;
const whoEl = (r) => `<span class="av ${r.cls}">${r.av || '◈'}</span>
  <span class="nm">${r.name}</span>${r.pos ? `<span class="pos">${r.pos}</span>` : ''}`;
