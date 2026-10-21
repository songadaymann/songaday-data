"""Shared helpers for the skeptic's statistics checks (analysis/checks/check_2_*.py).

These checks re-test the findings in analysis/findings.json with methods that differ from
the ones analysis/analyze.py used:
  - fixed-effects regressions (year, month-of-year, year-month, week ...) instead of
    Mantel-Haenszel stratified differences,
  - cluster-robust standard errors (songs in the same month or week are not independent),
  - cluster bootstraps that resample whole years (or months) with replacement,
  - permutation schemes that keep more of the time structure than analyze.py's.

The songs are loaded with analyze.py's own load_songs(), so every derived column
(wild, dark, traveling, log_views, news_song ...) means exactly what it means there.
Nothing here writes outside analysis/checks/.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

CHECKS = Path(__file__).resolve().parent
ANALYSIS = CHECKS.parent
ROOT = ANALYSIS.parent
sys.path.insert(0, str(ANALYSIS))

import analyze as A  # noqa: E402  (analyze.py only runs its pipeline under __main__)


def load():
    """The songs, as analyze.py sees them, plus a few keys used for fixed effects and
    clusters."""
    df = A.load_songs().sort_values("number").reset_index(drop=True)
    df["ym"] = df["date"].dt.strftime("%Y-%m")
    # ISO-ish calendar week that starts on Monday: every Mon-Sun run of 7 songs.
    df["week"] = (df["date"] - pd.to_timedelta(df["date"].dt.weekday, unit="D")).dt.strftime(
        "%Y-%m-%d")
    df["quarter"] = df["year"].astype(str) + "Q" + ((df["month"] - 1) // 3 + 1).astype(str)
    return df


def findings():
    import json
    return {f["id"]: f for f in json.loads((ANALYSIS / "findings.json").read_text())["findings"]}


# ---------------------------------------------------------------------------------------
# Fixed effects by demeaning (alternating projections), then OLS on the residuals (FWL).

def demean(M, fe_codes, tol=1e-10, max_iter=500):
    """Remove every fixed effect in fe_codes (list of integer code arrays) from each column
    of M. One FE is exact; several are handled by alternating projections."""
    M = np.array(M, dtype=float, copy=True)
    if M.ndim == 1:
        M = M[:, None]
    if not fe_codes:
        return M - M.mean(0)
    if len(fe_codes) > 1 and sum(c.max() + 1 for c in fe_codes) <= 600:
        # Several small fixed effects: project them out exactly with a dummy matrix.
        D = np.column_stack([np.eye(c.max() + 1)[c] for c in fe_codes])
        coef, *_ = np.linalg.lstsq(D, M, rcond=None)
        return M - D @ coef
    for _ in range(max_iter):
        before = M.copy()
        for codes in fe_codes:
            cnt = np.bincount(codes)
            for j in range(M.shape[1]):
                M[:, j] -= (np.bincount(codes, weights=M[:, j]) / cnt)[codes]
        if len(fe_codes) == 1 or np.max(np.abs(M - before)) < tol:
            break
    return M


def codes_of(df, cols):
    """Integer codes for the combination of columns."""
    if isinstance(cols, str):
        cols = [cols]
    return pd.factorize(df[cols].astype(str).agg("|".join, axis=1))[0]


def fe_ols(df, y, xs, fe, cluster):
    """OLS of df[y] on df[xs] with fixed effects `fe` (list of column lists) and
    cluster-robust (CR1) standard errors by `cluster`. Returns dict(beta, se, cov, n, G,
    resid)."""
    d = df.dropna(subset=[y] + xs).reset_index(drop=True)
    fe_codes = [codes_of(d, c) for c in fe]
    Y = demean(d[y].to_numpy(float), fe_codes)[:, 0]
    X = demean(d[xs].to_numpy(float), fe_codes)
    beta, *_ = np.linalg.lstsq(X, Y, rcond=None)
    u = Y - X @ beta
    g = codes_of(d, cluster)
    cov = cluster_cov(X, u, g, n_fe=sum(c.max() + 1 for c in fe_codes))
    return dict(beta=beta, se=np.sqrt(np.diag(cov)), cov=cov, n=len(d), G=g.max() + 1,
                resid=u, X=X, Y=Y, d=d)


def cluster_cov(X, u, g, n_fe=0):
    """CR1 cluster-robust covariance for OLS coefficients."""
    n, k = X.shape
    G = g.max() + 1
    bread = np.linalg.pinv(X.T @ X)
    S = np.zeros((G, k))
    np.add.at(S, g, X * u[:, None])
    meat = S.T @ S
    adj = G / (G - 1) * (n - 1) / max(n - k - n_fe, 1)
    return bread @ meat @ bread * adj


def multi_outcome_wald(df, x_cat, x_levels, y_cat, y_levels, fe, cluster):
    """Joint test that a categorical exposure is unrelated to a categorical outcome,
    within fixed effects: stack one linear-probability model per outcome level (all but
    the last level) on dummies for the exposure (all but the first level), and do a
    cluster-robust Wald test of all (A-1)(C-1) coefficients. Returns W, df, the
    small-sample F version and its p-value (Hotelling-style correction for G clusters)."""
    d = df[df[x_cat].isin(x_levels) & df[y_cat].isin(y_levels)].reset_index(drop=True)
    fe_codes = [codes_of(d, c) for c in fe]
    Xd = np.column_stack([(d[x_cat] == lv).astype(float) for lv in x_levels[1:]])
    Yd = np.column_stack([(d[y_cat] == lv).astype(float) for lv in y_levels[:-1]])
    X = demean(Xd, fe_codes)
    Y = demean(Yd, fe_codes)
    bread = np.linalg.pinv(X.T @ X)
    B = bread @ X.T @ Y                       # (A-1) x (C-1)
    U = Y - X @ B
    g = codes_of(d, cluster)
    G = g.max() + 1
    a, c = X.shape[1], Y.shape[1]
    # Score per cluster: vec(X_g' U_g), stacked column by column of B.
    S = np.zeros((G, a * c))
    for j in range(c):
        Sj = np.zeros((G, a))
        np.add.at(Sj, g, X * U[:, [j]])
        S[:, j * a:(j + 1) * a] = Sj
    Binv = np.kron(np.eye(c), bread)
    V = Binv @ (S.T @ S) @ Binv * G / (G - 1)
    b = B.T.reshape(-1)                       # column-major: outcome blocks of size a
    W = float(b @ np.linalg.pinv(V) @ b)
    q = a * c
    p_chi2 = float(stats.chi2.sf(W, q))
    if G > q:
        F = W * (G - q) / (q * (G - 1))
        p_F = float(stats.f.sf(F, q, G - q))
    else:
        F, p_F = float("nan"), float("nan")
    return dict(W=W, q=q, G=int(G), n=len(d), p_chi2=p_chi2, F=F, p_F=p_F, B=B,
                x_levels=x_levels, y_levels=y_levels)


def chi2_within(x, y, strata, n_x, n_y):
    """Chi-square of observed x-by-y counts against counts expected if x and y were
    independent inside every stratum (the statistic analyze.py uses for mood mixes)."""
    S = strata.max() + 1
    cc = np.bincount(strata * n_y + y, minlength=S * n_y).reshape(S, n_y)
    W = cc / cc.sum(1)[:, None]
    rc = np.bincount(strata * n_x + x, minlength=S * n_x).reshape(S, n_x)
    E = rc.T @ W
    O = np.bincount(x * n_y + y, minlength=n_x * n_y).reshape(n_x, n_y)
    with np.errstate(divide="ignore", invalid="ignore"):
        return float(np.where(E > 0, (O - E) ** 2 / E, 0).sum())


def fast_year_bootstrap(df, y, xs, fe, n_boot=2000, seed=1):
    """Cluster bootstrap of an FE regression, resampling whole years with replacement,
    done on numpy arrays (fast). `fe` is a list of column lists as in fe_ols. A fixed
    effect that includes 'year' or 'ym' or 'week' or 'quarter' is made distinct for each
    resampled copy of a year (a year drawn twice counts as two years). Returns the
    bootstrap draws of the coefficient on xs[0]."""
    d = df.dropna(subset=[y] + xs).reset_index(drop=True)
    Y = d[y].to_numpy(float)
    X = d[xs].to_numpy(float)
    yr = d["year"].to_numpy()
    years = np.unique(yr)
    idx_by_year = [np.flatnonzero(yr == v) for v in years]
    fe_info = []
    for cols in fe:
        codes = codes_of(d, cols)
        per_copy = any(c in ("year", "ym", "week", "quarter") for c in cols)
        fe_info.append((codes, per_copy, codes.max() + 1))
    rng = np.random.default_rng(seed)
    out = np.empty(n_boot)
    for b in range(n_boot):
        pick = rng.integers(0, len(years), len(years))
        idx = np.concatenate([idx_by_year[k] for k in pick])
        copy = np.concatenate([np.full(len(idx_by_year[k]), i) for i, k in enumerate(pick)])
        fcodes = []
        for codes, per_copy, K in fe_info:
            c = codes[idx] + (copy * K if per_copy else 0)
            fcodes.append(pd.factorize(c)[0])
        Yb = demean(Y[idx], fcodes, tol=1e-8, max_iter=200)[:, 0]
        Xb = demean(X[idx], fcodes, tol=1e-8, max_iter=200)
        beta, *_ = np.linalg.lstsq(Xb, Yb, rcond=None)
        out[b] = beta[0]
    return out


def year_bootstrap(df, stat_fn, n_boot=2000, seed=1, unit="year"):
    """Cluster bootstrap: resample whole `unit`s (years by default) with replacement and
    recompute stat_fn on the stacked sample. Resampled copies of a year get distinct
    labels so year fixed effects treat them as separate years. Returns the array of
    statistics."""
    rng = np.random.default_rng(seed)
    units = df[unit].unique()
    parts = {u: g for u, g in df.groupby(unit)}
    out = []
    for _ in range(n_boot):
        pick = rng.choice(units, size=len(units), replace=True)
        frames = []
        for i, u in enumerate(pick):
            g = parts[u].copy()
            g["boot_unit"] = i
            # Keep year-month keys distinct per copy too.
            g["ym"] = g["ym"] + f"#{i}"
            g["year_copy"] = g["year"].astype(str) + f"#{i}"
            frames.append(g)
        out.append(stat_fn(pd.concat(frames, ignore_index=True)))
    return np.array(out)


def ci(a, level=0.95):
    a = np.asarray(a, float)
    a = a[np.isfinite(a)]
    lo, hi = np.quantile(a, [(1 - level) / 2, 1 - (1 - level) / 2])
    return float(lo), float(hi)


def boot_p_two_sided(a):
    """Share of bootstrap draws on the other side of zero, doubled (percentile p)."""
    a = np.asarray(a, float)
    a = a[np.isfinite(a)]
    p = 2 * min((a <= 0).mean(), (a >= 0).mean())
    return float(min(1.0, max(p, 1 / len(a))))
