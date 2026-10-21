"""Shared helpers for the skeptic checks (check_1_*.py).

Loads the songs exactly as analysis/analyze.py does (by importing its load_songs), so every
check starts from the same variables the findings used, and adds a few plain tools:
  - mh_diff:         Mantel-Haenszel-weighted within-stratum difference (same formula as
                     analyze.py's "diff" statistic)
  - perm_p:          stratified permutation p-value for mh_diff
  - shift_p:         circular-shift p-value for mh_diff
  - ols_cluster:     OLS with cluster-robust (CR1) standard errors, plus HC1 for comparison
  - block_wald:      Wald chi-square for a block of coefficients from a covariance matrix
"""

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[2]

_spec = importlib.util.spec_from_file_location("analyze", ROOT / "analysis" / "analyze.py")
analyze = importlib.util.module_from_spec(_spec)
sys.modules["analyze"] = analyze
_spec.loader.exec_module(analyze)


def load():
    """The analysis frame, plus a few raw columns the checks need."""
    df = analyze.load_songs()
    raw = pd.read_csv(ROOT / "dataset" / "songaday.csv", keep_default_na=False, dtype=str)
    for col in ["location_raw", "place_kind", "place_confidence", "is_between_homes",
                "yt_channel", "yt_days_online", "yt_published_at", "song_sources",
                "news_control_score", "news_match_score", "nouns", "description",
                "main_style", "styles", "song_flags", "yt_views"]:
        df[col] = raw[col].values
    df["between"] = (raw["is_between_homes"] == "True").astype(float).values
    df["days_online"] = pd.to_numeric(raw["yt_days_online"].where(raw["yt_days_online"] != ""))
    df["control_score"] = pd.to_numeric(raw["news_control_score"].where(
        raw["news_control_score"] != ""))
    return df


def codes(df, cols):
    if not cols:
        return np.zeros(len(df), dtype=int)
    return pd.factorize(df[cols].astype(str).agg("|".join, axis=1))[0]


def mh_diff(x, y, strata):
    """Weighted average over strata of mean(y|x=1) - mean(y|x=0), weights n1*n0/n."""
    d = pd.DataFrame({"x": x, "y": y, "s": strata})
    g = d.groupby(["s", "x"])["y"].agg(["sum", "count"]).unstack("x")
    g = g.dropna()
    n1, n0 = g[("count", 1.0)], g[("count", 0.0)]
    m1, m0 = g[("sum", 1.0)] / n1, g[("sum", 0.0)] / n0
    w = n1 * n0 / (n1 + n0)
    return float((w * (m1 - m0)).sum() / w.sum())


def perm_p(x, y, strata, n_perm=1999, seed=1):
    """Two-sided stratified permutation p for mh_diff."""
    rng = np.random.default_rng(seed)
    obs = mh_diff(x, y, strata)
    x = np.asarray(x, float)
    groups = [np.flatnonzero(strata == s) for s in np.unique(strata)]
    null = np.empty(n_perm)
    for b in range(n_perm):
        xp = x.copy()
        for idx in groups:
            xp[idx] = rng.permutation(x[idx])
        null[b] = mh_diff(xp, y, strata)
    p = (1 + np.sum(np.abs(null) >= abs(obs) - 1e-12)) / (n_perm + 1)
    return obs, float(p), null


def shift_p(x, y, strata, n_perm=1999, seed=1, min_shift=30):
    """Two-sided circular-shift p for mh_diff (x rotated in time, y and strata fixed)."""
    rng = np.random.default_rng(seed)
    obs = mh_diff(x, y, strata)
    x = np.asarray(x, float)
    n = len(x)
    ks = rng.integers(min_shift, n - min_shift + 1, size=n_perm)
    null = np.array([mh_diff(np.roll(x, k), y, strata) for k in ks])
    p = (1 + np.sum(np.abs(null) >= abs(obs) - 1e-12)) / (n_perm + 1)
    return obs, float(p), null


def ols_cluster(X, y, clusters):
    """OLS with HC1 and cluster-robust (CR1) covariance."""
    X = np.asarray(X, float)
    y = np.asarray(y, float)
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    n, k = X.shape
    bread = np.linalg.pinv(X.T @ X)
    meat_hc = (X * resid[:, None] ** 2).T @ X
    cov_hc1 = bread @ meat_hc @ bread * n / (n - k)
    cl = pd.factorize(pd.Series(clusters).astype(str))[0]
    G = cl.max() + 1
    S = np.zeros((G, k))
    np.add.at(S, cl, X * resid[:, None])
    meat_cl = S.T @ S
    cov_cl = bread @ meat_cl @ bread * (G / (G - 1)) * ((n - 1) / (n - k))
    return beta, cov_hc1, cov_cl, resid


def block_wald(beta, cov, idx):
    b = beta[idx]
    V = cov[np.ix_(idx, idx)]
    w = float(b @ np.linalg.pinv(V) @ b)
    return w, float(stats.chi2.sf(w, len(idx)))


def fmt(p):
    return f"{p:.4f}" if p >= 0.0001 else "<0.0001"
