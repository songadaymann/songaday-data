"""Check 2 / trend_dark: 'Are the moods getting darker over time?' (+8.4 points per decade,
Kendall tau +0.57 on 18 yearly means, q = 0.0036).

The published test treats the 18 yearly shares as independent draws around a line. That
fails if the yearly series wanders (tagging habits that persist for years look like a
trend). Re-tests:
  1. the published Kendall test and OLS, reproduced; then without 2026 (a partial year)
  2. Theil-Sen slope with its 95% CI
  3. residual autocorrelation (lag-1) and an OLS t-test with the effective sample size
     shrunk for AR(1) residuals, n_eff = n (1 - r1) / (1 + r1)
  4. Newey-West (HAC, 2 lags) standard error for the yearly OLS slope
  5. random-walk null: if the yearly share is a random walk with no drift, the 17
     year-on-year changes have mean 0; t-test on them
  6. song-level regression on the date with standard errors clustered by year
  7. which moods drive it: the trend for Sad alone, and for 'dark' without Angry and
     Anxious (the two moods whose use grew)
Run: .venv/bin/python analysis/checks/check_2_trend.py
"""

import json

import numpy as np
import pandas as pd
from scipy import stats

from check_2_common import CHECKS, cluster_cov, codes_of, load


def yearly_tests(yearly, label):
    years = yearly.index.to_numpy(float)
    v = yearly.to_numpy(float)
    n = len(v)
    tau, p_tau = stats.kendalltau(years, v)
    fit = stats.linregress(years, v)
    resid = v - (fit.intercept + fit.slope * years)
    r1 = float(np.corrcoef(resid[:-1], resid[1:])[0, 1])
    # AR(1)-adjusted t-test: shrink the degrees of freedom to n_eff.
    n_eff = max(n * (1 - r1) / (1 + r1), 3) if r1 > 0 else n
    se_adj = fit.stderr * np.sqrt((n - 2) / max(n_eff - 2, 1))
    p_adj = 2 * stats.t.sf(abs(fit.slope / se_adj), max(n_eff - 2, 1))
    # Newey-West with 2 lags.
    X = np.column_stack([np.ones(n), years - years.mean()])
    bread = np.linalg.inv(X.T @ X)
    u = resid
    S = (X * u[:, None]).T @ (X * u[:, None])
    for lag in (1, 2):
        w = 1 - lag / 3
        G = (X[lag:] * u[lag:, None]).T @ (X[:-lag] * u[:-lag, None])
        S += w * (G + G.T)
    se_nw = float(np.sqrt((bread @ S @ bread)[1, 1] * n / (n - 2)))
    p_nw = 2 * stats.t.sf(abs(fit.slope / se_nw), n - 2)
    ts = stats.theilslopes(v, years)
    dif = np.diff(v)
    t_rw, p_rw = stats.ttest_1samp(dif, 0.0)
    row = dict(label=label, n_years=n, slope_per_decade_pts=1000 * fit.slope,
               ols_p=float(fit.pvalue), kendall_tau=float(tau), kendall_p=float(p_tau),
               theil_sen_pts=1000 * ts.slope, theil_sen_ci=(1000 * ts.low_slope,
                                                            1000 * ts.high_slope),
               resid_lag1_r=r1, n_eff=float(n_eff), ar1_adjusted_p=float(p_adj),
               newey_west_p=float(p_nw), random_walk_mean_change_pts=100 * dif.mean(),
               random_walk_p=float(p_rw))
    print(f"\n{label} ({n} years)")
    print(f"   OLS {row['slope_per_decade_pts']:+.1f} pts/decade, p={fit.pvalue:.2g}; "
          f"Kendall tau {tau:+.2f}, p={p_tau:.2g}")
    print(f"   Theil-Sen {row['theil_sen_pts']:+.1f} pts/decade "
          f"(95% CI {row['theil_sen_ci'][0]:+.1f} to {row['theil_sen_ci'][1]:+.1f})")
    print(f"   residual lag-1 r = {r1:+.2f} -> n_eff {n_eff:.1f}, AR(1)-adjusted p={p_adj:.2g}; "
          f"Newey-West p={p_nw:.2g}")
    print(f"   random-walk null: mean yearly change {100 * dif.mean():+.2f} pts, "
          f"t-test p={p_rw:.2g}")
    return row


def main():
    df = load()
    out = []
    yearly = df.groupby("year")["dark"].mean()
    out.append(yearly_tests(yearly, "dark share, all years (as published)"))
    out.append(yearly_tests(yearly.drop(2026), "dark share, 2009-2025 (2026 is partial)"))

    # Song-level: dark ~ years since 2009, SEs clustered by year.
    d = df.dropna(subset=["dark"]).reset_index(drop=True)
    t = (d["date"] - d["date"].min()).dt.days.to_numpy() / 3652.5
    X = np.column_stack([np.ones(len(d)), t])
    y = d["dark"].to_numpy()
    b, *_ = np.linalg.lstsq(X, y, rcond=None)
    cov = cluster_cov(X, y - X @ b, codes_of(d, ["year"]))
    se = float(np.sqrt(cov[1, 1]))
    p = 2 * stats.t.sf(abs(b[1] / se), 17)
    print(f"\nsong-level OLS on time, clustered by year: {100 * b[1]:+.1f} pts/decade, "
          f"SE {100 * se:.1f}, p={p:.2g}")
    out.append(dict(label="song-level OLS, cluster by year", slope_per_decade_pts=100 * b[1],
                    se=100 * se, p=float(p)))

    # Which moods carry the trend.
    moods = df["mood"]
    for label, s in (("Sad only", (moods == "Sad").astype(float)),
                     ("dark without Angry and Anxious",
                      (df["dark"].astype(bool) & ~moods.isin(["Angry", "Anxious"]))
                      .astype(float)),
                     ("Angry or Anxious", moods.isin(["Angry", "Anxious"]).astype(float))):
        out.append(yearly_tests(s.groupby(df["year"]).mean(), label))
    by_year = (pd.crosstab(df["year"], df["mood"], normalize="index")
               [["Sad", "Angry", "Anxious", "Annoyed", "Scared"]] * 100).round(1)
    print("\nShares (%) of the dark moods by year:")
    print(by_year.to_string())
    (CHECKS / "check_2_trend.json").write_text(json.dumps(out, indent=1, default=float))


if __name__ == "__main__":
    main()
