"""Skeptic check: the four views-model findings (views_topic, views_mood, views_length,
views_genre), and the model checks of travel, news and beard.

The model is OLS of log10(views + 1) on month dummies plus song features, with HC1
(heteroskedasticity-only) standard errors. Confounds and inference problems tried:
  1. Correlated errors: songs of the same month (or the same year) share audiences, viral
     runs and channel changes. Recompute every block's Wald test with cluster-robust
     standard errors by month and by year.
  2. Channel: three channels host the videos; add channel dummies.
  3. Age within the month: days online relative to the month's mean.
  4. Viral outliers: drop the top 1% by views. Ranks: replace log views with the song's
     percentile within its month.
  5. Replication: fit the model separately on 2009-2016 and 2017-2026 and see whether each
     block is significant in both halves and the coefficients agree.
  6. Length: a quadratic in log length is assumed; show the within-month binned shape, and
     check that the effect is not only the very short songs (YouTube may treat videos
     under a minute as Shorts).
"""

import math

import numpy as np
import pandas as pd

from check_1_common import analyze, block_wald, fmt, load, ols_cluster

df = load()
d = df[df.log_views.notna() & df.length_raw.notna()].copy()


def design(d, extra=None):
    """The analyze.py views-model design (same blocks and baselines)."""
    blocks = {}

    def dummies(series, levels, prefix):
        return pd.DataFrame({f"{prefix}{lv}": (series == lv).astype(float) for lv in levels},
                            index=series.index)

    month = pd.get_dummies(d["year_month"], drop_first=False, dtype=float)
    topic_counts = pd.Series([t for ts in d["topics"] for t in ts]).value_counts()
    top_topics = [t for t in topic_counts.index if topic_counts[t] >= 30][:30]
    blocks["topic"] = pd.DataFrame({f"topic:{t}": d["topics"].apply(lambda ts: float(t in ts))
                                    for t in top_topics}, index=d.index)
    blocks["mood"] = dummies(d["mood12"], [m for m in analyze.MOOD_ORDER if m != "Pensive"],
                             "mood:")
    loglen = np.log2(d["length_raw"].clip(30, 600))
    c = loglen - loglen.mean()
    blocks["length"] = pd.DataFrame({"log2_length": c, "log2_length_sq": c ** 2}, index=d.index)
    inst_counts = d["main_instrument"].value_counts()
    top_inst = [i for i in inst_counts.index[:13] if i != "Acoustic Guitar"]
    blocks["instrument"] = dummies(d["main_instrument"], top_inst, "instrument:")
    genres = ["Rock", "Electro", "Blues", "Folk Rock", "Acapella", "Country"]
    blocks["genre"] = dummies(d["genre"], genres, "genre:")
    blocks["genre"]["genre:Other"] = (~d["genre"].isin(genres + ["Folk"])).astype(float)
    blocks["traveling"] = pd.DataFrame({"traveling": d["traveling"]}, index=d.index)
    blocks["weekday"] = dummies(d["weekday"], analyze.WEEKDAYS[1:], "weekday:")
    blocks["news_song"] = pd.DataFrame({"news_song": d["news_song"]}, index=d.index)
    blocks["beard"] = dummies(d["beard"].fillna(""), ["Shadow", "Clean"], "beard:")
    blocks["beard"]["beard:Other"] = (~d["beard"].isin(["Beard", "Shadow", "Clean"])).astype(float)
    if extra is not None:
        blocks["extra"] = extra
    feats = pd.concat([month] + list(blocks.values()), axis=1)
    # drop all-zero columns (can happen in subsets)
    feats = feats.loc[:, feats.abs().sum() > 0]
    idx = {b: [list(feats.columns).index(c) for c in bdf.columns if c in feats.columns]
           for b, bdf in blocks.items()}
    return feats, idx


BLOCKS = ["topic", "mood", "length", "genre", "instrument", "traveling", "news_song", "beard",
          "weekday"]


def fit(d, y, clusters, extra=None, label=""):
    X, idx = design(d, extra)
    b, hc, cl, _ = ols_cluster(X.values, y, clusters)
    out = {}
    for bn in BLOCKS:
        out[bn] = (block_wald(b, hc, idx[bn])[1], block_wald(b, cl, idx[bn])[1])
    return X, b, idx, out


def main():
    """Run every check above and print the results."""
    y = d.log_views.values
    print("block p-values (HC1 as in findings | cluster by month | cluster by year):")
    X, b, idx, by_month = fit(d, y, d.year_month.values)
    _, _, _, by_year = fit(d, y, d.year.values)
    for bn in BLOCKS:
        print(f"  {bn:<11} HC1 {fmt(by_month[bn][0]):>8} | month {fmt(by_month[bn][1]):>8} | "
              f"year {fmt(by_year[bn][1]):>8}")

    # Channel and age-within-month
    d["age_in_month"] = d.days_online - d.groupby("year_month").days_online.transform("mean")
    extra = pd.concat([pd.get_dummies(d.yt_channel, prefix="ch", dtype=float).iloc[:, 1:],
                       d[["age_in_month"]].fillna(0)], axis=1)
    _, _, _, r = fit(d, y, d.year_month.values, extra=extra)
    print("\n+ channel dummies + age within month (month-clustered p):",
          {bn: fmt(r[bn][1]) for bn in BLOCKS})

    cut = d.views.quantile(0.99)
    m = (d.views < cut).values
    dd = d[m]
    _, _, _, r = fit(dd, dd.log_views.values, dd.year_month.values)
    print("drop top 1% views (month-clustered p):", {bn: fmt(r[bn][1]) for bn in BLOCKS})
    rank = d.groupby("year_month").log_views.rank(pct=True).values
    _, _, _, r = fit(d, rank, d.year_month.values)
    print("within-month percentile rank as outcome (month-clustered p):",
          {bn: fmt(r[bn][1]) for bn in BLOCKS})

    print("\nsplit-sample replication (month-clustered p; key multipliers):")
    halves = {}
    for lab, mm in [("2009-2016", d.year <= 2016), ("2017-2026", d.year >= 2017)]:
        dd = d[mm.values]
        X, b, idx, r = fit(dd, dd.log_views.values, dd.year_month.values)
        cols = list(X.columns)
        get = lambda nm: 10 ** b[cols.index(nm)] if nm in cols else float("nan")
        halves[lab] = {nm: get(nm) for nm in cols if ":" in nm or nm.startswith("log2")}
        print(f"  {lab}: " + ", ".join(f"{bn} {fmt(r[bn][1])}" for bn in BLOCKS))
        print(f"     Silly x{get('mood:Silly'):.2f} Excited x{get('mood:Excited'):.2f} "
              f"Angry x{get('mood:Angry'):.2f} | Rock x{get('genre:Rock'):.2f} "
              f"Electro x{get('genre:Electro'):.2f} | Apple x{get('topic:Apple'):.2f} "
              f"Conference x{get('topic:Conference'):.2f} Commission x{get('topic:Commission'):.2f} "
              f"| log2 length x{get('log2_length'):.2f} | Clean x{get('beard:Clean'):.2f}")
    common = [k for k in halves["2009-2016"] if k in halves["2017-2026"]]
    for pre in ["topic:", "mood:", "genre:", "instrument:"]:
        ks = [k for k in common if k.startswith(pre)]
        a = np.log10([halves["2009-2016"][k] for k in ks])
        c = np.log10([halves["2017-2026"][k] for k in ks])
        print(f"  {pre:<12} correlation of log multipliers between halves: "
              f"r={np.corrcoef(a, c)[0, 1]:+.2f} over {len(ks)} terms")

    print("\nlength, within-month binned (mean log views minus month mean -> multiplier):")
    d["resid"] = d.log_views - d.groupby("year_month").log_views.transform("mean")
    bins = [0, 60, 90, 120, 150, 180, 240, 300, 480, 10000]
    g = d.groupby(pd.cut(d.length_raw, bins)).resid.agg(["mean", "count"])
    print("  " + "; ".join(f"{iv}: x{10 ** row['mean']:.2f} (n={int(row['count'])})"
                           for iv, row in g.iterrows()))
    dd = d[d.length_raw > 60]
    X, b, idx, r = fit(dd, dd.log_views.values, dd.year_month.values)
    j = list(X.columns).index("log2_length")
    print(f"  songs over 60 s only: log2 length x{10 ** b[j]:.2f}, block month-clustered p="
          f"{fmt(r['length'][1])}")
    print("  correlation of length with year:", round(np.corrcoef(d.length_raw, d.year)[0, 1], 3),
          "| median length by era:", d.groupby("home_era").length_raw.median().to_dict())


if __name__ == "__main__":
    main()
