"""Skeptic check: the two news findings.
  news_song_views      "Do songs about the day's news get more views?" (+124% within month)
  news_politics_topic  "When politics fills the news, does he write about politics?"

Confounds tried for news_song_views:
  1. Metadata coverage: a song can only match the news through its title, nouns, proper
     nouns and description. Nouns/proper nouns are tagged on about a quarter of songs and
     descriptions exist only from #4749. If the tagged songs are also the popular ones, the
     "news song" flag is partly a "well-documented song" flag. Check views for tagged vs
     untagged songs within month, and rerun the news effect inside the tagged songs only.
  2. Famous names, not timing: a song naming Apple, Trump or Baby Yoda may do well on any
     day. news_control_score scores the same song against the news a year earlier and
     later; songs that match those (always-in-the-news names) but not today's news show the
     "famous name" effect. Compare them, and regress on match score and control score.
  3. Viral outliers and topics: drop the top 1% by views, the Apple topic, and the
     Politics/Trump topics.
  4. Cluster-robust inference by month.
Confounds tried for news_politics_topic:
  5. Election days: drop US federal election days and the days around them, and the
     inauguration days; also drop 2009 to April 2010, where sections were inferred.
  6. Placebo: politics headlines 7 and 14 days after the song (news autocorrelates, so a
     same-strength placebo would mean the slope is about the news cycle, not the day).
"""

import numpy as np
import pandas as pd

from check_1_common import analyze, codes, fmt, load, mh_diff, ols_cluster, perm_p

df = load()
v = df[df.log_views.notna()].copy()
S = codes(v, analyze.MONTHLY)
pct = lambda e: f"{100 * (10 ** e - 1):+.1f}%"

print("== news_song_views ==")
print(f"reproduced: {pct(mh_diff(v.news_song, v.log_views, S))} (findings +124%)")
v["tagged"] = ((v.proper_nouns.apply(len) > 0) | (v.nouns != "")).astype(float)
v["has_desc"] = (v.description != "").astype(float)
print(f"songs with nouns/proper nouns tagged: {v.tagged.mean():.1%}; among news songs "
      f"{v.tagged[v.news_song == 1].mean():.1%}")
print(f"tagged vs untagged, within month: {pct(mh_diff(v.tagged, v.log_views, S))}")
t = v[v.tagged == 1]
print(f"news effect inside tagged songs only (n={len(t)}, news={int(t.news_song.sum())}): "
      f"{pct(mh_diff(t.news_song, t.log_views, codes(t, analyze.MONTHLY)))}")
u = v[v.tagged == 0]
print(f"news effect inside untagged songs (title/description only; n={len(u)}, "
      f"news={int(u.news_song.sum())}): "
      f"{pct(mh_diff(u.news_song, u.log_views, codes(u, analyze.MONTHLY)))}")
for lab, sub in [("before descriptions (#<4749)", v[v.number < 4749]),
                 ("with descriptions (#4749+)", v[v.number >= 4749])]:
    print(f"  {lab:<30} news n={int(sub.news_song.sum()):<4} "
          f"{pct(mh_diff(sub.news_song, sub.log_views, codes(sub, analyze.MONTHLY)))}")
print("news songs per era:", v.groupby("home_era").news_song.sum().astype(int).to_dict())

# Famous names regardless of timing
v["named_any"] = (v.control_score.fillna(0) > 0).astype(float)
famous_only = v[(v.news_song == 0)]
print(f"\nsongs (not news songs) that match the news a year off (control score > 0): "
      f"{int(famous_only.named_any.sum())}; vs songs matching nothing, within month: "
      f"{pct(mh_diff(famous_only.named_any, famous_only.log_views, codes(famous_only, analyze.MONTHLY)))}")
v["score"] = pd.to_numeric(v.news_match_score.where(v.news_match_score != ""), errors="coerce")
d = v.dropna(subset=["score", "control_score"]).copy()
X = pd.concat([pd.get_dummies(d.year_month, dtype=float),
               pd.DataFrame({"log1p_score": np.log1p(d.score),
                             "log1p_control": np.log1p(d.control_score),
                             "tagged": d.tagged}, index=d.index)], axis=1)
b, hc, cl, _ = ols_cluster(X.values, d.log_views.values, d.year_month.values)
for nm in ["log1p_score", "log1p_control", "tagged"]:
    j = list(X.columns).index(nm)
    print(f"  month FE regression: {nm:<14} x{10 ** b[j]:.2f} per unit, month-cluster z="
          f"{b[j] / np.sqrt(cl[j, j]):+.2f}")

cut = v.views.quantile(0.99)
apple = v.topics.apply(lambda ts: "Apple" in ts)
pol = v.politics_topic == 1
for lab, sub in [("drop top 1% views", v[v.views < cut]), ("drop Apple topic", v[~apple]),
                 ("drop Politics/Trump", v[~pol]),
                 ("drop all three", v[(v.views < cut) & ~apple & ~pol])]:
    print(f"{lab:<22} {pct(mh_diff(sub.news_song, sub.log_views, codes(sub, analyze.MONTHLY)))}")
v["rank"] = v.groupby("year_month").log_views.rank(pct=True)
print(f"within-month percentile rank: news {v['rank'][v.news_song == 1].mean():.3f} vs others "
      f"{v['rank'][v.news_song == 0].mean():.3f}")
X = pd.concat([pd.get_dummies(v.year_month, dtype=float), v[["news_song", "tagged"]]], axis=1)
b, hc, cl, _ = ols_cluster(X.values, v.log_views.values, v.year_month.values)
j = list(X.columns).index("news_song")
print(f"month FE + tagged covariate: news x{10 ** b[j]:.2f}, month-cluster z="
      f"{b[j] / np.sqrt(cl[j, j]):.2f}")

print("\n== news_politics_topic ==")
x = "news_section_politics_elections"
spec = next(t for t in analyze.TESTS if t["id"] == "news_politics_topic")
res = analyze.run_permutation(spec, df, analyze.MONTHLY, 1999)
print(f"reproduced: slope {300 * res['observed']:+.2f} points per 3 headlines, p={fmt(res['p'])}")
# US federal election days (first Tuesday after the first Monday in November, even years)
# and inaugurations.
elec = []
for yr in range(2010, 2027, 2):
    nov1 = pd.Timestamp(f"{yr}-11-01")
    first_mon = nov1 + pd.Timedelta(days=(0 - nov1.weekday()) % 7)
    elec.append(first_mon + pd.Timedelta(days=1))
special = set()
for e in elec:
    for k in range(-3, 4):
        special.add(e + pd.Timedelta(days=k))
for inaug in ["2009-01-20", "2013-01-21", "2017-01-20", "2021-01-20", "2025-01-20"]:
    for k in range(-1, 2):
        special.add(pd.Timestamp(inaug) + pd.Timedelta(days=k))
near = df.date.isin(special)
print(f"days near US elections/inaugurations: {int(near.sum())}; politics-song share there "
      f"{df.politics_topic[near].mean():.1%} vs {df.politics_topic[~near].mean():.1%}")
for lab, sub in [("drop US election/inauguration windows", df[~near]),
                 ("drop 2009-04/2010 (inferred sections)", df[df.date >= "2010-05-01"]),
                 ("drop both", df[~near & (df.date >= "2010-05-01")])]:
    r = analyze.run_permutation(spec, sub, analyze.MONTHLY, 1999)
    print(f"  {lab:<40} slope {300 * r['observed']:+.2f} points, p={fmt(r['p'])}")
# Placebo leads: the politics headlines of later days
for lead in [7, 14, -7]:
    d2 = df.copy()
    d2["lead"] = d2[x].shift(-lead)
    sp = dict(spec, x="lead", id=f"placebo{lead}")
    r = analyze.run_permutation(sp, d2.dropna(subset=["lead"]), analyze.MONTHLY, 1999)
    print(f"  placebo: headlines {lead:+d} days from the song: slope {300 * r['observed']:+.2f}, "
          f"p={fmt(r['p'])}")
# Top days driving it
top = df.assign(resid=df.politics_topic).sort_values(x, ascending=False).head(15)
print("highest-politics-headline days:", [(str(d.date()), int(n), int(p)) for d, n, p in
                                          zip(top.date, top[x], top.politics_topic)])
