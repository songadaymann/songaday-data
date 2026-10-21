"""Skeptic check: are song dates right? Compare each song's date (2009-01-01 + n - 1) with
its YouTube upload date (UTC). A song uploaded on its own evening in US time often shows
the next UTC day, so 0 or +1 is normal. A long run of -1 (upload before the song's date) or
of +2 or more would mean the numbering, and every weekday/weather/sky/news join, is off.
Also: the weekend effect (the strongest weekday result) is recomputed with the weekday
taken from the upload date instead, as a check that it doesn't depend on the numbering.
"""

import numpy as np
import pandas as pd

from check_1_common import analyze, codes, load, mh_diff

df = load()
pub = pd.to_datetime(df.yt_published_at.where(df.yt_published_at != ""))
df["delay"] = (pub - df.date).dt.days
print("upload delay (UTC upload date minus song date), share of songs by year:")
t = pd.crosstab(df.year, df.delay.clip(-2, 3), normalize="index").round(3)
print(t.to_string())
print("songs uploaded before their date (delay < 0):", int((df.delay < 0).sum()),
      df.loc[df.delay < 0, ["number", "date", "yt_published_at"]].head(10).values.tolist())
# Longest run of identical nonzero delay
runs = (df.delay != df.delay.shift()).cumsum()
r = df.groupby(runs).agg(delay=("delay", "first"), start=("number", "first"),
                         length=("number", "size"))
print("longest runs of delay -1 or >= 2:",
      r[(r.delay < 0) | (r.delay >= 2)].sort_values("length", ascending=False).head(5)
      .values.tolist())
# Weekend effect using the local day implied by an evening US upload: upload weekday - 1
# when delay == 1, else upload weekday (only songs with delay 0 or 1)
ok = df.delay.isin([0, 1])
alt_day = (pub - pd.to_timedelta(df.delay.where(ok, 0), unit="D")).dt.dayofweek
same = (alt_day[ok] == df.date[ok].dt.dayofweek).mean()
print(f"weekday implied by upload matches song weekday for {same:.1%} of songs with delay 0/1 "
      "(by construction); weekend effect among songs uploaded the same UTC day (delay 0):")
sub = df[df.delay == 0]
print(f"  {100 * mh_diff(sub.weekend, sub.wild, codes(sub, analyze.DAILY)):+.1f} points "
      f"(n={len(sub)}); delay 1: "
      f"{100 * mh_diff(df[df.delay == 1].weekend, df[df.delay == 1].wild, codes(df[df.delay == 1], analyze.DAILY)):+.1f}")
