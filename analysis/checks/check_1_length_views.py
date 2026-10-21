"""Skeptic check: where does "doubling the length: x1.20 views" come from?

Within a month, raw views barely move with length (check_1_views_model.py's binned shape is
flat from 60 to 300 s). So the model's x1.20 must appear only once other features are held
fixed. Fit log views on log2 length with month dummies, then add each block of the views
model by itself, to see which one produces it, and say how length relates to that block.
"""

import numpy as np
import pandas as pd

from check_1_common import fmt, load, ols_cluster
from check_1_views_model import design

df = load()
d = df[df.log_views.notna() & df.length_raw.notna()].copy()
X, idx = design(d)
cols = list(X.columns)
month_cols = [c for c in cols if c[:2] in ("20",)]
y = d.log_views.values
L = [cols.index("log2_length"), cols.index("log2_length_sq")]
base = [cols.index(c) for c in month_cols]


def slope(extra_idx, label):
    keep = base + L + extra_idx
    b, hc, cl, _ = ols_cluster(X.values[:, keep], y, d.year_month.values)
    j = len(base)
    print(f"  {label:<34} doubling length x{10 ** b[j]:.2f} "
          f"(month-cluster z {b[j] / np.sqrt(cl[j, j]):+.1f})")


print("log2 length (+ square) with month dummies, adding one block at a time:")
slope([], "month only")
for bn in ["topic", "mood", "genre", "instrument", "traveling", "news_song", "beard", "weekday"]:
    slope(idx[bn], f"+ {bn}")
allx = [i for bn in ["topic", "mood", "genre", "instrument", "traveling", "news_song", "beard",
                     "weekday"] for i in idx[bn]]
slope(allx, "+ everything (the findings model)")

# How long are the high-view kinds of songs?
d["resid"] = d.log_views - d.groupby("year_month").log_views.transform("mean")
print("\nmedian length and within-month views by mood:")
g = d.groupby("mood12").agg(median_len=("length_raw", "median"),
                            views_x=("resid", lambda r: 10 ** r.mean()), n=("resid", "size"))
print(g.sort_values("views_x").round(2).to_string())
