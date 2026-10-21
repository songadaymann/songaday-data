"""Skeptic check: the two beard findings.
  beard_views  "Does the beard get more views?"  (Clean +24% within month)
  beard_mood   "Does the beard change the mood?" (V = 0.084 within year x era)

What the beard column really is: 2009-2014 it alternates Clean/Shadow every few days (a
shaving cycle: 737 Clean runs, median 2 days); 2015-2016 mostly Beard; 2017-2021
Shadow/Clean again; from 2022 on almost every song is Beard. So within a month "Clean" vs
"Shadow" is mostly "did he shave today". Confounds tried:
  1. Where the variation is: count the months that have more than one beard state; the
     effect can only come from those.
  2. Occasion: he may shave for gigs, shoots, commissions and trips. Hold travel, weekday,
     topic and the views-model features fixed; drop event topics.
  3. Viral outliers: drop the top 1% of songs by views; use within-month ranks.
  4. Independence: a few months or one era could carry it. Leave one era out, and use a
     sign test over months (each month one vote: do its Clean songs beat its others?).
  5. Neighbouring days: compare each Clean song only with the songs of the 3 days on either
     side (a matched comparison that also controls for anything that moves week to week).
"""

import numpy as np
import pandas as pd
from scipy import stats

from check_1_common import analyze, block_wald, codes, fmt, load, mh_diff, ols_cluster

df = load()
v = df[df.log_views.notna() & df.beard3.notna()].copy()

print("== beard_views ==")
spec = next(t for t in analyze.TESTS if t["id"] == "beard_views")
res = analyze.run_permutation(spec, df, analyze.MONTHLY, 999)
_, _, st = analyze.describe(spec, res)
print("reproduced: p", fmt(res["p"]), {k: round(100 * (10 ** (g["adjusted_mean"] - res["y"].mean()) - 1))
                                      for k, g in st["groups"].items()})
mixed = v.groupby("year_month").beard3.nunique()
print(f"months with >1 beard state: {(mixed > 1).sum()} of {len(mixed)}; "
      f"songs in them: {v.year_month.map(mixed).gt(1).sum()}")
print("months with >1 state, by year:", v[v.year_month.map(mixed) > 1].groupby("year")
      .year_month.nunique().to_dict())

v["clean"] = (v.beard3 == "Clean").astype(float)
S = codes(v, analyze.MONTHLY)
pct = lambda e: f"{100 * (10 ** e - 1):+.1f}%"
print(f"Clean vs not-Clean within month (MH): {pct(mh_diff(v.clean, v.log_views, S))}")
sub = v[v.beard3 != "Beard"]
print(f"Clean vs Shadow only, within month: "
      f"{pct(mh_diff(sub.clean, sub.log_views, codes(sub, analyze.MONTHLY)))}")
for lab, strata in [("month x traveling", analyze.MONTHLY + ["traveling"]),
                    ("month x weekday", analyze.MONTHLY + ["weekday"]),
                    ("month x channel", analyze.MONTHLY + ["yt_channel"])]:
    print(f"strata {lab}: {pct(mh_diff(v.clean, v.log_views, codes(v, strata)))}")
EVENT = {"Conference", "Commission", "Collab Month", "Contest", "Kickstarter", "Podcast",
         "Birthday", "Song A Day"}
ev = v.topics.apply(lambda ts: bool(EVENT & set(ts)))
print(f"event topics: Clean {ev[v.clean == 1].mean():.1%} vs others {ev[v.clean == 0].mean():.1%}")
sub = v[~ev & (v.news_song == 0)]
print(f"dropping event topics and news songs: "
      f"{pct(mh_diff(sub.clean, sub.log_views, codes(sub, analyze.MONTHLY)))}")
cut = v.views.quantile(0.99)
sub = v[v.views < cut]
print(f"dropping top 1% (> {cut:,.0f} views): "
      f"{pct(mh_diff(sub.clean, sub.log_views, codes(sub, analyze.MONTHLY)))}")
v["rank"] = v.groupby("year_month").log_views.rank(pct=True)
print(f"within-month percentile rank: Clean {v[v.clean == 1]['rank'].mean():.3f} vs "
      f"others {v[v.clean == 0]['rank'].mean():.3f} (MH diff "
      f"{mh_diff(v.clean, v['rank'], S):+.3f})")
for era in analyze.ERAS:
    sub = v[v.home_era != era]
    print(f"  leave out {era:<12}: {pct(mh_diff(sub.clean, sub.log_views, codes(sub, analyze.MONTHLY)))}")
    sub = v[v.home_era == era]
    if sub.clean.nunique() > 1:
        print(f"  only {era:<17}: {pct(mh_diff(sub.clean, sub.log_views, codes(sub, analyze.MONTHLY)))}"
              f" (Clean n={int(sub.clean.sum())})")

# Sign test across months
g = v.groupby(["year_month", "clean"]).log_views.mean().unstack().dropna()
d = g[1.0] - g[0.0]
print(f"months where Clean songs beat the rest: {(d > 0).sum()} of {len(d)} "
      f"(sign p={fmt(stats.binomtest(int((d > 0).sum()), len(d)).pvalue)}); "
      f"mean month diff {pct(d.mean())}, t p={fmt(stats.ttest_1samp(d, 0).pvalue)}")

# Matched neighbours: each Clean song against the non-Clean songs within 3 days
lv = df.set_index("number").log_views
b3 = df.set_index("number").beard3
diffs = []
for n in v.number[v.clean == 1]:
    nb = [m for m in range(n - 3, n + 4) if m != n and m in lv.index
          and pd.notna(lv[m]) and pd.notna(b3[m]) and b3[m] != "Clean"]
    if nb:
        diffs.append(lv[n] - lv[nb].mean())
diffs = np.array(diffs)
print(f"Clean vs non-Clean neighbours within 3 days: {pct(diffs.mean())} "
      f"(n={len(diffs)}, t p={fmt(stats.ttest_1samp(diffs, 0).pvalue)}, "
      f"median {pct(np.median(diffs))})")

# Views model with month FE, clustered by month
d = df[df.log_views.notna() & df.length_raw.notna()].copy()
month = pd.get_dummies(d.year_month, dtype=float)
feats = [month,
         pd.get_dummies(d.mood12, prefix="m", dtype=float).drop(columns="m_Pensive"),
         pd.DataFrame({"tr": d.traveling, "ns": d.news_song,
                       "ll": np.log2(d.length_raw.clip(30, 600))}, index=d.index),
         pd.get_dummies(d.weekday, prefix="w", dtype=float).drop(columns="w_Monday")]
topc = pd.Series([t for ts in d.topics for t in ts]).value_counts()
for t in [t for t in topc.index if topc[t] >= 30][:30]:
    feats.append(pd.DataFrame({f"t_{t}": d.topics.apply(lambda ts: float(t in ts))}, index=d.index))
bd = pd.DataFrame({"Shadow": (d.beard == "Shadow").astype(float),
                   "Clean": (d.beard == "Clean").astype(float),
                   "Other": (~d.beard.isin(["Beard", "Shadow", "Clean"])).astype(float)},
                  index=d.index)
X = pd.concat(feats + [bd], axis=1)
b, hc, cl, _ = ols_cluster(X.values, d.log_views.values, d.year_month.values)
idx = [list(X.columns).index(c) for c in bd.columns]
j = list(X.columns).index("Clean")
print(f"views model (month FE, mood, topic, travel, news, length, weekday): Clean "
      f"x{10 ** b[j]:.2f}; block p HC1={fmt(block_wald(b, hc, idx)[1])}, "
      f"month-cluster={fmt(block_wald(b, cl, idx)[1])}")
# 2009-2021 only (where the beard varies)
m = (d.year <= 2021).values
b2, hc2, cl2, _ = ols_cluster(X.values[m], d.log_views.values[m], d.year_month.values[m])
print(f"  same, 2009-2021 only: Clean x{10 ** b2[j]:.2f}, month-cluster p="
      f"{fmt(block_wald(b2, cl2, idx)[1])}")

print("\n== beard_mood ==")
spec = next(t for t in analyze.TESTS if t["id"] == "beard_mood")
for lab, d_, strata, null in [
        ("reproduced", df, analyze.DAILY, "shift"),
        ("strata year-month", df, ["year", "month"], "shift"),
        ("strata year x era x traveling", df, analyze.DAILY + ["traveling"], "shift"),
        ("2009-2014 only", df[df.year <= 2014], analyze.DAILY, "shift"),
        ("2015-2021 only", df[(df.year >= 2015) & (df.year <= 2021)], analyze.DAILY, "shift"),
        ("Clean vs Shadow only", df[df.beard3.isin(["Clean", "Shadow"])], analyze.DAILY,
         "shift")]:
    s2 = dict(spec, null=null)
    if lab == "Clean vs Shadow only":
        s2["x_order"] = ["Shadow", "Clean"]
    res = analyze.run_permutation(s2, d_, strata, 1999)
    _, _, st = analyze.describe(dict(s2, strata=strata), res)
    bc = st["biggest_cell"]
    print(f"  {lab:<30} p={fmt(res['p'])} V={st['cramers_v']:.3f} (chance "
          f"{st['cramers_v_chance']:.3f}); {bc['x']} x {bc['y']} {bc['observed']} vs "
          f"{bc['expected']:.0f}")
# Is it the same pattern in both halves? Clean minus Shadow share of Tired and Silly.
for lab, sub in [("2009-2014", df[df.year <= 2014]), ("2015-2021", df[(df.year >= 2015) & (df.year <= 2021)])]:
    t = pd.crosstab(sub.beard3, sub.mood12, normalize="index")
    print(f"  {lab}: Tired Clean {t.loc['Clean', 'Tired']:.3f} vs Shadow {t.loc['Shadow', 'Tired']:.3f}; "
          f"Silly Clean {t.loc['Clean', 'Silly']:.3f} vs Shadow {t.loc['Shadow', 'Silly']:.3f}")
