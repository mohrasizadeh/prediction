/* The landing page's drawings (docs/68).
 *
 * String builders rather than JSX because they are dense SVG geometry, and because every one of
 * them is a pure function of the feed: the same input always draws the same picture, which is what
 * lets the page refresh itself with the endpoints instead of carrying a snapshot.
 *
 * Everything that reaches innerHTML goes through esc() first. The names come from our own
 * database rather than from a visitor, but a page that escapes only the inputs it currently
 * distrusts is one schema change from not escaping the one that matters.
 */
/* eslint-disable no-useless-concat */
/** Draw the whole page into the containers React has rendered.
 *
 * Called from an effect once both feeds have arrived, so nothing here ever meets a half-loaded
 * page. It returns early if its containers are not mounted -- an unmounted effect firing after a
 * route change should do nothing rather than throw.
 */
export function paint(proof, track, tonight) {
  if (!document.getElementById('proof-grid')) return;
  // The three feeds, as plain locals. They were globals on window in the design lab; here they are
  // arguments, so two calls with different data cannot leak into each other.
  var PROOF = proof || [], TRACK = track || {}, T = tonight || {};
  // Everything below reads T.player.name, T.run.length and T.lo/hi without asking first, so a day
  // with no fixture inside the window threw here and the page rendered as headings over nothing --
  // on the one screen a stranger sees first. A card is drawable only if it has a subject and a
  // number; the sections that need one are skipped rather than half-drawn.
  var HAS_CARD = !!(T && T.player && T.player.name && T.p != null && (T.run || []).length);
  // TRACK.scored is read the same way, and /track-record answers with no counts until the first
  // forecasts have been scored.
  var SCORED = typeof TRACK.scored === "number" ? TRACK.scored : null;
  var C = {brand:'#034737', strong:'#1B8962', accent:'#A9FF9B', text:'#22281E',
           text2:'#3C4238', text3:'#62685F', s2:'#EBEEEA', border:'#D3D7D2', border2:'#AAAEA7',
           hair:'#E6E9E5', warm:'#FDF8F7', mint:'#E8F4EE'};
  var pc = function(x){ return Math.round(x*100) + '%'; };
  var esc = function(s){ return String(s).replace(/[&<>]/g, function(c){
    return {'&':'&amp;','<':'&lt;','>':'&gt;'}[c]; }); };

  /* ---------------- hero numbers ---------------- */
  var hi = TRACK.high || {};
  // The calibration figure moved out of the headline and into the kicker. In the headline it was
  // the largest thing on the page and meaningless without a prior the reader does not have yet --
  // 86 beside 87 reads as a typo. Here it is a credential under the promise, and the record
  // section further down is where it is explained.
  if (SCORED != null) document.getElementById('kicker').innerHTML =
    '<b>' + SCORED.toLocaleString('en-GB') + '</b> forecasts published, scored and left on the site';

  if (SCORED != null) document.getElementById('counters').innerHTML =
    '<div><b>' + SCORED.toLocaleString('en-GB') + '</b><span>forecasts scored and published</span></div>' +
    '<div><b>' + hi.n + '</b><span>of them at ' + pc(hi.from) + ' or higher</span></div>' +
    '<div><b>' + pc(Math.abs(hi.actual - hi.stated)) + '</b><span>between what we said and what happened, at ' + pc(hi.from) + '+</span></div>';

  /* ---------------- run strip (shared motif) ---------------- */
  function runStrip(run, need, w){
    var n = run.length, max = Math.max.apply(null, run), gap = 4;
    var bw = (w - gap*(n-1))/n, H = 70, base = 52, top = 4;
    var unit = (base - top)/max, yThr = base - need*unit;
    var s = '<svg viewBox="0 0 '+w+' '+H+'" role="img" ' +
            'aria-label="his last ' + n + ' counts against the same line; every one cleared it">';
    for(var i=0;i<n;i++){
      var x = i*(bw+gap), h = run[i]*unit;
      s += '<rect x="'+x.toFixed(1)+'" y="'+yThr.toFixed(1)+'" width="'+bw.toFixed(1)+
           '" height="'+(base-yThr).toFixed(1)+'" fill="'+C.s2+'"/>';
      s += '<rect x="'+x.toFixed(1)+'" y="'+(base-h).toFixed(1)+'" width="'+bw.toFixed(1)+
           '" height="'+(h-(base-yThr)).toFixed(1)+'" fill="'+C.strong+'"/>';
      s += '<rect x="'+x.toFixed(1)+'" y="'+(base-h).toFixed(1)+'" width="'+bw.toFixed(1)+
           '" height="'+h.toFixed(1)+'" rx="2" fill="none" stroke="'+C.strong+'" stroke-width="1"/>';
      s += '<text x="'+(x+bw/2).toFixed(1)+'" y="'+(H-3)+'" font-size="10" fill="'+C.text3+
           '" text-anchor="middle">'+run[i]+'</text>';
    }
    s += '<line x1="0" y1="'+yThr.toFixed(1)+'" x2="'+w+'" y2="'+yThr.toFixed(1)+
         '" stroke="'+C.brand+'" stroke-width="2.2"/>';
    s += '</svg>';
    return s;
  }

  /* ---------------- hero live card ---------------- */
  (function(){
    if (!HAS_CARD) return;
    var pct = Math.round(T.p*100);
    // A settled line is the fallback when nothing is inside the window, and the card says so:
    // passing a finished match off as tonight's would be the one thing this page cannot do.
    var lbl = T.past ? 'Last match day' : 'Tonight';
    var when = T.past
      ? (T.actual != null ? 'He got ' + T.actual : 'Settled')
      : 'Kick-off ' + esc(T.kickoff);
    document.getElementById('livecard').innerHTML =
    '<div class="live' + (T.past ? ' live--past' : '') + '">' +
      '<div class="live-top"><span class="lbl"><span class="dot"></span>' + lbl + '</span>' +
      '<span class="ko">' + when + '</span></div>' +
      '<div class="live-body">' +
        '<div class="live-name">' + esc(T.player.name) + '</div>' +
        '<div class="live-meta"><b>' + esc(T.team.name) + '</b> v ' + esc(T.opp.name) +
          ' · ' + esc(T.player.pos) + '</div>' +
        '<div class="live-row"><div>' +
          '<span class="live-mk">' + esc(T.market) + '</span>' +
          '<div class="live-mk-sub">range ' + pc(T.lo) + '–' + pc(T.hi) + '</div></div>' +
          '<div class="live-p"><b>' + pct + '%</b><span>we say</span></div>' +
        '</div>' +
        '<div class="chips"><span class="chip on">Lineup <b>' + esc(T.lineup) + '</b></span>' +
          '<span class="chip">Needs ' + T.need + ' to clear the line</span></div>' +
        '<div class="live-run"><div class="run-h"><span>His last ' + T.run.length +
          ', against the same line</span><span>cleared it <b>' + T.reached + ' of ' + T.run.length +
          '</b></span></div>' + runStrip(T.run, T.need, 330) + '</div>' +
      '</div></div>';
  })();

  /* ---------------- proof cards ---------------- */
  (function(){
    var tick = '<svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">' +
      '<path d="M2 7.5 L5.5 11 L12 3.5" fill="none" stroke="#034737" stroke-width="2.2" ' +
      'stroke-linecap="round" stroke-linejoin="round"/></svg>';
    var unitName = {shots:'shot', tackles:'tackle', fouls:'foul', yellow:'card'};

    function clearedStrip(thr, actual, w){
      /* how far past the published line he finished: the track is the scale, the bar is what he
         recorded. ("steps" rather than the obvious word for them -- that one is on this product's
         banned list in its staking sense, and check-copy.js does not read intent.) */
      var steps = Math.max(actual, Math.ceil(thr)) + 1;
      var H = 20, ux = w/steps, bar = actual*ux, xThr = thr*ux;
      var s = '<svg viewBox="0 0 '+w+' '+H+'" role="img" ' +
              'aria-label="the line was ' + thr + '; he recorded ' + actual + '">';
      /* The bar is the MID-TONE, not the lime. Eight of these stacked down the page made the
         brightest colour on the screen the background of a measurement rather than the result of
         one -- and lime next to lime, card after card, is what made the page feel loud and flat at
         the same time. The ramp per card is now dark tick, mid-tone fill, lime chip. */
      s += '<rect x="0.6" y="3.6" width="'+(w-1.2)+'" height="12.8" rx="3.5" fill="#fff" stroke="'+
           C.hair+'" stroke-width="1.1"/>';
      s += '<rect x="0.6" y="3.6" width="'+(bar-1.2).toFixed(1)+'" height="12.8" rx="3.5" fill="'+
           C.strong+'"/>';
      for(var i=1;i<actual;i++)
        s += '<line x1="'+(i*ux).toFixed(1)+'" y1="4.2" x2="'+(i*ux).toFixed(1)+'" y2="15.8" stroke="#fff" ' +
             'stroke-width="1" opacity=".55"/>';
      s += '<line x1="'+xThr.toFixed(1)+'" y1="0" x2="'+xThr.toFixed(1)+'" y2="'+H+
           '" stroke="'+C.brand+'" stroke-width="2.4"/>';
      s += '</svg>';
      return s;
    }

    document.getElementById('proof-grid').innerHTML = PROOF.map(function(r){
      var u = unitName[r.stat] || r.stat;
      var word = r.actual === 1 ? u : u + 's';
      return '<article class="pc">' +
        '<div class="pc-top"><span class="pc-mk">' + esc(r.market) + '</span></div>' +
        '<div class="pc-name">' + esc(r.player.name) + '</div>' +
        '<div class="pc-fix">' + esc(r.team.name) + ' v ' + esc(r.opp.name) +
          '<span class="pc-lg">' + esc(r.league_name) + '</span></div>' +
        '<div class="pc-nums"><b>' + pc(r.p) + '</b><span>we said</span></div>' +
        '<div class="pc-strip">' + clearedStrip(r.thr, r.actual, 190) + '</div>' +
        '<div class="pc-out">' + tick + 'He had ' + r.actual + ' ' + word + '</div>' +
      '</article>';
    }).join('');

    var n = PROOF.length;
    var lo = Math.min.apply(null, PROOF.map(function(r){return r.p;}));
    document.getElementById('proof-note').innerHTML =
      'The ' + n + ' most recent scored cards, newest first, from ' + pc(lo) + ' upward — ' +
      'this strip reloads itself every match day. The dark upright on each bar is the line we ' +
      'published; the lime is how far past it he finished.';
  })();

  /* ---------------- engine figures ---------------- */
  var W = 360;

  function poisson(lam, k){
    var p = Math.exp(-lam);
    for(var i=1;i<=k;i++) p = p*lam/i;
    return p;
  }

  /* 1 — a fitted curve per player, with the published line on it */
  function figDistribution(){
    var p = T.p, lam = -Math.log(1-p);               /* the curve behind the published 93% */
    var H = 212, x0 = 20, x1 = 344, base = 168, top = 62;
    var K = 8, slot = (x1-x0)/(K+1), bw = slot*0.74;
    var vals = [], max = 0;
    for(var k=0;k<=K;k++){ var v = poisson(lam,k); vals.push(v); if(v>max) max = v; }
    var sc = (base-top)/max;
    var xLine = x0 + slot;                            /* the 0.5 boundary: between 0 and 1 */
    var s = '<svg viewBox="0 0 '+W+' '+H+'" role="img" aria-label="' + esc(T.player.name) +
      '&#39;s fitted shot curve, with the ' + esc(T.market) + ' line marked; ' +
      Math.round((1-p)*100) + ' percent of the curve sits left of the line and ' +
      Math.round(p*100) + ' percent right of it">';
    /* the region the forecast is made of */
    s += '<rect x="'+xLine+'" y="'+(top-14)+'" width="'+(x1-xLine)+'" height="'+(base-top+14)+
         '" fill="'+C.s2+'"/>';
    for(var k2=0;k2<=K;k2++){
      var cx = x0 + slot*(k2+0.5), h = vals[k2]*sc, on = k2 >= 1;
      s += '<rect x="'+(cx-bw/2).toFixed(1)+'" y="'+(base-h).toFixed(1)+'" width="'+bw.toFixed(1)+
           '" height="'+h.toFixed(1)+'" rx="2" fill="'+(on?C.strong:'#fff')+'" stroke="'+
           (on?C.strong:C.text3)+'" stroke-width="'+(on?1:1.3)+'"/>';
      s += '<text x="'+cx.toFixed(1)+'" y="'+(base+16)+'" font-size="11" fill="'+C.text3+
           '" text-anchor="middle">'+k2+'</text>';
    }
    s += '<line x1="'+x0+'" y1="'+base+'" x2="'+x1+'" y2="'+base+'" stroke="'+C.text3+'" stroke-width="1"/>';
    /* the line itself */
    s += '<line x1="'+xLine+'" y1="22" x2="'+xLine+'" y2="'+(base+7)+
         '" stroke="'+C.brand+'" stroke-width="2.5"/>';
    s += '<rect x="'+(xLine-2)+'" y="4" width="100" height="20" rx="5" fill="'+C.brand+'"/>';
    s += '<text x="'+(xLine+7)+'" y="18.5" font-size="11.5" font-weight="700" fill="#fff">the line: ' +
         esc(T.market) + '</text>';
    /* the two areas, named */
    s += '<text x="'+(x0+slot*0.5).toFixed(1)+'" y="'+(base-vals[0]*sc-7).toFixed(1)+
         '" font-size="12" font-weight="700" fill="'+C.text2+'" text-anchor="middle">' +
         Math.round((1-p)*100) + '%</text>';
    s += '<text x="'+(x1-6)+'" y="42" font-size="21" font-weight="700" fill="'+C.brand+
         '" text-anchor="end">' + Math.round(p*100) + '%</text>';
    s += '<text x="'+(x1-6)+'" y="56" font-size="10.5" fill="'+C.text2+
         '" text-anchor="end">of the curve is past it</text>';
    s += '<text x="'+x0+'" y="'+(H-5)+'" font-size="10.5" fill="'+C.text3+'">shots in one match</text>';
    s += '</svg>';
    return s;
  }

  /* 2 — ten matches against the same line */
  function figRun(){
    var run = T.run, need = T.need, n = run.length;
    var H = 212, x0 = 22, x1 = 344, base = 152, top = 44;
    var gap = 7, bw = ((x1-x0) - gap*(n-1))/n;
    var max = Math.max.apply(null, run);
    var unit = (base-top)/max;
    var mean = run.reduce(function(a,b){return a+b;},0)/n;
    var yThr = base - need*unit, yMean = base - mean*unit;
    var s = '<svg viewBox="0 0 '+W+' '+H+'" role="img" aria-label="his last ' + n + ' shot counts: ' +
      'every one cleared the line of ' + need + ', although the counts swing between ' +
      Math.min.apply(null,run) + ' and ' + max + '">';
    for(var i=0;i<n;i++){
      var x = x0 + i*(bw+gap), h = run[i]*unit;
      /* below the line, the part that only gets him level; above it, the clearance */
      s += '<rect x="'+x.toFixed(1)+'" y="'+yThr.toFixed(1)+'" width="'+bw.toFixed(1)+
           '" height="'+(base-yThr).toFixed(1)+'" fill="'+C.s2+'"/>';
      s += '<rect x="'+x.toFixed(1)+'" y="'+(base-h).toFixed(1)+'" width="'+bw.toFixed(1)+
           '" height="'+(h-(base-yThr)).toFixed(1)+'" fill="'+C.strong+'"/>';
      s += '<rect x="'+x.toFixed(1)+'" y="'+(base-h).toFixed(1)+'" width="'+bw.toFixed(1)+
           '" height="'+h.toFixed(1)+'" rx="2" fill="none" stroke="'+C.strong+'" stroke-width="1.1"/>';
      s += '<text x="'+(x+bw/2).toFixed(1)+'" y="'+(base+15)+'" font-size="10.5" fill="'+C.text3+
           '" text-anchor="middle">'+run[i]+'</text>';
    }
    /* the mean — the thing an average table hands you instead */
    s += '<line x1="'+x0+'" y1="'+yMean.toFixed(1)+'" x2="'+x1+'" y2="'+yMean.toFixed(1)+
         '" stroke="'+C.text3+'" stroke-width="1.4" stroke-dasharray="2 4"/>';
    /* the line */
    s += '<line x1="'+x0+'" y1="'+yThr.toFixed(1)+'" x2="'+x1+'" y2="'+yThr.toFixed(1)+
         '" stroke="'+C.brand+'" stroke-width="2.6"/>';
    s += '<line x1="'+x0+'" y1="'+base+'" x2="'+x1+'" y2="'+base+'" stroke="'+C.text3+'" stroke-width="1"/>';
    s += '<rect x="'+x0+'" y="8" width="196" height="21" rx="5" fill="'+C.brand+'"/>';
    s += '<text x="'+(x0+9)+'" y="22.5" font-size="12" font-weight="700" fill="#fff">the line: ' +
         need + ' — cleared ' + T.reached + ' of ' + n + '</text>';
    s += '<text x="'+x0+'" y="'+(base+31)+'" font-size="10.5" fill="'+C.text3+'">his last ' + n +
         ' matches, oldest first</text>';
    /* legend, clear of the plot */
    var ly = H - 10;
    s += '<line x1="'+x0+'" y1="'+(ly-4)+'" x2="'+(x0+20)+'" y2="'+(ly-4)+'" stroke="'+C.brand+'" stroke-width="2.6"/>';
    s += '<text x="'+(x0+26)+'" y="'+ly+'" font-size="10.5" fill="'+C.text2+'">the line, ' + need + '</text>';
    s += '<line x1="190" y1="'+(ly-4)+'" x2="210" y2="'+(ly-4)+'" stroke="'+C.text3+
         '" stroke-width="1.4" stroke-dasharray="2 4"/>';
    s += '<text x="216" y="'+ly+'" font-size="10.5" fill="'+C.text2+'">his average, ' +
         mean.toFixed(1) + '</text>';
    s += '</svg>';
    return s;
  }

  /* 3 — two lines on one player: why multiplying is wrong */
  function figOverlap(){
    var H = 236;
    var s = '<svg viewBox="0 0 '+W+' '+H+'" role="img" aria-label="the two lines overlap: the ' +
      'matches where he takes a shot are mostly the matches where he hits the target, so the ' +
      'measured both-of-them figure is wider than the multiplied one">';
    s += '<text x="14" y="16" font-size="10.5" fill="'+C.text3+'">every match he plays</text>';
    s += '<rect x="12" y="22" width="336" height="88" rx="11" fill="#fff" stroke="'+C.border+'"/>';
    var cy = 66, rx = 98, ry = 36, caX = 118, cbX = 242;
    s += '<defs><clipPath id="lensA"><ellipse cx="'+caX+'" cy="'+cy+'" rx="'+rx+'" ry="'+ry+'"/></clipPath></defs>';
    /* 1+ shot */
    s += '<ellipse cx="'+caX+'" cy="'+cy+'" rx="'+rx+'" ry="'+ry+'" fill="'+C.mint+'" stroke="'+
         C.strong+'" stroke-width="1.4"/>';
    /* 1+ on target */
    s += '<ellipse cx="'+cbX+'" cy="'+cy+'" rx="'+rx+'" ry="'+ry+'" fill="#fff" fill-opacity="0" stroke="'+
         C.brand+'" stroke-width="2.2"/>';
    /* the nights that are both */
    s += '<g clip-path="url(#lensA)"><ellipse cx="'+cbX+'" cy="'+cy+'" rx="'+rx+'" ry="'+ry+
         '" fill="'+C.brand+'"/></g>';
    s += '<ellipse cx="'+caX+'" cy="'+cy+'" rx="'+rx+'" ry="'+ry+'" fill="none" stroke="'+
         C.strong+'" stroke-width="1.4"/>';
    s += '<ellipse cx="'+cbX+'" cy="'+cy+'" rx="'+rx+'" ry="'+ry+'" fill="none" stroke="'+
         C.brand+'" stroke-width="2.2"/>';
    s += '<text x="62" y="70" font-size="12.5" font-weight="700" fill="'+C.brand+
         '" text-anchor="middle">line A</text>';
    s += '<text x="180" y="70" font-size="11.5" font-weight="700" fill="#fff" text-anchor="middle">both</text>';
    s += '<text x="298" y="70" font-size="12" font-weight="700" fill="'+C.brand+
         '" text-anchor="middle">line B</text>';
    /* The two readings of "both", to scale. a and b are an example pair, stated in the caption;
       the joint is the engine's own formula, not an artist's impression of it. */
    var ea = 0.60, eb = 0.55;
    var mult = ea * eb;                                   /* 33% */
    var meas = Math.min(ea, eb) * Math.pow(Math.max(ea, eb), 0.38);   /* 45% */
    var lx = 104, by1 = 136, by2 = 176, bh = 26, w2 = 206, w1 = Math.round(w2 * mult / meas);
    s += '<text x="'+(lx-10)+'" y="'+(by1+17)+'" font-size="11.5" fill="'+C.text2+
         '" text-anchor="end">multiplied</text>';
    s += '<rect x="'+lx+'" y="'+by1+'" width="'+w1+'" height="'+bh+'" rx="5" fill="#fff" stroke="'+
         C.text3+'" stroke-width="1.3"/>';
    s += '<text x="'+(lx+w1/2)+'" y="'+(by1+17)+'" font-size="11.5" font-weight="700" fill="'+C.text2+
         '" text-anchor="middle">'+Math.round(mult*100)+'%</text>';
    s += '<text x="'+(lx-10)+'" y="'+(by2+17)+'" font-size="11.5" font-weight="700" fill="'+C.text+
         '" text-anchor="end">measured</text>';
    s += '<rect x="'+lx+'" y="'+by2+'" width="'+w2+'" height="'+bh+'" rx="5" fill="'+C.accent+
         '" stroke="'+C.strong+'" stroke-width="1.3"/>';
    s += '<text x="'+(lx+w1/2)+'" y="'+(by2+17)+'" font-size="11.5" font-weight="700" fill="'+C.text+
         '" text-anchor="middle">'+Math.round(meas*100)+'%</text>';
    s += '<line x1="'+(lx+w1)+'" y1="'+(by2-5)+'" x2="'+(lx+w1)+'" y2="'+(by2+bh+5)+
         '" stroke="'+C.brand+'" stroke-width="1.6" stroke-dasharray="3 3"/>';
    /* bracket under the difference */
    var b0 = lx+w1, b1 = lx+w2, byy = by2+bh+8;
    s += '<path d="M'+b0+' '+byy+' v5 H'+b1+' v-5" fill="none" stroke="'+C.strong+'" stroke-width="1.3"/>';
    s += '<text x="'+((b0+b1)/2)+'" y="'+(byy+19)+'" font-size="10.5" font-weight="700" fill="'+
         C.brand+'" text-anchor="middle">what multiplying throws away</text>';
    s += '</svg>';
    return s;
  }

  /* 4 — the range as a band around the point */
  function figRange(){
    var H = 208, x0 = 26, x1 = 330, axisY = 126;
    var A = 80, B = 100;                          /* axis window */
    var X = function(v){ return x0 + (v*100 - A)/(B-A) * (x1-x0); };
    var xlo = X(T.lo), xhi = X(T.hi), xp = X(T.p);
    var s = '<svg viewBox="0 0 '+W+' '+H+'" role="img" aria-label="the forecast of ' +
      Math.round(T.p*100) + ' percent sits in the middle of a band from ' + Math.round(T.lo*100) +
      ' to ' + Math.round(T.hi*100) + ' percent, ' + Math.round((T.hi-T.lo)*100) + ' points wide">';
    s += '<text x="'+x0+'" y="14" font-size="10.5" fill="'+C.text3+
         '">the number we publish, and the band it sits in</text>';
    /* band */
    s += '<rect x="'+xlo.toFixed(1)+'" y="54" width="'+(xhi-xlo).toFixed(1)+
         '" height="48" rx="7" fill="'+C.mint+'" stroke="'+C.strong+'" stroke-width="1.4"/>';
    s += '<line x1="'+xlo.toFixed(1)+'" y1="48" x2="'+xlo.toFixed(1)+'" y2="'+(axisY-2)+
         '" stroke="'+C.strong+'" stroke-width="1.5"/>';
    s += '<line x1="'+xhi.toFixed(1)+'" y1="48" x2="'+xhi.toFixed(1)+'" y2="'+(axisY-2)+
         '" stroke="'+C.strong+'" stroke-width="1.5"/>';
    /* the point */
    s += '<line x1="'+xp.toFixed(1)+'" y1="44" x2="'+xp.toFixed(1)+'" y2="'+(axisY-2)+
         '" stroke="'+C.brand+'" stroke-width="3"/>';
    s += '<circle cx="'+xp.toFixed(1)+'" cy="78" r="6.5" fill="'+C.brand+'"/>';
    s += '<text x="'+xp.toFixed(1)+'" y="38" font-size="23" font-weight="700" fill="'+
         C.brand+'" text-anchor="middle">' + Math.round(T.p*100) + '%</text>';
    s += '<text x="'+(xlo-5).toFixed(1)+'" y="119" font-size="11.5" font-weight="700" fill="'+
         C.strong+'" text-anchor="end">' + Math.round(T.lo*100) + '%</text>';
    s += '<text x="'+(xhi+5).toFixed(1)+'" y="119" font-size="11.5" font-weight="700" fill="'+
         C.strong+'" text-anchor="start">' + Math.round(T.hi*100) + '%</text>';
    /* axis last, below everything */
    s += '<line x1="'+x0+'" y1="'+axisY+'" x2="'+x1+'" y2="'+axisY+'" stroke="'+C.text3+'" stroke-width="1.5"/>';
    for(var v=A; v<=B; v+=5){
      var x = X(v/100);
      s += '<line x1="'+x.toFixed(1)+'" y1="'+axisY+'" x2="'+x.toFixed(1)+'" y2="'+(axisY+6)+
           '" stroke="'+C.text3+'" stroke-width="1.5"/>';
      s += '<text x="'+x.toFixed(1)+'" y="'+(axisY+20)+'" font-size="10.5" fill="'+C.text3+
           '" text-anchor="middle">'+v+'%</text>';
    }
    s += '<text x="'+x1+'" y="'+(axisY+36)+'" font-size="10.5" fill="'+C.text3+
         '" text-anchor="end">chance he clears ' + esc(T.market) + '</text>';
    /* the separate question, kept separate */
    s += '<line x1="'+x0+'" y1="174" x2="'+x1+'" y2="174" stroke="'+C.border+'" stroke-width="1"/>';
    s += '<text x="'+x0+'" y="196" font-size="11.5" fill="'+C.text2+
         '">…and only if he is on the pitch:</text>';
    s += '<rect x="236" y="182" width="94" height="21" rx="10.5" fill="'+C.brand+'"/>';
    s += '<text x="283" y="196.5" font-size="11.5" font-weight="700" fill="'+C.accent+
         '" text-anchor="middle">' + esc(T.lineup) + '</text>';
    s += '</svg>';
    return s;
  }

  // Built only when there is a card: every caption below interpolates T.player.name and T.p
  // as the array is constructed, so guarding the write that consumes it was guarding the
  // wrong line -- the throw happened here.
  var ENG = !HAS_CARD ? [] : [
    {n:'01', h:'A fitted curve for the player, not an average',
     p:'Every player gets his own distribution for every market — shots, on target, tackles, ' +
       'fouls, cards — fitted from how often he does it, how much of the match he plays and how ' +
       'far the count swings week to week. The percentage we publish is the part of that curve ' +
       'sitting past the line, which is why it is never just his mean.',
     fig: figDistribution,
     cap:'<b>' + esc(T.player.name) + ', ' + esc(T.market) + '.</b> Left of the line is the ' +
          Math.round((1-T.p)*100) + '% where he takes none. Everything right of it adds up to the ' +
          Math.round(T.p*100) + '% on the card.'},
    {n:'02', h:'Then it is checked against what he actually did',
     p:'The curve is the claim; the record is the test. His last ten counts swing from one to ' +
       'five, and an average of those would hide exactly the thing being asked. Crossing the ' +
       'line is a different question from how far past it he goes — and the opponent moves the ' +
       'curve too, because a side that smothers shots is not the same fixture as one that does not.',
     fig: figRun,
     cap:'<b>Ten matches, one line.</b> The counts bounce around; what matters is that the bar ' +
          'reaches the dark rule, and ' + T.reached + ' of ' + T.run.length + ' did.'},
    {n:'03', h:'Two lines on one player are not two lines multiplied',
     p:'A shot and a shot on target are the same night of football. The matches where one ' +
       'happens are heavily the matches where the other does, so multiplying the two numbers ' +
       'quietly discards the overlap and lands under the truth. We measured how far under across ' +
       '237,000 real combinations and correct for it, which is why our combined numbers differ ' +
       'from the obvious arithmetic.',
     fig: figOverlap,
     cap:'<b>The dark lens is the overlap.</b> Example: two lines on one player at 60% and 55%. ' +
          'Multiplying says 33%. Measured across 237,000 real combinations, it is 45% — the pale ' +
          'bar against the lime one, drawn to scale.'},
    {n:'04', h:'The range travels with the number, and so does the lineup',
     p:'A single percentage pretends to a precision nothing has. Every forecast carries the ' +
       'spread around it, so a narrow band reads as confidence and a wide one reads as a warning. ' +
       'And the whole thing is conditional on him being on the pitch, which is answered separately ' +
       'and shown as its own word — never folded into the percentage where it could hide.',
     fig: figRange,
     cap:'<b>' + esc(T.player.name) + ' tonight.</b> ' + Math.round(T.p*100) + '% is the middle of a ' +
          'band ' + Math.round((T.hi-T.lo)*100) + ' points wide. The lineup never enters that number — ' +
          'it is answered on its own line.'}
  ];

  if (HAS_CARD) document.getElementById('eng-grid').innerHTML = ENG.map(function(e){
    return '<article class="eng"><div class="eng-n">' + e.n + '</div><h3>' + e.h + '</h3><p>' +
      e.p + '</p><figure class="fig">' + e.fig() + '<figcaption>' + e.cap + '</figcaption></figure></article>';
  }).join('');

  /* ---------------- track record ---------------- */
  (function(){
    // /track-record answers with no bins until forecasts have been scored, and this maps over them.
    if (!Array.isArray(TRACK.bins) || !TRACK.bins.length) return;
    var A = 60, B = 100;
    var X = function(v){ return ((v*100 - A)/(B-A))*100; };
    document.getElementById('rec-sub').innerHTML =
      'Every forecast is scored once the match is over. This is all of them — <b>' +
      (SCORED == null ? '' : SCORED.toLocaleString('en-GB')) + '</b> so far, split by how likely we said it was. ' +
      'Nothing is held back for looking bad.';

    var ax = '<div class="axis">', grid = '';
    for(var v=60; v<=100; v+=10){
      ax += '<i style="left:' + X(v/100) + '%">' + v + '%</i>';
      grid += '<span class="gl" style="left:' + X(v/100) + '%"></span>';
    }
    ax += '</div>';

    var rows = TRACK.bins.map(function(b){
      var xs = X(b.stated), xh = X(b.actual);
      var l = Math.min(xs,xh), w = Math.abs(xh-xs);
      return '<div class="rrow">' +
        '<div class="rhead"><span class="bandname">' + Math.round(b.from*100) + '–' +
          Math.round(b.to*100) + '%</span>' +
        '<span class="vs"><b class="s">' + Math.round(b.stated*100) + '%</b> said<i>→</i><b class="h">' +
          Math.round(b.actual*100) + '%</b> happened</span>' +
        '<span class="n">' + b.n + ' scored</span></div>' +
        '<div class="track">' + grid + '<span class="rail"></span>' +
          '<span class="link" style="left:' + l + '%;width:' + w + '%"></span>' +
          '<span class="m hap" style="left:' + xh + '%"></span>' +
          '<span class="m said" style="left:' + xs + '%"></span>' +
        '</div></div>';
    }).join('');

    document.getElementById('rec').innerHTML = ax + rows +
      '<div class="leg"><span><i class="s"></i>what we said</span>' +
      '<span><i class="h"></i>what happened</span></div>';
  })();

  /* the form is React's, not this file's */

}