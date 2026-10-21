"""Skeptic check: the two findings that are really about time.
  trend_dark  "Are the moods getting darker over time?"  (+8.4 points per decade)
  era_mood    "Did the mood mix change between homes?"   (V = 0.146, q = 0.0075)

Confounds tried:
  trend_dark
    1. Vocabulary drift: when each dark mood first appears, and whether the trend survives
       with only the moods used in every year (Sad, Angry, Anxious).
    2. Relabeling: Intense (a high-energy mood, not counted as dark) fell from 69 songs in
       2009 to about 10-30 later while Angry rose. If early angry songs were tagged Intense,
       dark + Intense should be flat.
    3. Politics: Angry songs may be political songs. Drop Politics/Trump topics.
    4. The source switch at #5102 (sheet + catalog before, catalog only after) and the
       partial year 2026.
  era_mood
    5. Is it the move, or just time? The circular-shift null wraps the timeline, so its
       fake "eras" mix 2026 with 2009 and can't carry a slow trend. Here the null is random
       contiguous 4-segment partitions that do not wrap (each segment at least a year),
       which keep a slow trend. If the real era boundaries are not special against those,
       the "era" effect is just drift (in mood or in tagging).
    6. Local jumps: the mood mix in the 180 songs before vs after each move, against the
       same comparison at random dates.
"""

import numpy as np
import pandas as pd
from scipy import stats

from check_1_common import analyze, fmt, load

df = load()


def trend(col_or_series, label):
    s = col_or_series
    yearly = s.groupby(df.year).mean()
    tau, p = stats.kendalltau(yearly.index, yearly.values)
    fit = stats.linregress(yearly.index, yearly.values)
    print(f"  {label:<44} slope {1000 * fit.slope:+5.1f} pts/decade, tau {tau:+.2f}, "
          f"Kendall p={fmt(p)}; 2009 {100 * yearly.iloc[0]:.1f}% -> 2026 {100 * yearly.iloc[-1]:.1f}%")
    return yearly


print("== trend_dark ==")
first = {m: int(df.year[df.mood == m].min()) for m in analyze.DARK_MOODS if (df.mood == m).any()}
print("first year each dark mood is used:", dict(sorted(first.items(), key=lambda kv: kv[1])))
print("distinct moods per year:", df.groupby("year").mood.nunique().to_dict())
trend(df.dark, "dark (as in findings)")
trend(df.mood.isin({"Sad", "Angry", "Anxious"}).astype(float), "only Sad, Angry, Anxious")
trend((df.mood == "Sad").astype(float), "Sad alone")
trend((df.mood == "Angry").astype(float), "Angry alone")
trend((df.mood == "Intense").astype(float), "Intense alone")
trend((df.dark == 1) | (df.mood == "Intense"), "dark + Intense (relabeling check)")
trend((df.mood.isin({"Angry", "Intense"})).astype(float), "Angry + Intense")
nopol = df.politics_topic == 0
s = df.dark.where(nopol)
yearly = s.groupby(df.year).mean()
tau, p = stats.kendalltau(yearly.index, yearly.values)
fit = stats.linregress(yearly.index, yearly.values)
print(f"  {'dark, Politics/Trump songs dropped':<44} slope {1000 * fit.slope:+5.1f} pts/decade, "
      f"tau {tau:+.2f}, Kendall p={fmt(p)}")
print(f"  dark share of Politics/Trump songs {df.dark[~nopol].mean():.1%} vs others "
      f"{df.dark[nopol].mean():.1%}; politics share by year: "
      f"{(df.politics_topic.groupby(df.year).mean() * 100).round(0).astype(int).to_dict()}")
# without 2026 (partial) and before the source switch
y = df.dark.groupby(df.year).mean()
for lab, yy in [("2009-2025", y.loc[:2025]), ("2009-2021 (all sheet)", y.loc[:2021])]:
    tau, p = stats.kendalltau(yy.index, yy.values)
    fit = stats.linregress(yy.index, yy.values)
    print(f"  dark, {lab:<38} slope {1000 * fit.slope:+5.1f} pts/decade, Kendall p={fmt(p)}")
# Break vs trend: is it a step around 2016-2017?
pre, post = y.loc[2009:2015], y.loc[2017:2026]
print(f"  yearly dark share 2009-2015 mean {100 * pre.mean():.1f}% (trend tau "
      f"{stats.kendalltau(pre.index, pre.values)[0]:+.2f}), 2017-2026 mean "
      f"{100 * post.mean():.1f}% (trend tau {stats.kendalltau(post.index, post.values)[0]:+.2f}, "
      f"p={fmt(stats.kendalltau(post.index, post.values)[1])})")
print("  yearly dark %:", (100 * y).round(1).to_dict())

print("\n== era_mood ==")
spec = next(t for t in analyze.TESTS if t["id"] == "era_mood")
res = analyze.run_permutation(spec, df, [], 1999)
print(f"reproduced with circular shift: p={fmt(res['p'])}, chi2={res['observed']:.1f}")
sub = res["sub"]
y = res["y"]
x = res["x"]
f = analyze.make_statistic("assoc", y, np.zeros(len(y), int), n_x=4, n_y=12)
obs = float(f(x[None, :])[0])
n = len(y)
rng = np.random.default_rng(5)
sizes = np.bincount(x)
null = []
for _ in range(2999):
    # three random cut points, every segment at least 365 songs, no wrap-around
    while True:
        cuts = np.sort(rng.integers(365, n - 365, size=3))
        if np.all(np.diff(np.r_[0, cuts, n]) >= 365):
            break
    lab = np.searchsorted(cuts, np.arange(n), side="right")
    null.append(float(f(lab[None, :])[0]))
null = np.array(null)
p_nowrap = (1 + np.sum(null >= obs)) / (len(null) + 1)
print(f"null = random non-wrapping 4-segment partitions: p={fmt(p_nowrap)} "
      f"(real chi2 {obs:.1f}; null median {np.median(null):.1f}, 95th pct "
      f"{np.quantile(null, 0.95):.1f})")
# Same, but the segments keep the real era lengths in the real order, placed at a random
# offset with no wrap (shorter null space; offsets limited by the series length)
# -> equivalent to sliding the boundaries together; skip, the random-cut null covers it.

# Local jumps at each move
bounds = [1041, 2180, 4215]
W = 180


def local_chi2(center):
    before = (df.number >= center - W) & (df.number < center)
    after = (df.number >= center) & (df.number < center + W)
    t = pd.crosstab(np.where(before[before | after], 0, 1),
                    df.mood12[before | after])
    return stats.chi2_contingency(t)[0]


real = [local_chi2(b) for b in bounds]
rand_centres = rng.integers(W + 1, df.number.max() - W, size=600)
rnd = np.array([local_chi2(c) for c in rand_centres])
for b, c in zip(bounds, real):
    print(f"  move at #{b}: chi2 {c:.1f}, percentile among random dates "
          f"{100 * (rnd < c).mean():.0f}")
print(f"  mean chi2 at the 3 moves {np.mean(real):.1f} vs random-date mean {rnd.mean():.1f}; "
      f"p (mean of 3 random dates >= real) ="
      f" {fmt((1 + sum(rng.choice(rnd, 3).mean() >= np.mean(real) for _ in range(4999))) / 5000)}")
