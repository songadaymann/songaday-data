"""Skeptic check: "Are weekend songs mellower?" (weekend_wild) and "Does the day of the week
change the mood mix?" (weekday_mood).

Confounds tried:
  1. Slow drift in tagging: compare weekend with weekdays inside the same calendar week, so
     anything that changes over weeks or months cancels. Test across weeks with a t-test and
     a sign test (each week is one independent-ish unit, which also handles mood runs that
     make neighbouring days alike).
  2. Travel: gigs and family visits fall on weekends. Hold traveling fixed, and look at home
     songs only.
  3. Work songs: commissions, conferences, Apple keynotes and news songs are weekday events
     and skew Silly/Excited. Drop those topics and news songs.
  4. Source switch: the sheet (#1-#5101) and catalog-only (#5102 on) parts separately, and
     each home era and each year.
"""

import numpy as np
import pandas as pd
from scipy import stats

from check_1_common import analyze, codes, fmt, load, mh_diff, perm_p

df = load()
df["iso_week"] = df["date"].dt.strftime("%G-%V")


def within_week(d, y="wild"):
    """Per ISO week: weekend share minus weekday share; mean, t-test and sign test."""
    g = d.groupby(["iso_week", "weekend"])[y].mean().unstack()
    g = g.dropna()
    diff = g[1.0] - g[0.0]
    t = stats.ttest_1samp(diff, 0)
    neg, pos = int((diff < 0).sum()), int((diff > 0).sum())
    sign = stats.binomtest(neg, neg + pos).pvalue
    return diff.mean(), diff.std() / np.sqrt(len(diff)), t.pvalue, neg, pos, sign, len(diff)


print("== weekend_wild ==")
s = codes(df, analyze.DAILY)
print(f"reproduced MH diff (year x era): {100 * mh_diff(df.weekend, df.wild, s):+.2f} points "
      f"(findings: -10.4)")
m, se, p, neg, pos, sp, nw = within_week(df)
print(f"within ISO week ({nw} weeks): {100 * m:+.2f} points (SE {100 * se:.2f}), t p={fmt(p)}; "
      f"weeks weekend lower {neg} vs higher {pos} (sign p={fmt(sp)})")

for label, strata in [("year x era x traveling", analyze.DAILY + ["traveling"]),
                      ("year-month x traveling", ["year", "month", "traveling"])]:
    obs, pp, _ = perm_p(df.weekend.values, df.wild.values, codes(df, strata), n_perm=999)
    print(f"strata {label}: {100 * obs:+.2f} points, perm p={fmt(pp)}")

home = df[df.is_home == 1]
obs, pp, _ = perm_p(home.weekend.values, home.wild.values, codes(home, analyze.DAILY), 999)
print(f"home songs only (n={len(home)}): {100 * obs:+.2f} points, perm p={fmt(pp)}")

WORK = {"Commission", "Conference", "Apple", "News", "Politics", "Trump", "Crypto", "NFT",
        "Technology", "Work", "Business", "Internet"}
work = df.topics.apply(lambda ts: bool(WORK & set(ts))) | (df.news_song == 1)
print(f"\nwork/news-ish songs: {work.mean():.1%} of weekday songs? "
      f"weekday {work[df.weekend == 0].mean():.1%}, weekend {work[df.weekend == 1].mean():.1%}")
rest = df[~work]
obs, pp, _ = perm_p(rest.weekend.values, rest.wild.values, codes(rest, analyze.DAILY), 999)
print(f"dropping work/news topics (n={len(rest)}): {100 * obs:+.2f} points, perm p={fmt(pp)}")
m, se, p, neg, pos, sp, nw = within_week(rest)
print(f"  and within ISO week: {100 * m:+.2f} points, t p={fmt(p)}")

# Topic mix by weekend: which topics differ most (share of songs with that topic)
tops = pd.Series([t for ts in df.topics for t in ts]).value_counts()
tops = [t for t in tops.index if tops[t] >= 60]
rows = []
for t in tops:
    has = df.topics.apply(lambda ts: t in ts)
    rows.append((t, has[df.weekend == 0].mean(), has[df.weekend == 1].mean()))
rows.sort(key=lambda r: r[2] / max(r[1], 1e-9))
print("topics most weekday-heavy:", [(t, f"{a:.1%}", f"{b:.1%}") for t, a, b in rows[:6]])
print("topics most weekend-heavy:", [(t, f"{a:.1%}", f"{b:.1%}") for t, a, b in rows[-6:]])

print("\nby era (within-week diff, points):")
for era in analyze.ERAS:
    m, se, p, neg, pos, sp, nw = within_week(df[df.home_era == era])
    print(f"  {era:<12} {100 * m:+6.2f} (SE {100 * se:.2f}) p={fmt(p)} weeks={nw}")
for lab, sub in [("sheet #1-#5101", df[df.number <= 5101]),
                 ("catalog only #5102+", df[df.number > 5101])]:
    m, se, p, neg, pos, sp, nw = within_week(sub)
    print(f"  {lab:<20} {100 * m:+6.2f} (SE {100 * se:.2f}) p={fmt(p)} weeks={nw}")
yr = []
for y_, sub in df.groupby("year"):
    yr.append(100 * mh_diff(sub.weekend, sub.wild, np.zeros(len(sub), int)))
yr = np.array(yr)
print(f"years with weekend lower: {(yr < 0).sum()} of {len(yr)}; per-year diffs: "
      f"{np.round(yr, 1).tolist()}")

# Which moods carry the effect
print("\nmood shares weekday vs weekend:")
tab = pd.crosstab(df.mood12, df.weekend, normalize="columns")
tab["ratio"] = tab[1.0] / tab[0.0]
print(tab.sort_values("ratio").round(3).to_string())

print("\n== weekday_mood ==")
# Within-week version: chi-square of weekday x mood with expected counts within ISO week
spec = next(t for t in analyze.TESTS if t["id"] == "weekday_mood")
res = analyze.run_permutation(spec, df, analyze.DAILY, 999)
print(f"reproduced (year x era) p={fmt(res['p'])}")
res = analyze.run_permutation(spec, df, ["iso_week"], 999)
print(f"strata = ISO week (each day only against its own week): p={fmt(res['p'])}")
res = analyze.run_permutation(spec, df, analyze.DAILY + ["traveling"], 999)
print(f"strata = year x era x traveling: p={fmt(res['p'])}")
d2 = df[df.weekend == 0]
spec5 = dict(spec, x_order=analyze.WEEKDAYS[:5])
res = analyze.run_permutation(spec5, d2, analyze.DAILY, 999)
print(f"Monday-Friday only (is it more than the weekend split?): p={fmt(res['p'])}")
res = analyze.run_permutation(spec, rest, analyze.DAILY, 999)
print(f"dropping work/news topics: p={fmt(res['p'])}")
