"""Walk-forward model comparison on football-data style match tables (team level).
Usage: python wf.py LEAGUE STAT   -> writes out/LEAGUE_STAT.pkl with mu_home, mu_away per variant."""
import sys, numpy as np, pandas as pd, pickle, os
from scipy.optimize import minimize
D = pd.read_csv('/tmp/bt/xg/data/Matches.csv', low_memory=False, parse_dates=['MatchDate'])
COLS = {'goals': ('FTHome', 'FTAway'), 'shots': ('HomeShots', 'AwayShots'), 'sot': ('HomeTarget', 'AwayTarget'),
        'corners': ('HomeCorners', 'AwayCorners'), 'fouls': ('HomeFouls', 'AwayFouls'), 'yellow': ('HomeYellow', 'AwayYellow')}

def fit(H, A, yh, ya, age, xi, lam, lam2=None, elo=None, p0=None, n=None):
    """Poisson GLM. params: c, h, att[n], con[n] (+ split devs if lam2) (+ elo slope)."""
    n = n or int(max(H.max(), A.max())) + 1
    w = np.exp(-xi * age)
    split = lam2 is not None
    k = 2 + 2 * n + (4 * n if split else 0) + (1 if elo is not None else 0)
    def unpack(t):
        c, h = t[0], t[1]; a = t[2:2 + n]; d = t[2 + n:2 + 2 * n]
        o = 2 + 2 * n
        if split:
            ah, dh, aa, da = t[o:o + n], t[o + n:o + 2 * n], t[o + 2 * n:o + 3 * n], t[o + 3 * n:o + 4 * n]; o += 4 * n
        else: ah = dh = aa = da = np.zeros(n)
        b = t[o] if elo is not None else 0.0
        return c, h, a, d, ah, dh, aa, da, b
    def f(t):
        c, h, a, d, ah, dh, aa, da, b = unpack(t)
        eh = c + h + a[H] + d[A] + ah[H] + da[A]; ea = c + a[A] + d[H] + aa[A] + dh[H]
        if elo is not None: eh = eh + b * elo; ea = ea - b * elo
        mh, ma = np.exp(eh), np.exp(ea)
        ll = w * (yh * eh - mh + ya * ea - ma)
        pen = lam * (a @ a + d @ d)
        if split: pen += lam2 * (ah @ ah + dh @ dh + aa @ aa + da @ da)
        gh, ga = w * (yh - mh), w * (ya - ma)
        g = np.zeros(k)
        g[0] = gh.sum() + ga.sum(); g[1] = gh.sum()
        ga_ = np.bincount(H, gh, n) + np.bincount(A, ga, n)          # attack
        gd_ = np.bincount(A, gh, n) + np.bincount(H, ga, n)          # concession
        g[2:2 + n] = ga_ - 2 * lam * a; g[2 + n:2 + 2 * n] = gd_ - 2 * lam * d
        o = 2 + 2 * n
        if split:
            g[o:o + n] = np.bincount(H, gh, n) - 2 * lam2 * ah
            g[o + n:o + 2 * n] = np.bincount(H, ga, n) - 2 * lam2 * dh
            g[o + 2 * n:o + 3 * n] = np.bincount(A, ga, n) - 2 * lam2 * aa
            g[o + 3 * n:o + 4 * n] = np.bincount(A, gh, n) - 2 * lam2 * da
            o += 4 * n
        if elo is not None: g[o] = (gh * elo).sum() - (ga * elo).sum()
        return -(ll.sum() - pen), -g
    t0 = np.zeros(k) if p0 is None or len(p0) != k else p0
    if p0 is None: t0[0] = np.log(max((yh.mean() + ya.mean()) / 2, 0.1)) 
    r = minimize(f, t0, jac=True, method='L-BFGS-B', options={'maxiter': 150})
    return r.x, unpack(r.x)

def predict(par, H, A, elo=None):
    c, h, a, d, ah, dh, aa, da, b = par
    eh = c + h + a[H] + d[A] + ah[H] + da[A]; ea = c + a[A] + d[H] + aa[A] + dh[H]
    if elo is not None and b != 0: eh = eh + b * elo; ea = ea - b * elo
    return np.exp(eh), np.exp(ea)

# variant name -> kwargs (xi per day, lam, lam2, use_elo)
def variants(stat):
    base = {'goals': 0.0022, 'shots': 0.0022, 'sot': 0.0022, 'corners': 0.0016, 'fouls': 0.0012, 'yellow': 0.0014}[stat]
    lam = {'goals': 3.0, 'shots': 6.0, 'sot': 5.0, 'corners': 6.0, 'fouls': 8.0, 'yellow': 8.0}[stat]
    v = {}
    for xm in (1, 2, 3, 4.5, 7):
        for lm in (0.5, 1, 2):
            v[f'x{xm}_l{lm}'] = dict(xi=base * xm, lam=lam * lm)
    return v

if __name__ == '__main__':
    lg, stat = sys.argv[1], sys.argv[2]
    yc = COLS[stat]
    d = D[(D.Division == lg) & (D.MatchDate >= '2012-07-01') & (D.MatchDate <= '2026-07-01')].dropna(subset=list(COLS['goals']) + list(yc)).sort_values('MatchDate').reset_index(drop=True)
    teams = sorted(set(d.HomeTeam) | set(d.AwayTeam)); ti = {t: i for i, t in enumerate(teams)}
    H = d.HomeTeam.map(ti).values; A = d.AwayTeam.map(ti).values
    yh = d[yc[0]].values.astype(float); ya = d[yc[1]].values.astype(float)
    elo = ((d.HomeElo - d.AwayElo) / 400.0).values
    dates = d.MatchDate.values.astype('datetime64[D]').astype(int)
    out = {k: (np.full(len(d), np.nan), np.full(len(d), np.nan)) for k in variants(stat)}
    start = np.datetime64('2014-08-01').astype(int)
    t = start
    prev = {}
    while t <= dates.max():
        te = t + 28
        tr = (dates < t) & (dates >= t - 1500)
        pr = (dates >= t) & (dates < te)
        if tr.sum() > 600 and pr.any():
            for name, kw in variants(stat).items():
                e = elo[tr] if kw.get('use_elo') else None
                x, par = fit(H[tr], A[tr], yh[tr], ya[tr], (t - dates[tr]).astype(float), kw['xi'], kw['lam'], kw.get('lam2'), e, prev.get(name), len(teams))
                prev[name] = x
                mh, ma = predict(par, H[pr], A[pr], elo[pr] if kw.get('use_elo') else None)
                out[name][0][pr] = mh; out[name][1][pr] = ma
        t = te
    os.makedirs('/tmp/bt/out2', exist_ok=True)
    pickle.dump({'d': d, 'out': out}, open(f'/tmp/bt/out2/{lg}_{stat}.pkl', 'wb'))
    print(lg, stat, 'done', len(d))
