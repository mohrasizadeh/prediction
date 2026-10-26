"""fit_ctx.py -- fit and score context features on top of the Dixon-Coles baseline."""
import os, sys, json
import numpy as np, pandas as pd
from scipy.optimize import minimize
from scipy.special import gammaln
from scipy.stats import poisson

HERE = os.path.dirname(os.path.abspath(__file__))
T = pd.read_pickle(os.path.join(HERE, "data", "teamrows.pkl"))
EU = ("UCL", "UEL", "UECL")


def flag(cond):
    return cond.astype(float)


def add_features(T):
    T = T.copy()
    T["short"] = flag(T.prev_gap < 3.5)                      # played 3 days or fewer ago
    T["very_short"] = flag(T.prev_gap < 2.5)
    T["long"] = flag(T.prev_gap >= 7.5)
    T["eu_next"] = flag(T.next_comp.isin(EU) & (T.next_gap <= 4.5))
    T["eu_prev"] = flag(T.prev_comp.isin(EU) & (T.prev_gap <= 4.5))
    T["ucl_next"] = flag((T.next_comp == "UCL") & (T.next_gap <= 4.5))
    T["ucl_prev"] = flag((T.prev_comp == "UCL") & (T.prev_gap <= 4.5))
    T["cup_next"] = flag(T.next_comp.isin(("EFL", "FA")) & (T.next_gap <= 4.5))
    T["cup_prev"] = flag(T.prev_comp.isin(("EFL", "FA")) & (T.prev_gap <= 4.5))
    # pressure: a bigger game very soon (importance above the league match, weighted by closeness)
    T["press"] = np.where(T.next_gap <= 4.5, np.maximum(T.next_imp - 1.0, 0.0), 0.0) * np.where(T.next_gap <= 3.5, 1.0, 0.6)
    T["load"] = flag(T.prev_gap < 3.5)
    # pair each row with the opposite side of the same match
    key = T[["idx", "side"]].copy()
    other = T.set_index(["idx", "side"])
    opp_side = T.side.map({"H": "A", "A": "H"})
    cols = ["short", "very_short", "long", "eu_next", "eu_prev", "ucl_next", "ucl_prev", "cup_next", "cup_prev", "press", "load"]
    O = other.loc[list(zip(T.idx, opp_side)), cols]
    for c in cols:
        T["o_" + c] = O[c].values
    return T


T = add_features(T)


# ------------------------------------------------------------------ Poisson GLM with offset
def fit_glm(X, y, off, l2=0.5):
    k = X.shape[1]

    def f(b):
        eta = off + X @ b
        mu = np.exp(np.clip(eta, -10, 5))
        ll = np.sum(y * eta - mu)
        g = X.T @ (y - mu)
        return -ll + 0.5 * l2 * np.sum(b ** 2), -g + l2 * b

    res = minimize(f, np.zeros(k), jac=True, method="L-BFGS-B")
    return res.x


def pois_ll(y, mu):
    return y * np.log(mu) - mu - gammaln(y + 1)


def tau(x, y, lh, la, rho):
    t = 1.0
    if x == 0 and y == 0: t = 1 - lh * la * rho
    elif x == 0 and y == 1: t = 1 + lh * rho
    elif x == 1 and y == 0: t = 1 + la * rho
    elif x == 1 and y == 1: t = 1 - rho
    return max(t, 1e-9)


def outcome_probs(lh, la, rho, G=9):
    g = np.arange(G + 1)
    M = np.outer(poisson.pmf(g, lh), poisson.pmf(g, la))
    for x, y in ((0, 0), (0, 1), (1, 0), (1, 1)):
        M[x, y] *= tau(x, y, lh, la, rho)
    M /= M.sum()
    return np.tril(M, -1).sum(), np.trace(M), np.triu(M, 1).sum()


def match_table(T):
    H = T[T.side == "H"].set_index("idx"); A = T[T.side == "A"].set_index("idx")
    m = pd.DataFrame({"hg": H.y, "ag": A.y, "rho": H.rho, "season": H.season})
    return m


def logloss_1x2(T, mu):
    """mu: array aligned with T rows (adjusted expected goals)."""
    T = T.assign(mu=mu)
    H = T[T.side == "H"].set_index("idx"); A = T[T.side == "A"].set_index("idx")
    ll = []
    for i in H.index:
        ph, pd_, pa = outcome_probs(H.at[i, "mu"], A.at[i, "mu"], H.at[i, "rho"])
        hg, ag = H.at[i, "y"], A.at[i, "y"]
        p = ph if hg > ag else (pa if hg < ag else pd_)
        ll.append(-np.log(max(p, 1e-9)))
    return np.array(ll), H.index.values


def cv_model(T, cols, l2=0.5, with_1x2=True):
    """Leave-one-season-out. Returns out-of-sample goal log-lik for base and model, and 1X2 log loss."""
    seasons = sorted(T.season.unique())
    mu_m = np.zeros(len(T)); mu_b = T.lam.values.copy()
    off = np.log(T.lam.values)
    X = T[cols].values.astype(float) if cols else np.zeros((len(T), 0))
    for s in seasons:
        te = (T.season == s).values
        if X.shape[1] == 0:
            mu_m[te] = mu_b[te]
            continue
        b = fit_glm(X[~te], T.y.values[~te], off[~te], l2)
        mu_m[te] = np.exp(off[te] + X[te] @ b)
    y = T.y.values
    d_ll = pois_ll(y, mu_m) - pois_ll(y, mu_b)
    out = dict(n=len(T), d_goal_ll=float(d_ll.sum()), d_goal_ll_per1000=float(d_ll.sum() / len(T) * 1000))
    if with_1x2:
        lm, idx = logloss_1x2(T, mu_m)
        lb, _ = logloss_1x2(T, mu_b)
        out["logloss_base"] = float(lb.mean()); out["logloss_model"] = float(lm.mean())
        out["d_logloss"] = float(lm.mean() - lb.mean())
        out["d_logloss_se"] = float((lm - lb).std(ddof=1) / np.sqrt(len(lm)))
    return out


def boot_coefs(T, cols, B=400, l2=0.5, seed=1):
    rng = np.random.default_rng(seed)
    idxs = T.idx.unique()
    groups = {i: np.where(T.idx.values == i)[0] for i in idxs}
    off = np.log(T.lam.values); X = T[cols].values.astype(float); y = T.y.values
    b_full = fit_glm(X, y, off, l2)
    bs = []
    for _ in range(B):
        pick = rng.choice(idxs, len(idxs), replace=True)
        ii = np.concatenate([groups[i] for i in pick])
        bs.append(fit_glm(X[ii], y[ii], off[ii], l2))
    bs = np.array(bs)
    return b_full, np.percentile(bs, 2.5, axis=0), np.percentile(bs, 97.5, axis=0), bs.std(0)


def report(name, T, cols, B=300):
    cv = cv_model(T, cols)
    b, lo, hi, se = boot_coefs(T, cols, B=B)
    print(f"\n=== {name}   (n team-rows {len(T)}, matches {T.idx.nunique()})")
    print(f"  out-of-sample goal log-lik gain vs baseline: {cv['d_goal_ll']:+.2f}   (per 1000 team-rows {cv['d_goal_ll_per1000']:+.2f})")
    print(f"  1X2 log loss: base {cv['logloss_base']:.5f}  model {cv['logloss_model']:.5f}  change {cv['d_logloss']:+.5f}  (se {cv['d_logloss_se']:.5f})")
    for c, bb, l, h in zip(cols, b, lo, hi):
        star = "  <-- CI excludes 0" if (l > 0 or h < 0) else ""
        print(f"  {c:12s} {bb:+.3f}  [{l:+.3f}, {h:+.3f}]  = {100*(np.exp(bb)-1):+.1f}% goals{star}")
    return cv, dict(zip(cols, [float(x) for x in b]))


if __name__ == "__main__":
    out = {}
    ok = T.groupby("idx").apply(lambda g: bool((g.known == 1).all() and (g.matchweek_ord > 4).all()), include_groups=False)
    full = T[T.idx.isin(ok[ok].index)].copy()      # both clubs known to the model; skip each season's first 4 dates

    # ---------- A. Europe flags, all 14 seasons (Champions League only before 2020-21)
    cols = ["eu_next", "o_eu_next", "eu_prev", "o_eu_prev"]
    out["A_europe_all14"] = report("A. European game within 4.5 days (UCL only before 2020-21), 14 seasons", full, cols)

    # ---------- B. Rest features, seasons with cup data (2018-19 on)
    rest = full[full.season >= "2018-19"]
    cols = ["short", "o_short", "long", "o_long"]
    out["B_rest_2018"] = report("B. Days of rest, 2018-19 to 2024-25 (all cups present; Europa League missing 18-19, 19-20)", rest, cols)
    comp = full[full.season >= "2020-21"]
    out["B_rest_2020"] = report("B2. Days of rest, 2020-21 to 2024-25 (every competition present)", comp, cols)

    # ---------- C. Joint model on complete seasons
    cols = ["short", "o_short", "eu_next", "o_eu_next", "eu_prev", "o_eu_prev", "cup_next", "o_cup_next"]
    out["C_joint_2020"] = report("C. Rest + Europe + cup-next, 2020-21 to 2024-25", comp, cols)

    # ---------- D. importance-weighted pressure
    cols = ["press", "o_press", "load", "o_load"]
    out["D_pressure_2020"] = report("D. Pressure (bigger game soon) + load, 2020-21 to 2024-25", comp, cols)
    json.dump({k: v[1] | {"_cv": v[0]} for k, v in out.items()}, open(os.path.join(HERE, "data", "ctx_results.json"), "w"), indent=1)
