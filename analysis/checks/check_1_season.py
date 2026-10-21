"""Skeptic check: "Does the season change the mood mix?" (season_mood, probably real,
q = 0.0496, biggest cell winter x Tired 80 vs 115 expected).

q sits right at the 0.05 line, so small, fair changes matter. Confounds tried:
  1. Seed and shuffle count: rerun the same test with other seeds.
  2. Travel: trips cluster in summer and around the holidays, and travel changes the mood
     mix (travel_mood). Hold traveling fixed, and home songs only.
  3. The holidays: Christmas and New Year songs, and family visits, in December/January.
     Drop December, and drop the Christmas topic.
  4. Era: is the pattern the same in each half of the timeline? Compare the season x mood
     departures (observed minus expected within year) between 2009-2017 and 2018-2026.
  5. Berkeley has no real winter: drop the Berkeley era.
"""

import numpy as np
import pandas as pd

from check_1_common import analyze, fmt, load

df = load()
spec = next(t for t in analyze.TESTS if t["id"] == "season_mood")


def run(d, strata=("year",), n=4999, seed="", block_strata=("year",)):
    s = dict(spec, strata=list(strata), block_strata=list(block_strata))
    res = analyze.run_permutation(s, d, list(strata), n, seed_suffix=seed)
    _, _, st = analyze.describe(s, res)
    bc = st["biggest_cell"]
    return res, st, (f"p={fmt(res['p'])} V={st['cramers_v']:.3f} (chance "
                     f"{st['cramers_v_chance']:.3f}); {bc['x']} x {bc['y']} {bc['observed']} vs "
                     f"{bc['expected']:.0f}")


print("reproduced:", run(df)[2])
for seed in [":a", ":b", ":c", ":d"]:
    print(f"  other seed {seed}: {run(df, seed=seed)[2]}")
print("strata year x traveling:", run(df, ("year", "traveling"),
                                      block_strata=("year", "traveling"))[2])
print("home songs only:", run(df[df.is_home == 1])[2])
print("drop December:", run(df[df.month != 12])[2])
xmas = df.topics.apply(lambda ts: "Christmas" in ts)
print("drop Christmas topic:", run(df[~xmas])[2])
print("drop Berkeley era:", run(df[df.home_era != "berkeley"])[2])
print("2009-2017:", run(df[df.year <= 2017])[2])
print("2018-2026:", run(df[df.year >= 2018])[2])


def departures(d):
    """Observed minus expected (within year) share of each mood in each season."""
    t = pd.crosstab([d.year, d.season], d.mood12)
    exp = []
    for yr, block in t.groupby(level=0):
        p = block.sum(axis=0) / block.values.sum()
        exp.append(pd.DataFrame(np.outer(block.sum(axis=1), p), index=block.index,
                                columns=block.columns))
    e = pd.concat(exp)
    o = t.groupby(level=1).sum()
    e = e.groupby(level=1).sum()
    return ((o - e) / e.sum(axis=1).values[:, None]).reindex(analyze.SEASONS)


a = departures(df[df.year <= 2017])
b = departures(df[df.year >= 2018])
r = np.corrcoef(a.values.ravel(), b.values.ravel())[0, 1]
print(f"\ncorrelation of season x mood departures, 2009-2017 vs 2018-2026: r = {r:+.2f}")
print("winter Tired departure (share points): early "
      f"{100 * a.loc['winter', 'Tired']:+.2f}, late {100 * b.loc['winter', 'Tired']:+.2f}")
print("by season, Tired share:", (pd.crosstab(df.season, df.mood12, normalize="index")["Tired"]
                                  * 100).round(1).to_dict())

# 6. Adjacent-month drift. The block null shuffles single months within a year, so any
#    mood drift that lasts a few months makes three neighbouring months look alike and
#    inflates a "season" made of neighbouring months. Null here: per year, rotate the
#    month -> season map by a random 0-11 months (seasons stay three consecutive months,
#    drift is kept, only the label "winter" moves). Seasonality survives; drift doesn't.
SEASON_OF = {12: 0, 1: 0, 2: 0, 3: 1, 4: 1, 5: 1, 6: 2, 7: 2, 8: 2, 9: 3, 10: 3, 11: 3}
moods = analyze.MOOD_ORDER
years = sorted(df.year.unique())
C = np.zeros((len(years), 12, len(moods)))
for i, yr in enumerate(years):
    t = pd.crosstab(df.month[df.year == yr], df.mood12[df.year == yr]).reindex(
        index=range(1, 13), columns=moods, fill_value=0)
    C[i] = t.values


def chi2_for(rot):
    O = np.zeros((4, len(moods)))
    E = np.zeros((4, len(moods)))
    for i in range(len(years)):
        seas = np.array([SEASON_OF[((m - 1 + rot[i]) % 12) + 1] for m in range(1, 13)])
        S = np.zeros((4, len(moods)))
        np.add.at(S, seas, C[i])
        n = S.sum()
        if n == 0:
            continue
        O += S
        E += np.outer(S.sum(1), S.sum(0)) / n
    with np.errstate(divide="ignore", invalid="ignore"):
        return float(np.where(E > 0, (O - E) ** 2 / E, 0).sum())


obs = chi2_for(np.zeros(len(years), int))
rng = np.random.default_rng(11)
null = np.array([chi2_for(rng.integers(0, 12, len(years))) for _ in range(2999)])
print(f"\nrotation null (seasons = 3 consecutive months, label moved at random per year): "
      f"chi2 {obs:.1f}, p={fmt((1 + (null >= obs).sum()) / (len(null) + 1))} "
      f"(null median {np.median(null):.1f})")
