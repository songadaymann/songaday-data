"""Check 2 / differences and slopes: re-test the 'real' and 'probably real' two-group and slope
findings with regressions instead of analyze.py's stratified permutation tests.

For each finding:
  orig   analyze.py's own statistic (Mantel-Haenszel-weighted difference or within-stratum
         slope), recomputed here to confirm the published estimate
  A      OLS with year and month-of-year fixed effects (+ home era), standard errors
         clustered by calendar month (year-month)
  B      a stricter fixed effect: year-month (or calendar week for the weekend test, so
         each weekend is compared only with its own week), clustered by year-month
  C      cluster SEs by year (18 clusters), the most conservative clustering available
  boot   bootstrap that resamples whole years with replacement and refits A (2,000 draws):
         percentile 95% CI and a two-sided percentile p
Views outcomes always use year-month fixed effects (views depend on a video's age), so for
them A = year-month FE, and B adds home/away and weekday.

Extra robustness rows are printed for specific findings (see the notes in main()).
Run: .venv/bin/python analysis/checks/check_2_diffs.py
"""

import json

import numpy as np
import pandas as pd
from scipy import stats

from check_2_common import A, CHECKS, boot_p_two_sided, ci, fast_year_bootstrap, fe_ols, \
    load

N_BOOT = 2000


def orig_stat(df, spec):
    """analyze.py's own estimate for this spec (no permutations)."""
    sub = df.dropna(subset=[spec["x"], spec["y"]]).sort_values("number")
    strata = A.stratum_codes(sub, spec["strata"])
    x = sub[spec["x"]].to_numpy(float)
    y = sub[spec["y"]].to_numpy(float)
    f = A.make_statistic(spec["kind"], y, pd.factorize(strata)[0])
    return float(f(x[None, :])[0])


def row(name, beta, se, n, G, scale, unit):
    t = beta / se
    p = 2 * stats.t.sf(abs(t), max(G - 1, 1))
    lo, hi = beta - stats.t.ppf(0.975, max(G - 1, 1)) * se, \
        beta + stats.t.ppf(0.975, max(G - 1, 1)) * se
    return dict(method=name, estimate=scale(beta), ci_low=scale(lo), ci_high=scale(hi),
                p=float(p), n=int(n), clusters=int(G), unit=unit)


def show(r):
    print(f"   {r['method']:<46} {r['estimate']:+8.2f} {r['unit']:<6} "
          f"[{r['ci_low']:+.2f}, {r['ci_high']:+.2f}]  p={r['p']:.2g}  n={r['n']}  "
          f"G={r['clusters']}", flush=True)


def run_one(df, spec, fe_a, fe_b, label_b, scale, unit, extra=None):
    x, y = spec["x"], spec["y"]
    out = {"id": spec["id"], "rows": []}
    est0 = orig_stat(df, spec)
    print(f"\n{spec['id']}: {spec['question']}", flush=True)
    print(f"   original statistic recomputed: {scale(est0):+.2f} {unit}")
    out["orig"] = scale(est0)

    a = fe_ols(df, y, [x], fe_a, ["ym"])
    out["rows"].append(row("A  " + "+".join("x".join(c) for c in fe_a) + " FE, cl. year-month",
                           a["beta"][0], a["se"][0], a["n"], a["G"], scale, unit))
    b = fe_ols(df, y, [x], fe_b, ["ym"])
    out["rows"].append(row("B  " + label_b, b["beta"][0], b["se"][0], b["n"], b["G"],
                           scale, unit))
    c = fe_ols(df, y, [x], fe_a, ["year"])
    out["rows"].append(row("C  A's FE, clustered by year", c["beta"][0], c["se"][0], c["n"],
                           c["G"], scale, unit))
    # Year-block bootstrap of A (whole years resampled with replacement).
    draws = fast_year_bootstrap(df, y, [x], fe_a, n_boot=N_BOOT, seed=zlib_seed(spec["id"]))
    lo, hi = ci(draws)
    out["rows"].append(dict(method="boot  years resampled, refit A", estimate=scale(a["beta"][0]),
                            ci_low=scale(lo), ci_high=scale(hi), p=boot_p_two_sided(draws),
                            n=a["n"], clusters=int(df["year"].nunique()), unit=unit))
    for r in out["rows"]:
        show(r)
    if extra:
        for name, fn in extra:
            r = fn(df)
            r["method"] = name
            out["rows"].append(r)
            show(r)
    return out


def zlib_seed(s):
    import zlib
    return zlib.crc32(s.encode())


def pp(v):
    return 100 * v


def pct_views(v):
    return 100 * (10 ** v - 1)


def main():
    df = load()
    spec = {t["id"]: t for t in A.TESTS}
    results = []

    # Election days (US general elections) for the politics sensitivity check.
    elections = pd.to_datetime(["2010-11-02", "2012-11-06", "2014-11-04", "2016-11-08",
                                "2018-11-06", "2020-11-03", "2022-11-08", "2024-11-05"])
    near_election = np.zeros(len(df), bool)
    for e in elections:
        near_election |= (df["date"] - e).dt.days.abs().to_numpy() <= 3
    df["near_election"] = near_election
    # Calendar dummies for weekday fixed effects in views model B.
    df["wk"] = df["weekday"]

    def subset_row(mask, y, x, fe, scale, unit, cl=("ym",)):
        def fn(d):
            r = fe_ols(d[mask(d)], y, [x], fe, list(cl))
            return row("", r["beta"][0], r["se"][0], r["n"], r["G"], scale, unit)
        return fn

    # ---- weekend_wild: binary outcome, share in percentage points
    results.append(run_one(
        df, spec["weekend_wild"], fe_a=[["year"], ["month"], ["home_era"]],
        fe_b=[["week"]], label_b="calendar-week FE (weekend vs its own week), cl. ym",
        scale=pp, unit="pts",
        extra=[("   at home only, week FE",
                subset_row(lambda d: d["traveling"] == 0, "wild", "weekend", [["week"]], pp,
                           "pts")),
               ("   2009-2017 only, week FE",
                subset_row(lambda d: d["year"] <= 2017, "wild", "weekend", [["week"]], pp,
                           "pts")),
               ("   2018-2026 only, week FE",
                subset_row(lambda d: d["year"] >= 2018, "wild", "weekend", [["week"]], pp,
                           "pts"))]))

    # ---- travel_length: seconds (clipped 30-480 as in analyze.py)
    results.append(run_one(
        df, spec["travel_length"], fe_a=[["year"], ["month"], ["home_era"]],
        fe_b=[["ym"]], label_b="year-month FE, cl. year-month",
        scale=lambda v: v, unit="s",
        extra=[("   log2 length (x100 = % per doubling), ym FE",
                lambda d: row("", *(lambda r: (r["beta"][0], r["se"][0], r["n"], r["G"]))(
                    fe_ols(d.assign(l2=np.log2(d["length"])), "l2", ["traveling"], [["ym"]],
                           ["ym"])), lambda v: 100 * (2 ** v - 1), "%")),
               ("   unclipped length, ym FE",
                subset_row(lambda d: d["length_raw"].notna(), "length_raw", "traveling",
                           [["ym"]], lambda v: v, "s"))]))

    # ---- travel_views: log10 views -> % views
    results.append(run_one(
        df, spec["travel_views"], fe_a=[["ym"]],
        fe_b=[["ym"], ["wk"]], label_b="year-month + weekday FE, cl. year-month",
        scale=pct_views, unit="%"))

    # ---- news_song_views
    has_text = (df["proper_nouns"].apply(len) > 0) | (df["number"] >= 4749)
    df["has_text"] = has_text
    results.append(run_one(
        df, spec["news_song_views"], fe_a=[["ym"]],
        fe_b=[["ym"], ["wk"]], label_b="year-month + weekday FE, cl. year-month",
        scale=pct_views, unit="%",
        extra=[("   only songs with proper nouns or a description",
                subset_row(lambda d: d["has_text"], "log_views", "news_song", [["ym"]],
                           pct_views, "%")),
               ("   only songs before #4749 (no descriptions)",
                subset_row(lambda d: d["number"] < 4749, "log_views", "news_song", [["ym"]],
                           pct_views, "%"))]))

    # ---- news_politics_topic: slope per 3 politics headlines, in points
    results.append(run_one(
        df, spec["news_politics_topic"], fe_a=[["year"], ["month"]],
        fe_b=[["ym"]], label_b="year-month FE (as analyze.py), cl. year-month",
        scale=lambda v: 100 * 3 * v, unit="pts/3",
        extra=[("   ym FE, dropping +-3 days of US elections",
                subset_row(lambda d: ~d["near_election"], "politics_topic",
                           "news_section_politics_elections", [["ym"]],
                           lambda v: 100 * 3 * v, "pts/3")),
               ("   ym FE, dropping every November",
                subset_row(lambda d: d["month"] != 11, "politics_topic",
                           "news_section_politics_elections", [["ym"]],
                           lambda v: 100 * 3 * v, "pts/3"))]))

    (CHECKS / "check_2_diffs.json").write_text(json.dumps(results, indent=1, default=float))


if __name__ == "__main__":
    main()
