"""Check 2 / the views model: re-test views_topic, views_mood, views_length, views_genre and
beard_views with different inference than analyze.py's HC1 Wald tests.

analyze.py regresses log10(views + 1) on month dummies plus feature blocks and tests each
block with heteroskedasticity-robust (HC1) standard errors, which assume songs in the same
month are independent. Here, with the same design matrix (rebuilt below, line for line
from analyze.views_model):
  CR-month  Wald test with standard errors clustered by year-month (213 clusters),
            F-corrected for the cluster count
  CR-year   the same clustered by year (18 clusters); only possible for blocks with
            fewer than 18 terms
  perm      the block's rows shuffled within each month (keeping everything else), 999
            times; p = share of shuffles whose block partial R^2 is at least the real one
  boot      whole years resampled with replacement (500 draws); Wald test using the
            bootstrap covariance of the block's coefficients
For beard_views the single test (beard groups within month) is also rerun as a regression
of log views on beard dummies with year-month fixed effects, clustered by month and by year.
Run: .venv/bin/python analysis/checks/check_2_views.py
"""

import json

import numpy as np
import pandas as pd
from scipy import stats

from check_2_common import A, CHECKS, cluster_cov, codes_of, demean, fe_ols, load, \
    multi_outcome_wald

N_PERM = 999
N_BOOT = 500


def design(df):
    """The feature blocks of analyze.views_model (same rules, same baselines)."""
    d = df[df["log_views"].notna() & df["length_raw"].notna()].copy().reset_index(drop=True)
    blocks = {}

    def dummies(series, levels, prefix):
        return pd.DataFrame({f"{prefix}{lv}": (series == lv).astype(float) for lv in levels})

    topic_counts = pd.Series([t for ts in d["topics"] for t in ts]).value_counts()
    top_topics = [t for t in topic_counts.index if topic_counts[t] >= 30][:30]
    blocks["topic"] = pd.DataFrame({f"topic:{t}": d["topics"].apply(lambda ts: float(t in ts))
                                    for t in top_topics})
    blocks["mood"] = dummies(d["mood12"], [m for m in A.MOOD_ORDER if m != "Pensive"], "mood:")
    loglen = np.log2(d["length_raw"].clip(30, 600))
    c = loglen - loglen.mean()
    blocks["length"] = pd.DataFrame({"log2_length": c, "log2_length_sq": c ** 2})
    inst_counts = d["main_instrument"].value_counts()
    top_inst = [i for i in inst_counts.index[:13] if i != "Acoustic Guitar"]
    blocks["instrument"] = dummies(d["main_instrument"], top_inst, "instrument:")
    genres = ["Rock", "Electro", "Blues", "Folk Rock", "Acapella", "Country"]
    blocks["genre"] = dummies(d["genre"], genres, "genre:")
    blocks["genre"]["genre:Other"] = (~d["genre"].isin(genres + ["Folk"])).astype(float)
    blocks["traveling"] = pd.DataFrame({"traveling": d["traveling"]})
    blocks["weekday"] = dummies(d["weekday"], A.WEEKDAYS[1:], "weekday:")
    blocks["news_song"] = pd.DataFrame({"news_song": d["news_song"]})
    blocks["beard"] = dummies(d["beard"].fillna(""), ["Shadow", "Clean"], "beard:")
    blocks["beard"]["beard:Other"] = (~d["beard"].isin(["Beard", "Shadow", "Clean"])).astype(float)
    return d, blocks


def wald(b, V):
    return float(b @ np.linalg.pinv(V) @ b)


def main():
    df = load()
    d, blocks = design(df)
    month = codes_of(d, ["ym"])
    year = codes_of(d, ["year"])
    names, cols = [], []
    for bname, bdf in blocks.items():
        for c in bdf.columns:
            names.append((bname, c))
            cols.append(bdf[c].to_numpy(float))
    Xraw = np.column_stack(cols)
    # Month dummies absorbed by demeaning within month (FWL); same coefficients as the
    # dummy regression in analyze.py.
    X = demean(Xraw, [month])
    y = demean(d["log_views"].to_numpy(float), [month])[:, 0]
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    u = y - X @ beta
    n, k = X.shape
    G_m, G_y = month.max() + 1, year.max() + 1
    sst = float((y ** 2).sum())
    cov_m = cluster_cov(X, u, month, n_fe=G_m)
    cov_y = cluster_cov(X, u, year, n_fe=G_m)
    # HC1 for reference (n - k - months degrees of freedom, as analyze.py's dummy model).
    bread = np.linalg.pinv(X.T @ X)
    cov_hc1 = bread @ ((X * u[:, None] ** 2).T @ X) @ bread * n / (n - k - G_m)
    rng = np.random.default_rng(20261021)
    results = {}

    # Year bootstrap draws of all coefficients (refit on resampled years).
    yrs = np.unique(year)
    idx_by_year = [np.flatnonzero(year == v) for v in yrs]
    boot = np.empty((N_BOOT, k))
    for bi in range(N_BOOT):
        pick = rng.integers(0, len(yrs), len(yrs))
        idx = np.concatenate([idx_by_year[j] for j in pick])
        copy = np.concatenate([np.full(len(idx_by_year[j]), i) for i, j in enumerate(pick)])
        mc = pd.factorize(month[idx] + copy * G_m)[0]
        Xb = demean(Xraw[idx], [mc])
        yb = demean(d["log_views"].to_numpy(float)[idx], [mc])[:, 0]
        boot[bi], *_ = np.linalg.lstsq(Xb, yb, rcond=None)

    month_groups = [np.flatnonzero(month == m) for m in range(G_m)]
    for bname in ("topic", "mood", "length", "genre", "instrument", "beard", "traveling",
                  "news_song", "weekday"):
        idx = [i for i, (b, _) in enumerate(names) if b == bname]
        keep = [i for i in range(k) if i not in idx]
        q = len(idx)
        b = beta[idx]
        W_hc1 = wald(b, cov_hc1[np.ix_(idx, idx)])
        W_m = wald(b, cov_m[np.ix_(idx, idx)])
        F_m = W_m * (G_m - q) / (q * (G_m - 1))
        p_m = float(stats.f.sf(F_m, q, G_m - q))
        if q < G_y - 1:
            W_y = wald(b, cov_y[np.ix_(idx, idx)])
            F_y = W_y * (G_y - q) / (q * (G_y - 1))
            p_y = float(stats.f.sf(F_y, q, G_y - q))
        else:
            p_y = float("nan")
        Vb = np.cov(boot[:, idx], rowvar=False).reshape(q, q)
        W_b = wald(b, Vb)
        p_b = float(stats.chi2.sf(W_b, q))
        # Partial R^2 and its within-month permutation null.
        Xk = X[:, keep]
        bk, *_ = np.linalg.lstsq(Xk, y, rcond=None)
        rk = y - Xk @ bk
        partial = float(((rk ** 2).sum() - (u ** 2).sum()) / sst)
        # FWL: block effect after the other features = regress rk on the block residualized
        # on the other features. Under the permutation, rows of the block are shuffled within
        # months, then residualized again.
        P = np.linalg.pinv(Xk)
        null = np.empty(N_PERM)
        Braw = Xraw[:, idx]
        for j in range(N_PERM):
            perm = np.arange(n)
            for g in month_groups:
                perm[g] = rng.permutation(g)
            Bp = demean(Braw[perm], [month])
            Bp_res = Bp - Xk @ (P @ Bp)
            coef, *_ = np.linalg.lstsq(Bp_res, rk, rcond=None)
            null[j] = float(((Bp_res @ coef) ** 2).sum() / sst)
        p_perm = float((1 + np.sum(null >= partial)) / (N_PERM + 1))
        results[bname] = dict(terms=q, partial_r2=partial, perm_null_mean=float(null.mean()),
                              perm_null_p99=float(np.quantile(null, 0.99)), p_perm=p_perm,
                              p_hc1=float(stats.chi2.sf(W_hc1, q)), p_cluster_month=p_m,
                              p_cluster_year=p_y, p_boot_wald=p_b)
        r = results[bname]
        print(f"{bname:<11} {q:>2} terms  partial R2 {100 * partial:5.2f}% (perm null mean "
              f"{100 * r['perm_null_mean']:.2f}%, 99th pct {100 * r['perm_null_p99']:.2f}%)  "
              f"p: HC1 {r['p_hc1']:.2g} | cl.month {p_m:.2g} | cl.year {p_y:.2g} | "
              f"year-boot {p_b:.2g} | perm {p_perm:.3g}", flush=True)
        if bname == "length":
            i1 = names.index(("length", "log2_length"))
            print(f"   doubling length x{10 ** beta[i1]:.2f}; cl.month CI x"
                  f"{10 ** (beta[i1] - 1.96 * np.sqrt(cov_m[i1, i1])):.2f}-x"
                  f"{10 ** (beta[i1] + 1.96 * np.sqrt(cov_m[i1, i1])):.2f}; year-boot CI x"
                  f"{10 ** np.quantile(boot[:, i1], 0.025):.2f}-x"
                  f"{10 ** np.quantile(boot[:, i1], 0.975):.2f}")
        if bname == "topic":
            ia = names.index(("topic", "topic:Apple"))
            print(f"   Apple x{10 ** beta[ia]:.2f}; year-boot CI x"
                  f"{10 ** np.quantile(boot[:, ia], 0.025):.2f}-x"
                  f"{10 ** np.quantile(boot[:, ia], 0.975):.2f}")
            # Topic block without Apple: is it one topic?
            idx2 = [i for i in idx if i != ia]
            W2 = wald(beta[idx2], cov_m[np.ix_(idx2, idx2)])
            q2 = len(idx2)
            F2 = W2 * (G_m - q2) / (q2 * (G_m - 1))
            print(f"   topic block without Apple, cl.month p={stats.f.sf(F2, q2, G_m - q2):.2g}")
            results[bname]["p_cluster_month_without_apple"] = float(stats.f.sf(F2, q2,
                                                                               G_m - q2))

    # beard_views as its own test: log views on beard dummies, year-month FE.
    bd = df[df["beard3"].isin(["Beard", "Shadow", "Clean"]) & df["log_views"].notna()].copy()
    bd["shadow"] = (bd["beard3"] == "Shadow").astype(float)
    bd["clean"] = (bd["beard3"] == "Clean").astype(float)
    for cl in ("ym", "year"):
        r = fe_ols(bd, "log_views", ["shadow", "clean"], [["ym"]], [cl])
        W = wald(r["beta"], r["cov"])
        F = W * (r["G"] - 2) / (2 * (r["G"] - 1))
        p = float(stats.f.sf(F, 2, r["G"] - 2))
        print(f"beard_views single test, ym FE, cluster {cl}: Shadow "
              f"{100 * (10 ** r['beta'][0] - 1):+.0f}%, Clean {100 * (10 ** r['beta'][1] - 1):+.0f}%"
              f" (SE {r['se'][1]:.3f} log10), joint p={p:.2g}, G={r['G']}")
        results[f"beard_views_single_cl_{cl}"] = dict(shadow=float(r["beta"][0]),
                                                     clean=float(r["beta"][1]), p=p,
                                                     G=int(r["G"]))
    (CHECKS / "check_2_views.json").write_text(json.dumps(results, indent=1, default=float))


if __name__ == "__main__":
    main()
