// What the new encodings need on top of the shared ROWS: the ladder's other rungs, and the
// claim written as the sentence the product actually makes.
const EXTRA = {
  'Marcus Linday':   { noun:'tackles', verb:'makes', lad:[[1,94],[2,64],[3,26]], claim:'<b>Marcus Linday</b> <em>makes</em> <b>2 or more tackles</b>' },
  'Thom van den Berg':{ noun:'tackles', verb:'makes', lad:[[1,99],[2,91],[3,58]], claim:'<b>Thom van den Berg</b> <em>makes</em> <b>2 or more tackles</b>' },
  'SC Heerenveen':   { noun:'shots', verb:'take', lad:[[10,81],[11,66],[12,44]], claim:'<b>SC Heerenveen</b> <em>take</em> <b>11 or more shots</b>' },
};

// The grade thresholds, drawn on the meter's track so a reader can see how close a line came
// to being a better grade. Same numbers as engine.watch_min / solid_min / strong_min.
const TICKS = [[60, 'Watch'], [80, 'Solid'], [90, 'Strong']];

function meter(r) {
  const ticks = TICKS.map(([v, w]) =>
    `<span class="tick" style="left:${v}%"><s>${w}</s></span>`).join('');
  return `<span class="meterwrap">
    <span class="meterlbl"><b class="num">${r.p}%</b><span class="lbl"> likely</span><span class="rg num">range ${r.lo}–${r.hi}%</span></span>
    <span class="meter" role="img" aria-label="${r.p} per cent, likely range ${r.lo} to ${r.hi} per cent">
      <span class="fillbar" style="width:${r.p}%"></span>
      <span class="band" style="left:${r.lo}%;width:${r.hi - r.lo}%"></span>
      ${ticks}<span class="pt" style="left:${r.p}%"></span>
    </span>
    <span class="mlegend">Watch <b>60</b> · Solid <b>80</b> · Strong <b>90</b></span></span>`;
}

function ladder(r) {
  const e = EXTRA[r.name];
  return `<span class="lwrap"><span class="lcap">The line · tap to change</span>
    <span class="lad">${e.lad.map(([n, p]) =>
      `<button class="${n === r.n ? 'on' : (p > 92 ? 'off' : '')}"><s>${n}+</s><b class="num">${p}%</b></button>`).join('')}
    </span></span>`;
}
const railEl = (r) => `<span class="rail ${r.tier}"></span>`;
const wordEl = (r) => `<span class="tierword ${r.tier}">${{strong:'Strong',solid:'Solid',watch:'Watch'}[r.tier]}</span>`;
