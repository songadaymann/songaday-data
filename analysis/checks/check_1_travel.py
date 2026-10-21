"""Skeptic check: the three travel findings.
  travel_length  "Are songs on the road longer or shorter?"  (+17.3 s like-for-like)
  travel_views   "Do songs from the road get more views?"    (-28% within month)
  travel_mood    "Does traveling change the mood mix?"       (probably real, q = 0.0285)

"Traveling" is anything not in his home town, so it mixes very different things. Confounds
tried:
  1. What kind of trip: family homes (Avon, Canton, Southington CT, Severna Park MD), the
     between-homes stretches and the spring-2020 family stay, places under 30 km from home,
     named studios, and real trips (over 100 km, not family).
  2. Production: studio and band songs run long; hold genre and main instrument fixed.
  3. Event songs: Conference, Commission, Gig, Collaboration topics.
  4. Finer time strata (year-month), and cluster-robust regression with trips as clusters
     (consecutive travel days at one place = one trip), since one long trip is many
     non-independent songs.
  5. For views: the YouTube channel, age within the month, and the views-model features.
"""

import numpy as np
import pandas as pd

from check_1_common import analyze, block_wald, codes, fmt, load, mh_diff, ols_cluster, shift_p

df = load()

HOMES = {"berkeley": (37.8716, -122.2727), "brooklyn": (40.6782, -73.9442),
         "jersey_city": (40.7178, -74.0431), "hartford": (41.7658, -72.6734)}
FAMILY = {"Avon, CT", "Canton, CT", "Southington, CT", "Severna Park, MD"}


def km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    a = (np.sin((lat2 - lat1) / 2) ** 2
         + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2)
    return 6371 * 2 * np.arcsin(np.sqrt(a))


df["dist_km"] = [km(la, lo, *HOMES[e]) for la, lo, e in
                 zip(df.place_lat, df.place_lon, df.home_era)]
covid_family = (df.date >= "2020-05-01") & (df.date <= "2020-07-31") & (df.traveling == 1)


def trip_kind(r):
    if r.traveling != 1:
        return "home"
    if r.between == 1 or (pd.Timestamp("2020-05-01") <= r.date <= pd.Timestamp("2020-07-31")):
        return "between/2020 stay"
    if r.place_kind == "studio":
        return "studio"
    if r.place in FAMILY:
        return "family"
    if r.dist_km < 30:
        return "near (<30 km)"
    if r.dist_km < 100:
        return "30-100 km"
    return "trip >100 km"


df["trip_kind"] = df.apply(trip_kind, axis=1)
# Trip id: a run of consecutive traveling songs at the same place (home songs are their own
# cluster, one per month, so the regression clusters are trips and home-months).
run = ((df.traveling != df.traveling.shift()) | (df.place != df.place.shift())).cumsum()
df["cluster"] = np.where(df.traveling == 1, "trip" + run.astype(str), "home" + df.year_month)
print("songs by trip kind:", df.trip_kind.value_counts().to_dict())
print("distinct trips (runs):", df[df.traveling == 1].cluster.nunique())

S = codes(df, analyze.DAILY)
print("\n== travel_length ==")
print(f"reproduced: {mh_diff(df.traveling, df.length, S):+.2f} s (findings +17.3)")
for kind in ["between/2020 stay", "family", "studio", "near (<30 km)", "30-100 km",
             "trip >100 km"]:
    sub = df[(df.trip_kind == "home") | (df.trip_kind == kind)]
    n1 = int((sub.trip_kind == kind).sum())
    print(f"  {kind:<18} n={n1:<4} {mh_diff(sub.traveling, sub.length, codes(sub, analyze.DAILY)):+6.1f} s")

# Event topics
EVENT = {"Conference", "Commission", "Gig", "Collaboration", "Collab", "Concert", "Show",
         "Wedding", "Birthday"}
event = df.topics.apply(lambda ts: bool(EVENT & set(ts)))
print(f"event-topic share: traveling {event[df.traveling == 1].mean():.1%}, "
      f"home {event[df.traveling == 0].mean():.1%}")
sub = df[~event]
print(f"dropping event topics: {mh_diff(sub.traveling, sub.length, codes(sub, analyze.DAILY)):+.1f} s")
sub = df[df.trip_kind.isin(["home", "trip >100 km", "family"])]
print(f"home vs (real trips + family) only: "
      f"{mh_diff(sub.traveling, sub.length, codes(sub, analyze.DAILY)):+.1f} s")

for lab, strata in [("year-month", ["year", "month"]),
                    ("year x era x genre", analyze.DAILY + ["genre"]),
                    ("year x era x main instrument", analyze.DAILY + ["main_instrument"])]:
    print(f"strata {lab}: {mh_diff(df.traveling, df.length, codes(df, strata)):+.1f} s")

# Regression: length on traveling with year-month FE, genre and instrument dummies,
# cluster-robust by trip.
d = df.dropna(subset=["length"]).copy()
top_inst = d.main_instrument.value_counts().index[:12]
top_gen = d.genre.value_counts().index[:8]
X = pd.concat([pd.get_dummies(d.year_month, dtype=float),
               pd.get_dummies(d.main_instrument.where(d.main_instrument.isin(top_inst), "o"),
                              prefix="i", drop_first=True, dtype=float),
               pd.get_dummies(d.genre.where(d.genre.isin(top_gen), "o"), prefix="g",
                              drop_first=True, dtype=float),
               d[["traveling"]]], axis=1)
b, hc, cl, _ = ols_cluster(X.values, d.length.values, d.cluster.values)
j = list(X.columns).index("traveling")
print(f"OLS month FE + genre + instrument: {b[j]:+.1f} s, HC1 SE {np.sqrt(hc[j, j]):.1f}, "
      f"trip-cluster SE {np.sqrt(cl[j, j]):.1f}, cluster z={b[j] / np.sqrt(cl[j, j]):.2f}")
# Per era
for era in analyze.ERAS:
    sub = df[df.home_era == era]
    print(f"  era {era:<12} {mh_diff(sub.traveling, sub.length, codes(sub, ['year'])):+6.1f} s "
          f"(travel n={int(sub.traveling.sum())})")

print("\n== travel_views ==")
v = df[df.log_views.notna()].copy()
Sv = codes(v, analyze.MONTHLY)
obs = mh_diff(v.traveling, v.log_views, Sv)
print(f"reproduced: {100 * (10 ** obs - 1):+.1f}% (findings -28%)")
print("channels:", pd.crosstab(v.yt_channel, v.traveling).to_dict())
print(f"strata year-month x channel: "
      f"{100 * (10 ** mh_diff(v.traveling, v.log_views, codes(v, analyze.MONTHLY + ['yt_channel'])) - 1):+.1f}%")
for kind in ["between/2020 stay", "family", "studio", "near (<30 km)", "trip >100 km"]:
    sub = v[(v.trip_kind == "home") | (v.trip_kind == kind)]
    n1 = int((sub.trip_kind == kind).sum())
    e = mh_diff(sub.traveling, sub.log_views, codes(sub, analyze.MONTHLY))
    print(f"  {kind:<18} n={n1:<4} {100 * (10 ** e - 1):+6.1f}%")
sub = v[~event[v.index]]
e = mh_diff(sub.traveling, sub.log_views, codes(sub, analyze.MONTHLY))
print(f"dropping event topics: {100 * (10 ** e - 1):+.1f}%")
sub = v[~covid_family[v.index] & (v.between == 0)]
e, p, _ = shift_p(sub.traveling.values, sub.log_views.values, codes(sub, analyze.MONTHLY),
                  n_perm=999)
print(f"dropping between-homes and the 2020 family stay: {100 * (10 ** e - 1):+.1f}%, "
      f"shift p={fmt(p)}")
# Why does the controlled effect get bigger than the raw one? Months with travel.
mm = v.groupby("year_month").traveling.mean()
v["month_travel_share"] = v.year_month.map(mm)
print("median log-views by month-travel share bucket (raw):",
      v.groupby(pd.cut(v.month_travel_share, [-0.01, 0, 0.25, 0.75, 1.0])).log_views.median()
      .round(3).to_dict())
# Within-month position: days_online relative to the month
v["age_in_month"] = v.days_online - v.groupby("year_month").days_online.transform("mean")
X = pd.concat([pd.get_dummies(v.year_month, dtype=float),
               v[["traveling", "age_in_month"]]], axis=1)
b, hc, cl, _ = ols_cluster(X.values, v.log_views.values, v.cluster.values)
j = list(X.columns).index("traveling")
print(f"OLS month FE + age within month: {100 * (10 ** b[j] - 1):+.1f}%, "
      f"trip-cluster z={b[j] / np.sqrt(cl[j, j]):.2f} (HC1 z={b[j] / np.sqrt(hc[j, j]):.2f})")
for era in analyze.ERAS:
    sub = v[v.home_era == era]
    e = mh_diff(sub.traveling, sub.log_views, codes(sub, analyze.MONTHLY))
    print(f"  era {era:<12} {100 * (10 ** e - 1):+6.1f}% (travel n={int(sub.traveling.sum())})")

print("\n== travel_mood ==")
spec = next(t for t in analyze.TESTS if t["id"] == "travel_mood")
for lab, d_, strata in [
        ("reproduced", df, analyze.DAILY),
        ("+ season", df, analyze.DAILY + ["season"]),
        ("year-month", df, ["year", "month"]),
        ("drop between-homes + 2020 stay", df[~covid_family & (df.between == 0)], analyze.DAILY),
        ("drop family homes", df[df.trip_kind != "family"], analyze.DAILY),
        ("only real trips >100 km vs home", df[df.trip_kind.isin(["home", "trip >100 km"])],
         analyze.DAILY),
        ("drop work/event topics", df[~event], analyze.DAILY)]:
    res = analyze.run_permutation(spec, d_, strata, 1999)
    _, _, st = analyze.describe(dict(spec, strata=strata), res)
    print(f"  {lab:<34} p={fmt(res['p'])}  V={st['cramers_v']:.3f} vs chance "
          f"{st['cramers_v_chance']:.3f}; cell {st['biggest_cell']['x']} x "
          f"{st['biggest_cell']['y']} {st['biggest_cell']['observed']} vs "
          f"{st['biggest_cell']['expected']:.0f}")
