"""Look for patterns in Song A Day: chart-ready aggregates, and honest tests of fun questions
(does the full moon make him sadder? does Mercury retrograde cost views?).

Reads dataset/songaday.csv (made by sources/merge.py) and writes three files next to this one:
  aggregates.json  compact, chart-ready arrays: songs per year, mood/key/genre/instrument mix
                   by year, tempo and length, beard by month, topics, places, weekdays, views,
                   moon x mood, weather x mood, news by month, and a per-song table
  findings.json    every test: the question, a plain answer, the effect with a 95% CI, n,
                   p, Benjamini-Hochberg q, what was controlled for, and a verdict
  findings.md      the same for people: the real patterns and the funniest nulls first

How the tests stay honest
-------------------------
1. Compare like with like. Nearly everything here drifts with time: how he tagged moods
   (Happy was common in 2009 and almost gone by 2018), where he lived, the weather and season
   that come with a place, and YouTube's audience. So each test compares songs only within
   strata, for example "same year, same season, same home era" for the sky, or "same month of
   the same year, at home or away" for the weather. The effect is a Mantel-Haenszel-style
   weighted average of the within-stratum differences, or a slope after removing each
   stratum's mean.
2. Get p-values by shuffling, not by formula. The exposure (full moon, rain, ...) is shuffled
   among the songs of each stratum thousands of times, and p is how often a shuffle looks at
   least as striking as the real data. Exposures that change slowly (Mercury retrograde,
   planet positions, beard, trips, home era) would make plain shuffling over-confident,
   because neighbouring songs resemble each other, so for those the exposure series is
   rotated in time by a random offset instead: the "circular shift" test, which keeps both
   series' runs intact. Seasons, daylight and sun signs are shuffled as whole months (or
   whole sign periods) within a year.
3. The 95% CI inverts the shuffle test: it is the estimate minus the 97.5th and 2.5th
   percentiles of the shuffled (null) statistics, so it excludes 0 exactly when the
   two-sided p is below about 0.05, whatever shape the null distribution has.
4. Every test is also run once with no controls ("raw"). A pattern that is strong raw but
   gone with controls is labelled "confounded".
5. Benjamini-Hochberg q-values are computed across every p-value this script makes: the
   controlled tests, the raw versions, the time trends and the views model's blocks.
6. The views tests (weekday, travel, news songs, beard) are checked again in a regression
   that also holds topic, mood, length, instrument and genre fixed.
7. Verdicts: real (q < 0.01), probably real (q < 0.05), noise, confounded (raw q < 0.05 but
   controlled q >= 0.05; or a views effect that fades in that regression; or one that can't
   be told apart from something else, like daylight from season), and "fun null" (a famous
   superstition, q >= 0.05).

Run from the repo root:
  .venv/bin/python analysis/analyze.py            # full run, about a minute
  .venv/bin/python analysis/analyze.py --quick    # 10x fewer shuffles, for trying changes

Results are reproducible: every test seeds its random generator from its own id.
"""

import argparse
import json
import math
import sys
import time
import zlib
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parent.parent
SONGS_CSV = ROOT / "dataset" / "songaday.csv"
OUT_DIR = ROOT / "analysis"
AGGREGATES_JSON = OUT_DIR / "aggregates.json"
FINDINGS_JSON = OUT_DIR / "findings.json"
FINDINGS_MD = OUT_DIR / "findings.md"

N_PERM = 4999       # shuffles for each controlled test (smallest possible p = 0.0002)
N_PERM_RAW = 1999   # shuffles for each raw (uncontrolled) diagnostic
BATCH = 500         # shuffles computed at once

# ---------------------------------------------------------------------------------------
# Mood groups. The sheet has 35 moods; the 11 with at least 100 songs are kept, the rest
# pooled as "Other" for mood-mix tests. Two broader groups test specific folk claims.
TOP_MOODS = ["Pensive", "Chill", "Silly", "Excited", "Intense", "Tired", "Sad", "Angry",
             "Anxious", "Happy", "Hopeful"]
# High-energy moods: the "lunacy" claim is that full moons make people wilder.
WILD_MOODS = {"Silly", "Excited", "Intense", "Angry", "Anxious", "Scared", "Scary", "Drunk",
              "Wild", "Funky", "Horny", "Dizzy", "Amazed", "Motivational"}
# Unhappy moods: sad, angry, scared and the like.
DARK_MOODS = {"Sad", "Angry", "Anxious", "Scared", "Scary", "Disgusted", "Annoyed", "Upset",
              "In Pain", "Sick", "Embarrassed"}
# Mercury retrograde is said to scramble communication: confusion, anxiety, irritation.
CHAOS_MOODS = {"Anxious", "Confused", "Angry", "Annoyed"}
POLITICS_TOPICS = {"Politics", "Trump"}

ERAS = ["berkeley", "brooklyn", "jersey_city", "hartford"]
ERA_NAMES = {"berkeley": "Berkeley", "brooklyn": "Brooklyn", "jersey_city": "Jersey City",
             "hartford": "Hartford"}
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
SEASONS = ["winter", "spring", "summer", "fall"]
SIGNS = ["Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo", "Libra", "Scorpio",
         "Sagittarius", "Capricorn", "Aquarius", "Pisces"]
# Astronomical season of each sun sign (equinox and solstice to the next), for comparing
# signs only with the other signs of the same season.
SIGN_SEASON = {"Aries": "spring", "Taurus": "spring", "Gemini": "spring",
               "Cancer": "summer", "Leo": "summer", "Virgo": "summer",
               "Libra": "fall", "Scorpio": "fall", "Sagittarius": "fall",
               "Capricorn": "winter", "Aquarius": "winter", "Pisces": "winter"}
MOON_PHASES = ["new", "waxing crescent", "first quarter", "waxing gibbous", "full",
               "waning gibbous", "last quarter", "waning crescent"]
WEATHER_LABELS = ["clear", "mostly clear", "partly cloudy", "cloudy", "fog", "drizzle",
                  "rain", "snow"]

# Strata used by the tests: lists of columns whose combination defines a stratum.
SKY = ["year", "season", "home_era"]          # moon and planets
DAILY = ["year", "home_era"]                  # weekday, trips, beard
WEATHER = ["year", "month", "is_home"]        # weather: same month of the same year
MONTHLY = ["year", "month"]                   # views and news: same month of the same year


# =======================================================================================
# Loading
# =======================================================================================

def load_songs():
    """Read songaday.csv as text, convert the columns used here, and add derived columns."""
    df = pd.read_csv(SONGS_CSV, keep_default_na=False, dtype=str)

    def num(col):
        return pd.to_numeric(df[col].where(df[col] != ""))

    def flag(col):
        # True/False text to 1.0/0.0, blank to NaN
        return df[col].map({"True": 1.0, "False": 0.0})

    out = pd.DataFrame({"number": num("number").astype(int)})
    out["date"] = pd.to_datetime(df["date"])
    out["year"] = num("year").astype(int)
    out["month"] = num("month").astype(int)
    out["weekday"] = df["weekday"]
    out["season"] = df["season"]
    out["home_era"] = df["home_era"]
    out["is_home"] = flag("is_home")
    out["traveling"] = flag("is_traveling")
    out["title"] = df["title"]
    out["mood"] = df["mood"]
    out["mood12"] = df["mood"].where(df["mood"].isin(TOP_MOODS), "Other")
    out["wild"] = df["mood"].isin(WILD_MOODS).astype(float)
    out["dark"] = df["mood"].isin(DARK_MOODS).astype(float)
    out["sad"] = (df["mood"] == "Sad").astype(float)
    out["chaos"] = df["mood"].isin(CHAOS_MOODS).astype(float)
    out["tired_or_sad"] = df["mood"].isin({"Tired", "Sad"}).astype(float)
    out["topics"] = df["topics"].str.split("|").apply(lambda xs: [x for x in xs if x])
    out["main_topic"] = out["topics"].apply(lambda xs: xs[0] if xs else "")
    out["politics_topic"] = out["topics"].apply(
        lambda xs: float(bool(POLITICS_TOPICS & set(xs))))
    out["instruments"] = df["instruments"].str.split("|").apply(lambda xs: [x for x in xs if x])
    out["main_instrument"] = df["main_instrument"]
    out["genre"] = df["genre"]
    out["proper_nouns"] = df["proper_nouns"].str.split("|").apply(lambda xs: [x for x in xs if x])
    out["key"] = df["key"]
    out["mode"] = df["mode"]
    out["minor"] = flag("is_minor")
    out["tempo"] = num("tempo_bpm")
    out["length_raw"] = num("length_seconds")
    # Means are sensitive to the few 10-20 minute songs, so tests use length clipped to
    # 30 s - 8 min. Aggregates use the real length.
    out["length"] = out["length_raw"].clip(30, 480)
    beard = df["beard"]
    out["beard"] = beard.where(beard != "", np.nan)
    out["beard3"] = beard.where(beard.isin(["Beard", "Clean", "Shadow"]), np.nan)

    out["place"] = df["place"]
    out["place_lat"] = num("place_lat")
    out["place_lon"] = num("place_lon")
    out["place_city"] = df["place_city"]
    out["place_region"] = df["place_region"]
    out["place_country"] = df["place_country"]

    out["weather_label"] = df["weather_label"]
    out["temp"] = num("weather_temperature_2m_mean")
    out["temp_max"] = num("weather_temperature_2m_max")
    out["precip"] = num("weather_precipitation_sum")
    out["snowfall"] = num("weather_snowfall_sum")
    out["rain_day"] = (out["precip"] >= 1.0).astype(float)
    out["snow_day"] = (out["snowfall"] >= 1.0).astype(float)
    out["sunshine_h"] = num("weather_sunshine_duration") / 3600
    out["daylight_h"] = num("weather_daylight_duration") / 3600
    out["cloud"] = num("weather_cloud_cover_mean")

    out["moon_phase"] = df["sky_moon_phase"]
    out["moon_illum"] = num("sky_moon_illumination")
    out["full_moon"] = flag("sky_is_full_moon_day")
    out["new_moon"] = flag("sky_is_new_moon_day")
    out["supermoon"] = flag("sky_is_supermoon")
    out["mercury_retro"] = flag("sky_mercury_retrograde")
    out["retro_count"] = num("sky_retrograde_count")
    out["planet_arc"] = num("sky_planets_in_smallest_arc")
    out["conj_pairs"] = num("sky_conjunction_pairs")
    out["any_conj"] = (out["conj_pairs"] >= 1).astype(float)
    out["sun_sign"] = df["sky_sun_sign"]
    out["moon_sign"] = df["sky_moon_sign"]
    out["eclipse"] = flag("sky_is_eclipse_day")
    out["eclipse_kind"] = df["sky_eclipse_kind"]
    out["sign_season"] = out["sun_sign"].map(SIGN_SEASON)
    out["friday13"] = ((out["weekday"] == "Friday") & (out["date"].dt.day == 13)).astype(float)
    out["weekend"] = out["weekday"].isin(["Saturday", "Sunday"]).astype(float)
    out["monday"] = (out["weekday"] == "Monday").astype(float)

    # Views. Only songs whose video is up, was uploaded within 30 days of the song (13
    # re-uploads, like #1-#4 in 2021, have had a shorter life), and has been online at
    # least 30 days. Tests use log10(views + 1), because views are wildly uneven.
    views = num("yt_views")
    published = pd.to_datetime(df["yt_published_at"].where(df["yt_published_at"] != ""))
    upload_delay = (published - out["date"]).dt.days
    days_online = num("yt_days_online")
    ok = (views.notna() & (df["yt_video_status"] == "available")
          & (upload_delay <= 30) & (days_online >= 30))
    out["views"] = views
    out["views_ok"] = ok
    out["log_views"] = np.log10(views + 1).where(ok)
    # Views relative to the typical song of the same month: a chart-friendly, age-fair
    # measure. 2.0 means twice the month's median.
    month_key = out["date"].dt.strftime("%Y-%m")
    out["year_month"] = month_key
    month_median = out["views"].where(ok).groupby(month_key).transform("median")
    out["rel_views"] = (out["views"] / month_median).where(ok)

    # Wikipedia's Portal:Current events: headline items that day, and items per section.
    for col in ["news_n_items"] + [c for c in df.columns if c.startswith("news_section_")]:
        out[col] = num(col)
    out["news_excess"] = num("news_match_excess")
    out["news_score"] = num("news_match_score")
    out["news_terms"] = df["news_matched_terms"]
    # A "news song": names that day's news clearly more than chance (see dataset/README.md).
    out["news_song"] = (out["news_excess"] >= 1.0).astype(float)
    return out


# =======================================================================================
# The test engine
# =======================================================================================

def stratum_codes(df, cols):
    """One integer per row for the combination of the given columns (0 if cols is empty)."""
    if not cols:
        return np.zeros(len(df), dtype=int)
    key = df[cols].astype(str).agg("|".join, axis=1)
    return pd.factorize(key)[0]


def group_indices(codes):
    """List of index arrays, one per distinct code."""
    order = np.argsort(codes, kind="stable")
    bounds = np.flatnonzero(np.diff(codes[order])) + 1
    return np.split(order, bounds)


def shuffle_within(values, groups, size, rng):
    """`size` copies of `values`, each shuffled independently within each group."""
    out = np.empty((size, len(values)), dtype=values.dtype)
    for idx in groups:
        out[:, idx] = rng.permuted(np.tile(values[idx], (size, 1)), axis=1)
    return out


def circular_shift(values, size, rng, min_shift):
    """`size` copies of `values`, each rotated in time by a random offset of at least
    min_shift positions (either way)."""
    n = len(values)
    k = rng.integers(min_shift, n - min_shift + 1, size=size)
    return values[(np.arange(n)[None, :] + k[:, None]) % n]


def onehot(codes):
    m = np.zeros((len(codes), codes.max() + 1))
    m[np.arange(len(codes)), codes] = 1.0
    return m


def make_statistic(kind, y, strata, n_x=None, n_y=None):
    """Return f(X) -> one statistic per row of X (each row is one version of the exposure).

    diff   binary x, numeric y: Mantel-Haenszel-weighted average over strata of
           mean(y | x=1) - mean(y | x=0), weights n1*n0/n
    slope  numeric x, numeric y: least-squares slope of y on x after removing stratum means
    anova  categorical x, numeric y: between-group sum of squares of stratum-demeaned y
    assoc  categorical x, categorical y: chi-square of observed counts against the counts
           expected if x and y were independent within every stratum
    """
    n = len(y)
    if kind in ("diff", "slope"):
        M = onehot(strata)
        ns = M.sum(0)
        if kind == "diff":
            sy = y @ M

            def f(X):
                X = X.astype(float)
                n1 = X @ M
                sy1 = (X * y) @ M
                n0 = ns - n1
                ok = (n1 > 0) & (n0 > 0)
                d = np.where(ok, sy1 / np.where(ok, n1, 1)
                             - (sy - sy1) / np.where(ok, n0, 1), 0.0)
                w = np.where(ok, n1 * n0 / ns, 0.0)
                return (w * d).sum(1) / w.sum(1)
            return f
        yd = y - (y @ M / ns)[strata]

        def f(X):
            X = X.astype(float)
            xd = X - ((X @ M) / ns)[:, strata]
            return (xd @ yd) / (xd * xd).sum(1)
        return f
    if kind == "anova":
        M = onehot(strata)
        yd = y - (y @ M / M.sum(0))[strata]

        def f(X):
            B = X.shape[0]
            flat = (X + n_x * np.arange(B)[:, None]).ravel()
            sums = np.bincount(flat, weights=np.tile(yd, B), minlength=B * n_x).reshape(B, n_x)
            cnts = np.bincount(flat, minlength=B * n_x).reshape(B, n_x)
            return (sums ** 2 / np.maximum(cnts, 1)).sum(1)
        return f
    if kind == "assoc":
        S = strata.max() + 1
        col_counts = np.bincount(strata * n_y + y, minlength=S * n_y).reshape(S, n_y)
        ns = col_counts.sum(1)
        W = col_counts / ns[:, None]

        def f(X):
            B = X.shape[0]
            off = np.arange(B)[:, None]
            O = np.bincount(((off * n_x + X) * n_y + y[None, :]).ravel(),
                            minlength=B * n_x * n_y).reshape(B, n_x, n_y)
            R = np.bincount(((off * S + strata[None, :]) * n_x + X).ravel(),
                            minlength=B * S * n_x).reshape(B, S, n_x)
            E = np.einsum("bsa,sc->bac", R, W)
            with np.errstate(divide="ignore", invalid="ignore"):
                return np.where(E > 0, (O - E) ** 2 / E, 0.0).sum((1, 2))
        return f
    raise ValueError(kind)


def null_draws(x, null, strata, size, rng, spec, sub):
    """`size` versions of the exposure x under the null hypothesis."""
    if null == "perm":
        return shuffle_within(x, group_indices(strata), size, rng)
    if null == "shift":
        return circular_shift(x, size, rng, spec.get("min_shift", 30))
    if null == "block":
        # Shuffle whole blocks (a month, or a sun-sign period) among the blocks of the same
        # block stratum (a year, or a year's season), then give each song its block's value.
        block = pd.factorize(sub[spec["blocks"]].astype(str).agg("|".join, axis=1))[0]
        nb = block.max() + 1
        block_x = np.zeros(nb, dtype=x.dtype)
        if np.issubdtype(x.dtype, np.integer):
            block_x[block] = x                                     # constant within block
        else:
            block_x = np.bincount(block, weights=x, minlength=nb) / np.bincount(block)
        first = pd.Series(np.arange(len(block))).groupby(block).first().to_numpy()
        bstrata_cols = spec["block_strata"]
        bstrata = (stratum_codes(sub.iloc[first], bstrata_cols) if bstrata_cols
                   else np.zeros(nb, dtype=int))
        return shuffle_within(block_x, group_indices(bstrata), size, rng)[:, block]
    raise ValueError(null)


def block_mean_exposure(x, sub, spec):
    """For block nulls with a numeric exposure, the observed exposure is the block mean."""
    block = pd.factorize(sub[spec["blocks"]].astype(str).agg("|".join, axis=1))[0]
    means = np.bincount(block, weights=x) / np.bincount(block)
    return means[block]


def run_permutation(spec, df, strata_cols, n_perm, seed_suffix=""):
    """Run one test. Returns the observed statistic, its null distribution and details."""
    kind = spec["kind"]
    cols = [spec["x"], spec["y"]] + strata_cols + spec.get("blocks", []) \
        + spec.get("block_strata", [])
    sub = df.dropna(subset=[spec["x"], spec["y"]]).sort_values("number")
    sub = sub[list(dict.fromkeys(cols + ["number"]))]
    strata = stratum_codes(sub, strata_cols)
    rng = np.random.default_rng(zlib.crc32((spec["id"] + seed_suffix).encode()))

    x_labels = y_labels = None
    if kind in ("anova", "assoc"):
        order = spec.get("x_order")
        x_labels = order if order else sorted(sub[spec["x"]].unique())
        x = pd.Categorical(sub[spec["x"]], categories=x_labels).codes.astype(np.int64)
        keep = x >= 0
    else:
        x = sub[spec["x"]].to_numpy(dtype=float)
        keep = np.ones(len(x), bool)
    if kind == "assoc":
        y_labels = spec.get("y_order") or sorted(sub[spec["y"]].unique())
        y = pd.Categorical(sub[spec["y"]], categories=y_labels).codes.astype(np.int64)
        keep &= y >= 0
    else:
        y = sub[spec["y"]].to_numpy(dtype=float)
    sub, x, y, strata = sub[keep], x[keep], y[keep], pd.factorize(strata[keep])[0]

    if spec["null"] == "block" and kind != "anova" and kind != "assoc":
        x = block_mean_exposure(x, sub, spec)
    f = make_statistic(kind, y, strata,
                       n_x=len(x_labels) if x_labels else None,
                       n_y=len(y_labels) if y_labels else None)
    observed = float(f(x[None, :])[0])
    null = []
    for start in range(0, n_perm, BATCH):
        size = min(BATCH, n_perm - start)
        null.append(f(null_draws(x, spec["null"], strata, size, rng, spec, sub)))
    null = np.concatenate(null)
    if kind in ("diff", "slope"):
        p = (1 + np.sum(np.abs(null) >= abs(observed) - 1e-12)) / (n_perm + 1)
    else:
        p = (1 + np.sum(null >= observed - 1e-12)) / (n_perm + 1)
    return dict(observed=observed, null=null, p=float(p), sub=sub, x=x, y=y, strata=strata,
                x_labels=x_labels, y_labels=y_labels)


# ---------------------------------------------------------------------------------------
# Turning a test's raw numbers into effect sizes and a plain-language answer

def fmt_p(p):
    if p is None:
        return "n/a"
    return f"{p:.4f}" if p >= 0.0001 else "<0.0001"


def eq(p):
    """'= 0.0123' or '< 0.0001', for writing p and q in sentences."""
    f = fmt_p(p)
    return f"< {f[1:]}" if f.startswith("<") else f"= {f}"


def upper_first(text):
    """Capitalise only the first letter (str.capitalize would lowercase mood names)."""
    return text[:1].upper() + text[1:]


def pct(v, digits=1):
    return f"{100 * v:.{digits}f}%"


def describe(spec, res):
    """Effect size, CI and a plain sentence for one controlled test."""
    kind, obs, null = spec["kind"], res["observed"], res["null"]
    x, y, sub = res["x"], res["y"], res["sub"]
    yk = spec.get("y_kind", "number")
    unit = spec.get("y_unit", "")
    sd = float(np.std(null))
    # 95% CI by inverting the shuffle test under a shift model: the effects d for which
    # (estimate - d) would sit inside the middle 95% of the shuffled statistics.
    lo = obs - float(np.quantile(null, 0.975))
    hi = obs - float(np.quantile(null, 0.025))
    stats_out = {"estimate": obs, "ci_low": lo, "ci_high": hi, "null_sd": sd}
    ctl = ", controlled" if spec["strata"] else ", no controls"

    if kind == "diff":
        g1, g0 = y[x == 1], y[x == 0]
        stats_out.update(n_exposed=int(len(g1)), n_other=int(len(g0)),
                         mean_exposed=float(g1.mean()), mean_other=float(g0.mean()))
        if yk == "binary":
            effect = (f"{100 * obs:+.1f} percentage points (95% CI {100 * lo:+.1f} to "
                      f"{100 * hi:+.1f}){ctl}")
            answer = (f"{upper_first(spec['y_label'])}: {pct(g1.mean())} of {len(g1):,} songs "
                      f"{spec['x_label']} vs {pct(g0.mean())} of {len(g0):,} "
                      f"{spec['x_else']}; compared like with like, "
                      f"{100 * obs:+.1f} points (95% CI {100 * lo:+.1f} to {100 * hi:+.1f}).")
        elif yk == "log_views":
            m = lambda v: 100 * (10 ** v - 1)
            effect = f"{m(obs):+.0f}% views (95% CI {m(lo):+.0f}% to {m(hi):+.0f}%){ctl}"
            med1 = float(np.median(10 ** g1 - 1))
            med0 = float(np.median(10 ** g0 - 1))
            stats_out.update(median_views_exposed=med1, median_views_other=med0)
            answer = (f"Median views {med1:,.0f} for {len(g1):,} songs {spec['x_label']} vs "
                      f"{med0:,.0f} for {len(g0):,} {spec['x_else']}; against songs of the "
                      f"same month that's {m(obs):+.0f}% views "
                      f"(95% CI {m(lo):+.0f}% to {m(hi):+.0f}%).")
        else:
            effect = f"{obs:+.1f} {unit} (95% CI {lo:+.1f} to {hi:+.1f}){ctl}"
            answer = (f"Songs {spec['x_label']} averaged {g1.mean():.1f} {unit} "
                      f"({len(g1):,} songs) vs {g0.mean():.1f} {unit} {spec['x_else']}; "
                      f"compared like with like, {obs:+.1f} {unit} "
                      f"(95% CI {lo:+.1f} to {hi:+.1f}).")
    elif kind == "slope":
        step = spec.get("x_step", 1.0)
        xd = x - pd.Series(x).groupby(res["strata"]).transform("mean").to_numpy()
        yd = y - pd.Series(y).groupby(res["strata"]).transform("mean").to_numpy()
        # Partial correlation, signed in the direction of `step` (so "tighter" or "less"
        # reads the same way as the effect).
        r = float(np.corrcoef(xd, yd)[0, 1]) * float(np.sign(spec.get("x_step", 1.0)))
        # The effect per `step` of the exposure; a negative step reads "per 3 hours less".
        s = obs * step
        l, h = sorted([lo * step, hi * step])
        stats_out.update(partial_r=r, per_step=step, effect_per_step=s, ci_low_per_step=l,
                         ci_high_per_step=h)
        per = " ".join(f"{abs(step):g} {spec['x_unit']} {spec.get('x_label', '')}".split())
        if yk == "binary":
            effect = (f"{100 * s:+.2f} points per {per} (95% CI {100 * l:+.2f} to "
                      f"{100 * h:+.2f}); partial r = {r:+.3f}")
            answer = (f"Per {per}, the share of {spec['y_label']} changes by {100 * s:+.2f} "
                      f"points (95% CI {100 * l:+.2f} to {100 * h:+.2f}; overall "
                      f"{pct(y.mean())}).")
        elif yk == "log_views":
            m = lambda v: 100 * (10 ** v - 1)
            effect = (f"{m(s):+.1f}% views per {per} (95% CI {m(l):+.1f}% to {m(h):+.1f}%); "
                      f"partial r = {r:+.3f}")
            answer = (f"Per {per}, views change by {m(s):+.1f}% "
                      f"(95% CI {m(l):+.1f}% to {m(h):+.1f}%).")
        else:
            effect = (f"{s:+.2f} {unit} per {per} (95% CI {l:+.2f} to {h:+.2f}); "
                      f"partial r = {r:+.3f}")
            answer = (f"Per {per}, {spec['y_label']} changes by {s:+.2f} {unit} "
                      f"(95% CI {l:+.2f} to {h:+.2f}; overall mean {y.mean():.1f} {unit}).")
    elif kind == "anova":
        strata = res["strata"]
        yd = y - pd.Series(y).groupby(strata).transform("mean").to_numpy()
        eta2 = obs / float((yd ** 2).sum())
        null_eta2 = float(np.mean(null)) / float((yd ** 2).sum())
        groups = {}
        for i, lab in enumerate(res["x_labels"]):
            m = x == i
            if m.sum() == 0:
                continue
            adj = float(y.mean() + yd[m].mean())
            groups[lab] = {"n": int(m.sum()), "raw_mean": float(y[m].mean()),
                           "adjusted_mean": adj}
        stats_out = {"eta_squared": eta2, "eta_squared_chance": null_eta2, "groups": groups}
        if yk == "binary":
            parts = ", ".join(f"{spec.get('x_names', {}).get(k, k)} {pct(v['adjusted_mean'])}"
                              for k, v in groups.items())
            what = f"share of {spec['y_label']}"
        elif yk == "log_views":
            parts = ", ".join(
                f"{spec.get('x_names', {}).get(k, k)} "
                f"{100 * (10 ** (v['adjusted_mean'] - y.mean()) - 1):+.0f}%"
                for k, v in groups.items())
            what = ("views against same-month songs" if spec["strata"]
                    else "views against the overall mean")
        else:
            parts = ", ".join(f"{spec.get('x_names', {}).get(k, k)} "
                              f"{v['adjusted_mean']:.1f}" for k, v in groups.items())
            what = f"{spec['y_label']} ({unit})"
        controlled = " (controlled)" if spec["strata"] else ""
        effect = (f"eta^2 = {eta2:.4f} (chance alone gives about {null_eta2:.4f}); "
                  f"{what}{controlled}: {parts}")
        answer = (f"{spec['x_title']} explains {pct(eta2, 2)} of the variation in "
                  f"{spec['y_label']} (chance alone: about {pct(null_eta2, 2)}). "
                  f"{upper_first(what)}{controlled}: {parts}.")
    else:  # assoc
        n = len(y)
        A, C = len(res["x_labels"]), len(res["y_labels"])
        V = math.sqrt(obs / (n * (min(A, C) - 1)))
        V0 = math.sqrt(max(float(np.mean(null)), 0) / (n * (min(A, C) - 1)))
        # Biggest departure from independence, using the within-stratum expected counts.
        strata = res["strata"]
        S = strata.max() + 1
        cc = np.bincount(strata * C + y, minlength=S * C).reshape(S, C)
        rc = np.bincount(strata * A + x, minlength=S * A).reshape(S, A)
        E = (rc.T @ (cc / cc.sum(1)[:, None]))
        O = np.bincount(x * C + y, minlength=A * C).reshape(A, C)
        z = np.where(E >= 10, (O - E) / np.sqrt(np.maximum(E, 1e-9)), 0)
        a, c = np.unravel_index(np.argmax(np.abs(z)), z.shape)
        xn = spec.get("x_names", {}).get(res["x_labels"][a], res["x_labels"][a])
        cell = (f"{xn} x {res['y_labels'][c]}: {O[a, c]} songs vs {E[a, c]:.0f} expected "
                f"({100 * (O[a, c] / E[a, c] - 1):+.0f}%)")
        stats_out = {"cramers_v": V, "cramers_v_chance": V0, "chi2": obs,
                     "biggest_cell": {"x": xn, "y": res["y_labels"][c],
                                      "observed": int(O[a, c]), "expected": float(E[a, c]),
                                      "z": float(z[a, c])}}
        effect = f"Cramer's V = {V:.3f} (chance alone gives about {V0:.3f}); biggest cell {cell}"
        answer = (f"{spec['x_title']} vs {spec['y_label']}: association V = {V:.3f}, against "
                  f"about {V0:.3f} from chance alone. Biggest departure: {cell}.")
    return " ".join(effect.split()), " ".join(answer.split()), stats_out


# =======================================================================================
# The questions
# =======================================================================================

def T(**kw):
    """A test spec, with defaults."""
    kw.setdefault("fun", False)
    kw.setdefault("strata", [])
    kw.setdefault("null", "perm")
    kw.setdefault("y_kind", "binary")
    return kw


MOOD_ORDER = TOP_MOODS + ["Other"]
SKY_CONTROLS = "same year, season and home era"
DAILY_CONTROLS = "same year and home era"
WEATHER_CONTROLS = "same month of the same year, at home or away separately"
MONTH_CONTROLS = "same month of the same year (views grow with a video's age and YouTube era)"

TESTS = [
    # ---- The moon --------------------------------------------------------------------
    T(id="moon_full_wild", fun=True, group="Moon",
      question="Do full moons make wilder songs?",
      kind="diff", x="full_moon", y="wild", strata=SKY,
      x_label="on full-moon days", x_else="on other days",
      y_label="high-energy moods (Silly, Excited, Intense, Angry, Anxious...)",
      controls=SKY_CONTROLS, chart="moon_phase_summary: wild_share by phase (bar)"),
    T(id="moon_full_minor", fun=True, group="Moon",
      question="Are full-moon songs more often in a minor key?",
      kind="diff", x="full_moon", y="minor", strata=SKY,
      x_label="on full-moon days", x_else="on other days", y_label="minor-key songs",
      controls=SKY_CONTROLS + "; songs with a known mode",
      chart="moon_phase_summary: minor_share by phase (bar)"),
    T(id="moon_full_tempo", fun=True, group="Moon",
      question="Are full-moon songs faster?",
      kind="diff", x="full_moon", y="tempo", strata=SKY, y_kind="number", y_unit="bpm",
      x_label="on full-moon days", x_else="on other days", y_label="tempo",
      controls=SKY_CONTROLS, chart="moon_phase_summary: median_tempo by phase (dot plot)"),
    T(id="moon_full_length", fun=True, group="Moon",
      question="Are full-moon songs longer?",
      kind="diff", x="full_moon", y="length", strata=SKY, y_kind="number", y_unit="s",
      x_label="on full-moon days", x_else="on other days", y_label="length",
      controls=SKY_CONTROLS + "; length clipped to 30-480 s",
      chart="moon_phase_summary: median_length by phase (dot plot)"),
    T(id="moon_phase_mood", fun=True, group="Moon",
      question="Does the phase of the moon change the mood mix?",
      kind="assoc", x="moon_phase", y="mood12", strata=SKY, x_order=MOON_PHASES,
      y_order=MOOD_ORDER, x_title="Moon phase", y_label="mood",
      controls=SKY_CONTROLS, chart="moon_phase_mood: counts (heatmap, row-normalised)"),
    T(id="supermoon_wild", fun=True, group="Moon",
      question="Do supermoons make wilder songs?",
      kind="diff", x="supermoon", y="wild", strata=SKY,
      x_label="on supermoon days", x_else="on other days",
      y_label="high-energy moods", controls=SKY_CONTROLS,
      chart="moon_phase_summary (supermoon row)"),
    T(id="eclipse_dark", fun=True, group="Moon",
      question="Are eclipse days darker?",
      kind="diff", x="eclipse", y="dark", strata=SKY,
      x_label="on eclipse days", x_else="on other days",
      y_label="unhappy moods (Sad, Angry, Anxious, Scared...)", controls=SKY_CONTROLS,
      chart="eclipses: the eclipse-day songs (list or strip)"),
    T(id="moon_sign_mood", fun=True, group="Moon",
      question="Does the Moon's zodiac sign change the mood mix?",
      kind="assoc", x="moon_sign", y="mood12", strata=SKY, x_order=SIGNS, y_order=MOOD_ORDER,
      x_title="Moon sign", y_label="mood", controls=SKY_CONTROLS,
      chart="moon_sign_mood: counts (heatmap)"),

    # ---- Mercury retrograde ----------------------------------------------------------
    T(id="mercury_mood", fun=True, group="Mercury retrograde",
      question="Does Mercury retrograde change the mood mix?",
      kind="assoc", x="mercury_retro", y="mood12", strata=SKY, null="shift",
      x_order=[0.0, 1.0], x_names={0.0: "Direct", 1.0: "Retrograde"}, y_order=MOOD_ORDER,
      x_title="Mercury retrograde", y_label="mood",
      controls=SKY_CONTROLS + "; circular-shift null",
      chart="mercury_summary: mood shares, retrograde vs direct (paired bars)"),
    T(id="mercury_minor", fun=True, group="Mercury retrograde",
      question="Is he more often in a minor key when Mercury is retrograde?",
      kind="diff", x="mercury_retro", y="minor", strata=SKY, null="shift",
      x_label="during Mercury retrograde", x_else="otherwise", y_label="minor-key songs",
      controls=SKY_CONTROLS + "; circular-shift null",
      chart="mercury_summary: minor_share (paired bars)"),
    T(id="mercury_chaos", fun=True, group="Mercury retrograde",
      question="Does Mercury retrograde bring confused, anxious, angry songs?",
      kind="diff", x="mercury_retro", y="chaos", strata=SKY, null="shift",
      x_label="during Mercury retrograde", x_else="otherwise",
      y_label="Anxious, Confused, Angry or Annoyed moods",
      controls=SKY_CONTROLS + "; circular-shift null",
      chart="mercury_summary: chaos_share (paired bars)"),
    T(id="mercury_views", fun=True, group="Mercury retrograde",
      question="Do songs made during Mercury retrograde get fewer views?",
      kind="diff", x="mercury_retro", y="log_views", strata=MONTHLY, null="shift",
      y_kind="log_views", x_label="made during Mercury retrograde", x_else="otherwise",
      y_label="views", controls=MONTH_CONTROLS + "; circular-shift null",
      chart="mercury_summary: median_rel_views (paired bars)"),

    # ---- Planets -----------------------------------------------------------------------
    T(id="arc_wild", fun=True, group="Planets",
      question="When the planets bunch up in the sky (a 'planet parade'), are songs wilder?",
      kind="slope", x="planet_arc", y="wild", strata=SKY, null="shift", min_shift=60,
      x_step=-30, x_unit="degrees tighter planet bunching", x_label="",
      y_label="high-energy moods", controls=SKY_CONTROLS + "; circular-shift null",
      chart="planet_arc_binned: wild_share by arc bin (line)"),
    T(id="arc_tempo", fun=True, group="Planets",
      question="Are songs faster when the planets are aligned?",
      kind="slope", x="planet_arc", y="tempo", strata=SKY, null="shift", min_shift=60,
      y_kind="number", y_unit="bpm", x_step=-30,
      x_unit="degrees tighter planet bunching", x_label="", y_label="tempo",
      controls=SKY_CONTROLS + "; circular-shift null",
      chart="planet_arc_binned: median_tempo by arc bin (line)"),
    T(id="conj_mood", fun=True, group="Planets",
      question="Do planetary conjunctions change the mood mix?",
      kind="assoc", x="any_conj", y="mood12", strata=SKY, null="shift",
      x_order=[0.0, 1.0], x_names={0.0: "No conjunction", 1.0: "Conjunction"},
      y_order=MOOD_ORDER, x_title="Any planet pair within 5 degrees", y_label="mood",
      controls=SKY_CONTROLS + "; circular-shift null",
      chart="conjunction_summary: mood shares by number of pairs (stacked bars)"),
    T(id="conj_tempo", fun=True, group="Planets",
      question="Are songs faster when more planets are in conjunction?",
      kind="slope", x="conj_pairs", y="tempo", strata=SKY, null="shift", y_kind="number",
      y_unit="bpm", x_step=1, x_unit="more conjunction pair", x_label="",
      y_label="tempo", controls=SKY_CONTROLS + "; circular-shift null",
      chart="conjunction_summary: median_tempo by pairs (dot plot)"),
    T(id="retro_count_dark", fun=True, group="Planets",
      question="The more planets retrograde, the darker the song?",
      kind="slope", x="retro_count", y="dark", strata=SKY, null="shift", x_step=1,
      x_unit="more retrograde planet", x_label="",
      y_label="unhappy moods", controls=SKY_CONTROLS + "; circular-shift null",
      chart="retrograde_summary: dark_share by count (bar)"),

    # ---- Calendar superstitions ------------------------------------------------------
    T(id="sun_sign_mood", fun=True, group="Zodiac and calendar",
      question="Does the Sun's zodiac sign change the mood mix (beyond the season)?",
      kind="assoc", x="sun_sign", y="mood12", strata=["year", "sign_season"], null="block",
      blocks=["year", "sun_sign"], block_strata=["year", "sign_season"], x_order=SIGNS,
      y_order=MOOD_ORDER, x_title="Sun sign", y_label="mood",
      controls="same year and astronomical season (each sign only against the other two "
               "signs of its season); whole sign periods shuffled",
      chart="sun_sign_mood: counts (heatmap, row-normalised)"),
    T(id="friday13_dark", fun=True, group="Zodiac and calendar",
      question="Is Friday the 13th unlucky (darker songs)?",
      kind="diff", x="friday13", y="dark", strata=DAILY,
      x_label="on Friday the 13th", x_else="on other days", y_label="unhappy moods",
      controls=DAILY_CONTROLS, chart="friday13: the songs (list)"),
    T(id="monday_tired", fun=True, group="Zodiac and calendar",
      question="Monday blues: more tired or sad songs on Mondays?",
      kind="diff", x="monday", y="tired_or_sad", strata=DAILY,
      x_label="on Mondays", x_else="on other days", y_label="Tired or Sad moods",
      controls=DAILY_CONTROLS, chart="weekday: tired_or_sad_share by weekday (bar)"),

    # ---- Weather ---------------------------------------------------------------------
    T(id="temp_tempo", group="Weather",
      question="Are songs faster on warm days?",
      kind="slope", x="temp", y="tempo", strata=WEATHER, y_kind="number", y_unit="bpm",
      x_step=10, x_unit="C warmer", x_label="(daily mean)", y_label="tempo",
      controls=WEATHER_CONTROLS, chart="temperature_binned: median_tempo by 5 C bin (line)"),
    T(id="temp_length", group="Weather",
      question="Are songs longer on warm (or cold) days?",
      kind="slope", x="temp", y="length", strata=WEATHER, y_kind="number", y_unit="s",
      x_step=10, x_unit="C warmer", x_label="(daily mean)", y_label="length",
      controls=WEATHER_CONTROLS + "; length clipped to 30-480 s",
      chart="temperature_binned: median_length by 5 C bin (line)"),
    T(id="temp_wild", group="Weather",
      question="Do warm days bring high-energy moods?",
      kind="slope", x="temp", y="wild", strata=WEATHER, x_step=10, x_unit="C warmer",
      x_label="(daily mean)", y_label="high-energy moods",
      controls=WEATHER_CONTROLS, chart="temperature_binned: wild_share by bin (line)"),
    T(id="temp_minor", group="Weather",
      question="Are cold days more minor-key?",
      kind="slope", x="temp", y="minor", strata=WEATHER, x_step=10, x_unit="C warmer",
      x_label="(daily mean)", y_label="minor-key songs",
      controls=WEATHER_CONTROLS, chart="temperature_binned: minor_share by bin (line)"),
    T(id="rain_sad", group="Weather",
      question="Do rainy days make sad songs?",
      kind="diff", x="rain_day", y="sad", strata=WEATHER,
      x_label="on days with at least 1 mm of rain or snow", x_else="on drier days",
      y_label="Sad songs", controls=WEATHER_CONTROLS,
      chart="precip_binned: sad_share by precipitation bin (bar)"),
    T(id="rain_minor", group="Weather",
      question="Are rainy-day songs more often minor?",
      kind="diff", x="rain_day", y="minor", strata=WEATHER,
      x_label="on wet days", x_else="on drier days", y_label="minor-key songs",
      controls=WEATHER_CONTROLS, chart="precip_binned: minor_share by bin (bar)"),
    T(id="rain_tempo", group="Weather",
      question="Are rainy-day songs slower?",
      kind="diff", x="rain_day", y="tempo", strata=WEATHER, y_kind="number", y_unit="bpm",
      x_label="on wet days", x_else="on drier days", y_label="tempo",
      controls=WEATHER_CONTROLS, chart="precip_binned: median_tempo by bin (dot plot)"),
    T(id="snow_mood", group="Weather",
      question="Do snow days change the mood mix?",
      kind="assoc", x="snow_day", y="mood12", strata=WEATHER, x_order=[0.0, 1.0],
      x_names={0.0: "No snow", 1.0: "Snow day"}, y_order=MOOD_ORDER,
      x_title="Snow day (1 cm or more)", y_label="mood", controls=WEATHER_CONTROLS,
      chart="weather_mood: snow row vs the rest (bars)"),
    T(id="sunshine_sad", group="Weather",
      question="Do sunny days make fewer sad songs?",
      kind="slope", x="sunshine_h", y="sad", strata=WEATHER, x_step=4,
      x_unit="hours more sunshine", x_label="", y_label="Sad songs",
      controls=WEATHER_CONTROLS, chart="weather_mood: sad share by label (bar)"),
    T(id="cloud_minor", group="Weather",
      question="Are cloudy days more minor-key?",
      kind="slope", x="cloud", y="minor", strata=WEATHER, x_step=50,
      x_unit="percentage points more cloud cover", x_label="", y_label="minor-key songs",
      controls=WEATHER_CONTROLS, chart="weather_mood (bars)"),
    T(id="weather_label_mood", group="Weather",
      question="Does the day's weather (clear, cloudy, rain, snow...) change the mood mix?",
      kind="assoc", x="weather_label", y="mood12", strata=WEATHER, x_order=WEATHER_LABELS,
      y_order=MOOD_ORDER, x_title="Weather", y_label="mood", controls=WEATHER_CONTROLS,
      chart="weather_mood: counts (heatmap, row-normalised)"),

    # ---- Seasons and daylight ----------------------------------------------------------
    T(id="season_mood", group="Seasons",
      question="Does the season change the mood mix?",
      kind="assoc", x="season", y="mood12", strata=["year"], null="block",
      blocks=["year", "month"], block_strata=["year"], x_order=SEASONS, y_order=MOOD_ORDER,
      x_title="Season", y_label="mood",
      controls="same year; whole months shuffled within the year",
      chart="month_of_year: mood shares by month (stacked area)"),
    T(id="season_tempo", group="Seasons",
      question="Is he faster in some seasons?",
      kind="anova", x="season", y="tempo", strata=["year"], null="block",
      blocks=["year", "month"], block_strata=["year"], x_order=SEASONS, y_kind="number",
      y_unit="bpm", x_title="Season", y_label="tempo",
      controls="same year; whole months shuffled within the year",
      chart="month_of_year: median_tempo (line)"),
    T(id="daylight_sad", group="Seasons", inseparable="season",
      question="Seasonal blues: do short days make more sad songs?",
      kind="slope", x="daylight_h", y="sad", strata=["year"], null="block",
      blocks=["year", "month"], block_strata=["year"], x_step=-3,
      x_unit="hours less daylight", x_label="(monthly mean)", y_label="Sad songs",
      controls="same year; whole months shuffled within the year",
      chart="month_of_year: sad_share vs daylight_h (dual line)"),
    T(id="daylight_minor", group="Seasons", inseparable="season",
      question="Do short days make more minor-key songs?",
      kind="slope", x="daylight_h", y="minor", strata=["year"], null="block",
      blocks=["year", "month"], block_strata=["year"], x_step=-3,
      x_unit="hours less daylight", x_label="(monthly mean)", y_label="minor-key songs",
      controls="same year; whole months shuffled within the year",
      chart="month_of_year: minor_share vs daylight_h (dual line)"),

    # ---- Weekdays ----------------------------------------------------------------------
    T(id="weekend_length", group="Weekdays",
      question="Are weekend songs longer?",
      kind="diff", x="weekend", y="length", strata=DAILY, y_kind="number", y_unit="s",
      x_label="on weekends", x_else="on weekdays", y_label="length",
      controls=DAILY_CONTROLS + "; length clipped to 30-480 s",
      chart="weekday: median_length by weekday (bar)"),
    T(id="weekend_tempo", group="Weekdays",
      question="Are weekend songs faster or slower?",
      kind="diff", x="weekend", y="tempo", strata=DAILY, y_kind="number", y_unit="bpm",
      x_label="on weekends", x_else="on weekdays", y_label="tempo",
      controls=DAILY_CONTROLS, chart="weekday: median_tempo by weekday (bar)"),
    T(id="weekend_wild", group="Weekdays",
      question="Are weekend songs mellower?",
      kind="diff", x="weekend", y="wild", strata=DAILY,
      x_label="on weekends", x_else="on weekdays", y_label="high-energy moods",
      controls=DAILY_CONTROLS, chart="weekday: wild_share by weekday (bar)"),
    T(id="weekday_mood", group="Weekdays",
      question="Does the day of the week change the mood mix?",
      kind="assoc", x="weekday", y="mood12", strata=DAILY, x_order=WEEKDAYS,
      y_order=MOOD_ORDER, x_title="Weekday", y_label="mood", controls=DAILY_CONTROLS,
      chart="weekday: mood shares (heatmap)"),
    T(id="weekday_views", group="Weekdays",
      question="Do songs from some weekdays get more views?",
      kind="anova", x="weekday", y="log_views", strata=MONTHLY, x_order=WEEKDAYS,
      y_kind="log_views", x_title="Weekday", y_label="views", controls=MONTH_CONTROLS,
      chart="weekday: median_rel_views by weekday (bar)"),

    # ---- Home and away ---------------------------------------------------------------
    T(id="travel_minor", group="Home and away",
      question="Is he more often minor at home or away?",
      kind="diff", x="traveling", y="minor", strata=DAILY, null="shift",
      x_label="while traveling", x_else="at home", y_label="minor-key songs",
      controls=DAILY_CONTROLS + "; circular-shift null (trips last days)",
      chart="travel_summary: minor_share home vs away by era (paired bars)"),
    T(id="travel_mood", group="Home and away",
      question="Does traveling change the mood mix?",
      kind="assoc", x="traveling", y="mood12", strata=DAILY, null="shift",
      x_order=[0.0, 1.0], x_names={0.0: "Home", 1.0: "Traveling"}, y_order=MOOD_ORDER,
      x_title="Traveling", y_label="mood",
      controls=DAILY_CONTROLS + "; circular-shift null",
      chart="travel_summary: mood shares home vs away (paired bars)"),
    T(id="travel_length", group="Home and away",
      question="Are songs on the road longer or shorter?",
      kind="diff", x="traveling", y="length", strata=DAILY, null="shift", y_kind="number",
      y_unit="s", x_label="while traveling", x_else="at home", y_label="length",
      controls=DAILY_CONTROLS + "; circular-shift null; length clipped to 30-480 s",
      chart="travel_summary: median_length (paired bars)"),
    T(id="travel_views", group="Home and away",
      question="Do songs from the road get more views?",
      kind="diff", x="traveling", y="log_views", strata=MONTHLY, null="shift",
      y_kind="log_views", x_label="from the road", x_else="from home", y_label="views",
      controls=MONTH_CONTROLS + "; circular-shift null",
      chart="travel_summary: median_rel_views (paired bars)"),

    # ---- Home eras (no strata: era is a stretch of time; random cut points as the null)
    T(id="era_minor", group="Home eras",
      question="Did the minor-key share change between homes?",
      kind="anova", x="home_era", y="minor", null="shift", min_shift=365, x_order=ERAS,
      x_names=ERA_NAMES, x_title="Home era", y_label="minor-key songs",
      controls="none (era is time itself); null cuts the timeline at random points "
               "(circular shift of at least a year)",
      chart="era_summary: minor_share by era (bar); mode_by_year (line)"),
    T(id="era_mood", group="Home eras",
      question="Did the mood mix change between homes?",
      kind="assoc", x="home_era", y="mood12", null="shift", min_shift=365, x_order=ERAS,
      x_names=ERA_NAMES, y_order=MOOD_ORDER, x_title="Home era", y_label="mood",
      controls="none (era is time itself); circular shift of at least a year",
      chart="era_summary: mood shares (stacked bars); mood_by_year (stacked area)"),
    T(id="era_tempo", group="Home eras",
      question="Did his tempo change between homes?",
      kind="anova", x="home_era", y="tempo", null="shift", min_shift=365, x_order=ERAS,
      x_names=ERA_NAMES, y_kind="number", y_unit="bpm", x_title="Home era",
      y_label="tempo", controls="none (era is time itself); circular shift of at least a year",
      chart="era_summary: median_tempo (bar); tempo_by_year (line with IQR band)"),
    T(id="era_length", group="Home eras",
      question="Did his song length change between homes?",
      kind="anova", x="home_era", y="length", null="shift", min_shift=365, x_order=ERAS,
      x_names=ERA_NAMES, y_kind="number", y_unit="s", x_title="Home era", y_label="length",
      controls="none (era is time itself); circular shift of at least a year",
      chart="era_summary: median_length (bar); length_by_year (line with IQR band)"),

    # ---- The beard ---------------------------------------------------------------------
    T(id="beard_mood", group="The beard",
      question="Does the beard change the mood?",
      kind="assoc", x="beard3", y="mood12", strata=DAILY, null="shift", min_shift=90,
      x_order=["Beard", "Shadow", "Clean"], y_order=MOOD_ORDER, x_title="Beard",
      y_label="mood", controls=DAILY_CONTROLS + "; circular-shift null (beards last months)",
      chart="beard_summary: mood shares by beard (stacked bars); beard_by_month (timeline)"),
    T(id="beard_minor", group="The beard",
      question="Is the bearded Jonathan more minor-key?",
      kind="anova", x="beard3", y="minor", strata=DAILY, null="shift", min_shift=90,
      x_order=["Beard", "Shadow", "Clean"], x_title="Beard", y_label="minor-key songs",
      controls=DAILY_CONTROLS + "; circular-shift null",
      chart="beard_summary: minor_share by beard (bar)"),
    T(id="beard_views", group="The beard",
      question="Does the beard get more views?",
      kind="anova", x="beard3", y="log_views", strata=MONTHLY, null="shift", min_shift=90,
      x_order=["Beard", "Shadow", "Clean"], y_kind="log_views", x_title="Beard",
      y_label="views", controls=MONTH_CONTROLS + "; circular-shift null",
      chart="beard_summary: median_rel_views by beard (bar)"),

    # ---- The news ----------------------------------------------------------------------
    T(id="news_items_dark", group="News",
      question="Busy news days, darker songs?",
      kind="slope", x="news_n_items", y="dark", strata=MONTHLY, x_step=10,
      x_unit="more headlines", x_label="on Wikipedia's current-events page",
      y_label="unhappy moods",
      controls="same month of the same year (the page's coverage changes by year)",
      chart="news_intensity_mood: dark_share by within-month headline quintile (bar)"),
    T(id="news_conflict_dark", group="News",
      question="Days with more war and attack headlines, darker songs?",
      kind="slope", x="news_section_armed_conflicts", y="dark", strata=MONTHLY, x_step=5,
      x_unit="more armed-conflict headlines", x_label="", y_label="unhappy moods",
      controls="same month of the same year",
      chart="news_by_month: armed_conflicts vs dark share (dual line)"),
    T(id="news_disaster_sad", group="News",
      question="Days with disasters in the news, sadder songs?",
      kind="slope", x="news_section_disasters_accidents", y="sad", strata=MONTHLY, x_step=3,
      x_unit="more disaster headlines", x_label="", y_label="Sad songs",
      controls="same month of the same year", chart="news_intensity_mood (bar)"),
    T(id="news_items_minor", group="News",
      question="Busy news days, more minor keys?",
      kind="slope", x="news_n_items", y="minor", strata=MONTHLY, x_step=10,
      x_unit="more headlines", x_label="", y_label="minor-key songs",
      controls="same month of the same year", chart="news_intensity_mood (bar)"),
    T(id="news_politics_topic", group="News",
      question="When politics fills the news, does he write about politics?",
      kind="slope", x="news_section_politics_elections", y="politics_topic", strata=MONTHLY,
      x_step=3, x_unit="more politics headlines", x_label="",
      y_label="songs tagged Politics or Trump", controls="same month of the same year",
      chart="news_by_month: politics_elections vs politics songs (dual line)"),
    T(id="news_song_views", group="News",
      question="Do songs about the day's news get more views?",
      kind="diff", x="news_song", y="log_views", strata=MONTHLY, y_kind="log_views",
      x_label="that clearly name that day's news (match excess >= 1)",
      x_else="other songs", y_label="views", controls=MONTH_CONTROLS,
      chart="news_matched_by_year: songs and median_rel_views (bar)"),
]


# =======================================================================================
# Time trends and the views model (their own tests)
# =======================================================================================

TREND_CHARTS = {"tempo": "tempo_by_year: median with q1-q3 band (line)",
                "length_raw": "length_by_year: median with q1-q3 band (line)",
                "minor": "mode_by_year: minor_share (line)",
                "dark": "mood_by_year: unhappy moods' share (stacked area)",
                "wild": "mood_by_year: high-energy moods' share (stacked area)"}


def trend_tests(df):
    """Year-on-year trends. Song-level tests would treat 6,500 autocorrelated songs as
    independent, so each trend uses one value per year (2009-2026; 2026 is partial) and a
    Kendall rank test, with an OLS slope per decade and its t-based 95% CI."""
    out = []
    specs = [
        ("trend_tempo", "Has his tempo drifted over the years?", "tempo", "median", "bpm"),
        ("trend_length", "Are the songs getting longer or shorter?", "length_raw", "median",
         "s"),
        ("trend_minor", "Is he writing more minor-key songs over time?", "minor", "mean",
         "share"),
        ("trend_dark", "Are the moods getting darker over time?", "dark", "mean", "share"),
        ("trend_wild", "Are the moods getting wilder over time?", "wild", "mean", "share"),
    ]
    for tid, question, col, how, unit in specs:
        yearly = df.groupby("year")[col].agg(how).dropna()
        n_songs = int(df[col].notna().sum())
        years = yearly.index.to_numpy(dtype=float)
        vals = yearly.to_numpy(dtype=float)
        tau, p = stats.kendalltau(years, vals)
        fit = stats.linregress(years, vals)
        tcrit = stats.t.ppf(0.975, len(years) - 2)
        slope, lo, hi = 10 * fit.slope, 10 * (fit.slope - tcrit * fit.stderr), \
            10 * (fit.slope + tcrit * fit.stderr)
        first, last = vals[0], vals[-1]
        if unit == "share":
            eff = (f"{100 * slope:+.1f} points per decade (95% CI {100 * lo:+.1f} to "
                   f"{100 * hi:+.1f}); Kendall tau = {tau:+.2f}")
            ans = (f"Yearly {how}: {pct(first)} in 2009, {pct(last)} in 2026; the fitted "
                   f"trend is {100 * slope:+.1f} points per decade (95% CI {100 * lo:+.1f} to "
                   f"{100 * hi:+.1f}).")
        else:
            eff = (f"{slope:+.1f} {unit} per decade (95% CI {lo:+.1f} to {hi:+.1f}); "
                   f"Kendall tau = {tau:+.2f}")
            ans = (f"Yearly {how}: {first:.0f} {unit} in 2009, {last:.0f} {unit} in 2026; the "
                   f"fitted trend is {slope:+.1f} {unit} per decade "
                   f"(95% CI {lo:+.1f} to {hi:+.1f}).")
        out.append(dict(id=tid, group="Trends over time", question=question, fun=False,
                        test=f"Kendall rank test on {len(years)} yearly {how}s; OLS slope "
                             f"with t-based CI",
                        controls="one value per year, so day-to-day autocorrelation can't "
                                 "inflate it; nothing else (this is the raw time trend)",
                        chart=TREND_CHARTS[col],
                        effect=eff, answer=ans, n=n_songs, p=float(p),
                        stats={"slope_per_decade": slope, "ci_low": lo, "ci_high": hi,
                               "kendall_tau": float(tau),
                               "yearly": {int(k): float(v) for k, v in yearly.items()}}))
    return out


def ols_hc1(X, y):
    """Least squares with heteroskedasticity-robust (HC1) standard errors."""
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    n, k = X.shape
    XtX_inv = np.linalg.pinv(X.T @ X)
    meat = (X * resid[:, None] ** 2).T @ X
    cov = XtX_inv @ meat @ XtX_inv * n / (n - k)
    return beta, cov, resid


def views_model(df, rng_seed=7):
    """What predicts views? log10(views + 1) regressed on the song's features, with a
    dummy for every month (so each song is only compared with songs the same age, from the
    same YouTube era). Each block of features gets a robust Wald test. Out-of-sample R^2
    from 5-fold cross-validation shows how much the features add beyond the month."""
    d = df[df["log_views"].notna() & df["length_raw"].notna()].copy()
    y = d["log_views"].to_numpy()
    blocks = {}

    def dummies(series, levels, prefix):
        return pd.DataFrame({f"{prefix}{lv}": (series == lv).astype(float) for lv in levels},
                            index=series.index)

    month = pd.get_dummies(d["year_month"], drop_first=False, dtype=float)
    topic_counts = pd.Series([t for ts in d["topics"] for t in ts]).value_counts()
    top_topics = [t for t in topic_counts.index if topic_counts[t] >= 30][:30]
    blocks["topic"] = pd.DataFrame({f"topic:{t}": d["topics"].apply(lambda ts: float(t in ts))
                                    for t in top_topics}, index=d.index)
    blocks["mood"] = dummies(d["mood12"], [m for m in MOOD_ORDER if m != "Pensive"], "mood:")
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
    blocks["weekday"] = dummies(d["weekday"], WEEKDAYS[1:], "weekday:")
    blocks["news_song"] = pd.DataFrame({"news_song": d["news_song"]}, index=d.index)
    blocks["beard"] = dummies(d["beard"].fillna(""), ["Shadow", "Clean"], "beard:")
    blocks["beard"]["beard:Other"] = (~d["beard"].isin(["Beard", "Shadow", "Clean"])).astype(float)

    feats = pd.concat([month] + list(blocks.values()), axis=1)
    X = feats.to_numpy(dtype=float)
    names = list(feats.columns)
    beta, cov, resid = ols_hc1(X, y)
    sst_within = float(((y - pd.Series(y).groupby(d["year_month"].to_numpy())
                         .transform("mean").to_numpy()) ** 2).sum())

    def r2(Xm):
        b, *_ = np.linalg.lstsq(Xm, y, rcond=None)
        return 1 - ((y - Xm @ b) ** 2).sum() / ((y - y.mean()) ** 2).sum()

    r2_month = r2(month.to_numpy())
    r2_full = r2(X)
    # Cross-validated R^2 (folds random but seeded).
    rng = np.random.default_rng(rng_seed)
    fold = rng.integers(0, 5, len(y))

    def cv_r2(Xm):
        pred = np.empty(len(y))
        for k in range(5):
            tr, te = fold != k, fold == k
            b, *_ = np.linalg.lstsq(Xm[tr], y[tr], rcond=None)
            pred[te] = Xm[te] @ b
        return 1 - ((y - pred) ** 2).sum() / ((y - y.mean()) ** 2).sum()

    cv_month, cv_full = cv_r2(month.to_numpy()), cv_r2(X)
    # Era alone (no month dummies), to show how much of "era" is just age.
    era_X = pd.get_dummies(d["home_era"], dtype=float).to_numpy()
    r2_era = r2(era_X)
    year_X = pd.get_dummies(d["year"], dtype=float).to_numpy()
    r2_year = r2(year_X)

    tests = []
    block_info = {}
    for bname, bdf in blocks.items():
        idx = [names.index(c) for c in bdf.columns]
        b = beta[idx]
        V = cov[np.ix_(idx, idx)]
        wald = float(b @ np.linalg.pinv(V) @ b)
        dof = len(idx)
        p = float(stats.chi2.sf(wald, dof))
        # Partial R^2 within months: how much this block adds on top of everything else.
        keep = [i for i in range(X.shape[1]) if i not in idx]
        b2, *_ = np.linalg.lstsq(X[:, keep], y, rcond=None)
        sse_without = ((y - X[:, keep] @ b2) ** 2).sum()
        partial = float((sse_without - (resid ** 2).sum()) / sst_within)
        coefs = []
        for i, nm in zip(idx, bdf.columns):
            se = math.sqrt(cov[i, i])
            coefs.append({"term": nm, "n": int(bdf[nm].astype(bool).sum())
                          if bname not in ("length",) else int(len(y)),
                          "multiplier": 10 ** beta[i],
                          "ci_low": 10 ** (beta[i] - 1.96 * se),
                          "ci_high": 10 ** (beta[i] + 1.96 * se), "p": float(
                              2 * stats.norm.sf(abs(beta[i] / se)))})
        block_info[bname] = {"wald_chi2": wald, "df": dof, "p": p,
                             "partial_r2_within_month": partial, "terms": coefs}
    # The blocks tested as findings. Traveling, weekday, news_song and beard have their own
    # tests above; their model p-values become diagnostics ("does it survive the other
    # features?") and join the FDR family too.
    labels = {"topic": ("views_topic", "Does what a song is about predict its views?"),
              "mood": ("views_mood", "Does a song's mood predict its views?"),
              "length": ("views_length", "Does a song's length predict its views?"),
              "instrument": ("views_instrument", "Does the main instrument predict views?"),
              "genre": ("views_genre", "Does the genre predict views?")}
    for bname, (tid, question) in labels.items():
        info = block_info[bname]
        terms = sorted(info["terms"], key=lambda t: -abs(math.log10(t["multiplier"])))
        if bname == "length":
            # Express length as the multiplier for a song twice as long, at the mean length.
            b1 = beta[names.index("log2_length")]
            se1 = math.sqrt(cov[names.index("log2_length"), names.index("log2_length")])
            m, lo, hi = 10 ** b1, 10 ** (b1 - 1.96 * se1), 10 ** (b1 + 1.96 * se1)
            eff = (f"doubling the length: x{m:.2f} views (95% CI x{lo:.2f} to x{hi:.2f}) at "
                   f"the typical length; block adds {pct(info['partial_r2_within_month'], 2)} "
                   f"of within-month variance")
            ans = (f"Against songs of the same month and with topic, mood, instrument and "
                   f"genre held fixed, a song twice as long gets x{m:.2f} the views "
                   f"(95% CI x{lo:.2f} to x{hi:.2f}).")
        else:
            show = [t for t in terms if t["n"] >= 30][:4]
            parts = "; ".join(f"{t['term'].split(':', 1)[1]} x{t['multiplier']:.2f} "
                              f"(CI x{t['ci_low']:.2f}-x{t['ci_high']:.2f}, n={t['n']})"
                              for t in show)
            base = {"topic": "songs on rarer topics (none of the 30 most common)",
                    "mood": "Pensive songs",
                    "instrument": "Acoustic Guitar songs", "genre": "Folk songs"}[bname]
            eff = (f"block adds {pct(info['partial_r2_within_month'], 2)} of within-month "
                   f"variance; biggest: {parts}")
            ans = (f"Compared with {base} from the same month (other features held fixed), "
                   f"the biggest differences are {parts}. Together the {bname} terms explain "
                   f"{pct(info['partial_r2_within_month'], 2)} of the variation in views "
                   f"within a month.")
        tests.append(dict(id=tid, group="What predicts views", question=question, fun=False,
                          test=f"OLS on log10 views with month dummies; robust (HC1) Wald "
                               f"chi-square, {info['df']} df",
                          controls="month of upload (age and YouTube era) and every other "
                                   "feature in the model: topic, mood, length, instrument, "
                                   "genre, traveling, weekday, news song, beard",
                          chart="views_model: block partial R^2 (bar) and term multipliers "
                                "with CIs (dot plot)",
                          effect=eff, answer=ans, n=int(len(y)), p=info["p"],
                          stats={k: v for k, v in info.items() if k != "terms"}))
    summary = {"n": int(len(y)), "r2_month_only": r2_month, "r2_full": r2_full,
               "cv_r2_month_only": cv_month, "cv_r2_full": cv_full,
               "r2_era_only": r2_era, "r2_year_only": r2_year, "blocks": block_info}
    checks = []
    for bname in ("traveling", "weekday", "news_song", "beard"):
        info = block_info[bname]
        checks.append(dict(id=f"model:{bname}", of=MODEL_CHECKS_OF[bname], p=info["p"],
                           n=int(len(y)),
                           effect="; ".join(f"{t['term'].split(':', 1)[-1]} x{t['multiplier']:.2f}"
                                            f" (95% CI x{t['ci_low']:.2f} to x{t['ci_high']:.2f})"
                                            for t in info["terms"]),
                           test=f"robust (HC1) Wald chi-square for the {bname} block in the "
                                f"views model, {info['df']} df"))
    return tests, summary, checks


# The single tests that the views model checks again with every other feature held fixed.
MODEL_CHECKS_OF = {"traveling": "travel_views", "weekday": "weekday_views",
                   "news_song": "news_song_views", "beard": "beard_views"}


# =======================================================================================
# FDR and verdicts
# =======================================================================================

def bh_qvalues(pvals):
    """Benjamini-Hochberg adjusted p-values (q-values)."""
    p = np.asarray(pvals, dtype=float)
    n = len(p)
    order = np.argsort(p)
    ranked = p[order] * n / np.arange(1, n + 1)
    q = np.minimum.accumulate(ranked[::-1])[::-1]
    out = np.empty(n)
    out[order] = np.minimum(q, 1.0)
    return out


def verdict(f):
    """The label and a one-line reason for it, from the q-values (rules in the docstring)."""
    q, raw_q, model_q = f["q_value"], f.get("raw_q_value"), f.get("model_check_q")
    if q < 0.05 and f.get("inseparable"):
        return "confounded", (f"Shows up (q {eq(q)}), but {f['inseparable']} explains it "
                              f"just as well, so it can't be pinned on this.")
    if q < 0.05 and model_q is not None and model_q >= 0.05:
        return "confounded", (f"Real within the month (q {eq(q)}), but it fades once the views "
                              f"model holds topic, mood, length and the rest fixed "
                              f"(q {eq(model_q)}): it is mostly what the songs are about.")
    if q < 0.01:
        return "real", f"q {eq(q)}: very unlikely to be chance, even after {N_FDR_NOTE}."
    if q < 0.05:
        return "probably real", f"q {eq(q)}: unlikely to be chance after {N_FDR_NOTE}."
    if raw_q is not None and raw_q < 0.05:
        return "confounded", (f"Looks real without controls (q {eq(raw_q)}), but not once "
                              f"songs are compared like with like (q {eq(q)}).")
    if f["fun"]:
        return "fun null", f"q {eq(q)}: a superstition that shows nothing here."
    return "noise", f"q {eq(q)}: no detectable effect."


N_FDR_NOTE = "correcting for every test run"


TEST_NAMES = {
    ("diff", "perm"): "stratified permutation test of a Mantel-Haenszel-weighted difference",
    ("diff", "shift"): "circular-shift test of a Mantel-Haenszel-weighted difference",
    ("slope", "perm"): "stratified permutation test of a within-stratum slope",
    ("slope", "shift"): "circular-shift test of a within-stratum slope",
    ("slope", "block"): "month-block permutation test of a within-year slope",
    ("assoc", "perm"): "stratified permutation chi-square (expected counts within strata)",
    ("assoc", "shift"): "circular-shift chi-square (expected counts within strata)",
    ("assoc", "block"): "block permutation chi-square (expected counts within strata)",
    ("anova", "perm"): "stratified permutation test of between-group variance",
    ("anova", "shift"): "circular-shift test of between-group variance",
    ("anova", "block"): "month-block permutation test of between-group variance",
}


def run_all_tests(df, n_perm, n_perm_raw):
    findings, diagnostics = [], []
    for spec in TESTS:
        t0 = time.time()
        res = run_permutation(spec, df, spec["strata"], n_perm)
        effect, answer, st = describe(spec, res)
        f = dict(id=spec["id"], group=spec["group"], question=spec["question"],
                 fun=spec["fun"], inseparable=spec.get("inseparable"),
                 test=f"{TEST_NAMES[(spec['kind'], spec['null'])]}, {n_perm} shuffles",
                 controls=spec["controls"], chart=spec["chart"], effect=effect,
                 answer=answer, n=int(len(res["y"])), p=res["p"], stats=st,
                 kind=spec["kind"], y_kind=spec["y_kind"], y_unit=spec.get("y_unit", ""))
        if spec["strata"]:
            raw = run_permutation(spec, df, [], n_perm_raw, seed_suffix=":raw")
            raw_spec = dict(spec, strata=[])
            raw_effect, _, raw_st = describe(raw_spec, raw)
            f["raw_p"] = raw["p"]
            f["raw_effect"] = raw_effect
            diagnostics.append(dict(id=spec["id"] + ":raw", of=spec["id"], p=raw["p"],
                                    effect=raw_effect, n=int(len(raw["y"])),
                                    test=f"{TEST_NAMES[(spec['kind'], spec['null'])]} with "
                                         f"no strata, {n_perm_raw} shuffles"))
        findings.append(f)
        print(f"  {spec['id']:<22} p={fmt_p(f['p']):>8}  raw p={fmt_p(f.get('raw_p')):>8}"
              f"  ({time.time() - t0:.1f}s)", flush=True)
    return findings, diagnostics


# =======================================================================================
# Aggregates for charts
# =======================================================================================

def r(v, digits=2):
    """Round for JSON; NaN becomes null."""
    if v is None:
        return None
    try:
        if isinstance(v, (float, np.floating)) and not np.isfinite(v):
            return None
    except TypeError:
        return v
    if isinstance(v, (np.integer, int)):
        return int(v)
    return round(float(v), digits)


def matrix(df, row, col, rows, cols):
    """Counts of df[row] x df[col] as a nested list, rows x cols."""
    ct = pd.crosstab(df[row], df[col]).reindex(index=rows, columns=cols, fill_value=0)
    return ct.to_numpy().astype(int).tolist()


def quantiles(s):
    s = s.dropna()
    if len(s) == 0:
        return None, None, None
    q = s.quantile([0.25, 0.5, 0.75]).to_numpy()
    return r(q[0], 1), r(q[1], 1), r(q[2], 1)


def summary_by(df, key, levels, extra=None):
    """Common per-group summary: songs, mood shares, minor share, tempo, length, views."""
    out = []
    for lv in levels:
        g = df[df[key] == lv]
        if len(g) == 0:
            continue
        row = {"value": lv if not isinstance(lv, (np.floating, float)) else r(lv, 2),
               "songs": int(len(g)),
               "minor_share": r(g["minor"].mean(), 4),
               "wild_share": r(g["wild"].mean(), 4),
               "dark_share": r(g["dark"].mean(), 4),
               "sad_share": r(g["sad"].mean(), 4),
               "median_tempo": r(g["tempo"].median(), 1),
               "median_length": r(g["length_raw"].median(), 1),
               "median_rel_views": r(g["rel_views"].median(), 3)}
        if extra:
            row.update(extra(g))
        out.append(row)
    return out


def build_aggregates(df):
    agg = {}
    years = sorted(df["year"].unique().tolist())
    agg["meta"] = {
        "source": "dataset/songaday.csv", "songs": int(len(df)),
        "first": {"number": int(df["number"].min()), "date": str(df["date"].min().date())},
        "last": {"number": int(df["number"].max()), "date": str(df["date"].max().date())},
        "made_by": "analysis/analyze.py",
        "notes": ["Matrices are rows x columns as named by their keys.",
                  "rel_views = views / median views of songs from the same month (age-fair).",
                  "Shares are fractions 0-1. minor_share counts only songs with a known mode.",
                  "Moods outside the top 11 are pooled as Other in mood matrices."]}

    # Songs per year
    agg["songs_per_year"] = {"years": years,
                             "songs": [int((df["year"] == y).sum()) for y in years],
                             "first_number": [int(df.loc[df["year"] == y, "number"].min())
                                              for y in years]}

    # Mood mix by year: every mood with at least 30 songs, the rest as Other
    mood_counts = df["mood"].value_counts()
    moods30 = [m for m in mood_counts.index if mood_counts[m] >= 30]
    mood_any = df["mood"].where(df["mood"].isin(moods30), "Other")
    tmp = df.assign(mood_any=mood_any)
    agg["mood_by_year"] = {"years": years, "moods": moods30 + ["Other"],
                           "counts": matrix(tmp, "mood_any", "year", moods30 + ["Other"], years),
                           "layout": "moods x years"}
    agg["mood_totals"] = [{"mood": m, "songs": int(c)} for m, c in mood_counts.items()]

    # Keys and mode by year
    keys = ["C", "Db", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B",
            "Cm", "C#m", "Dm", "Ebm", "Em", "Fm", "F#m", "Gm", "G#m", "Am", "Bbm", "Bm"]
    agg["key_by_year"] = {"years": years, "keys": keys,
                          "counts": matrix(df, "key", "year", keys, years),
                          "layout": "keys x years",
                          "note": "Root-only keys in #212-#271 and #358-#727 count under the "
                                  "major spelling; mode for those is unknown."}
    agg["key_totals"] = [{"key": k, "songs": int((df["key"] == k).sum())} for k in keys]
    agg["mode_by_year"] = {
        "years": years,
        "major": [int(((df["year"] == y) & (df["mode"] == "major")).sum()) for y in years],
        "minor": [int(((df["year"] == y) & (df["mode"] == "minor")).sum()) for y in years],
        "unknown": [int(((df["year"] == y) & (df["mode"] == "unknown")).sum()) for y in years],
        "minor_share": [r(df.loc[df["year"] == y, "minor"].mean(), 4) for y in years]}

    # Tempo and length by year, and histograms
    for col, name, width, top in [("tempo", "tempo", 5, 240), ("length_raw", "length", 10, 600)]:
        rows = {"years": years, "n": [], "q1": [], "median": [], "q3": [], "mean": []}
        for y in years:
            s = df.loc[df["year"] == y, col]
            q1, med, q3 = quantiles(s)
            rows["n"].append(int(s.notna().sum()))
            rows["q1"].append(q1)
            rows["median"].append(med)
            rows["q3"].append(q3)
            rows["mean"].append(r(s.mean(), 1))
        agg[f"{name}_by_year"] = rows
        edges = list(range(0, top + width, width))
        s = df[col].dropna()
        counts, _ = np.histogram(s.clip(upper=top - 0.001), bins=edges)
        agg[f"{name}_hist"] = {"bin_edges": edges, "counts": counts.astype(int).tolist(),
                               "unit": "bpm" if name == "tempo" else "s",
                               "median": r(s.median(), 1),
                               "note": f"values above {top} counted in the last bin"}
    agg["length_by_era_hist"] = {
        "eras": ERAS, "bin_edges": list(range(0, 610, 10)),
        "counts": [np.histogram(df.loc[df["home_era"] == e, "length_raw"].dropna()
                                .clip(upper=599.999), bins=list(range(0, 610, 10)))[0]
                   .astype(int).tolist() for e in ERAS]}

    # Instruments by year (top 15, any position in the instruments list)
    inst = df[["year", "instruments"]].explode("instruments").dropna().reset_index(drop=True)
    top_inst = inst["instruments"].value_counts().head(15).index.tolist()
    per_year = df.groupby("year").size()
    ct = pd.crosstab(inst["instruments"], inst["year"]).reindex(index=top_inst, columns=years,
                                                                fill_value=0)
    agg["instruments_by_year"] = {
        "years": years, "instruments": top_inst, "songs_with": ct.to_numpy().astype(int).tolist(),
        "share": (ct / per_year.reindex(years).to_numpy()).round(4).to_numpy().tolist(),
        "layout": "instruments x years"}
    agg["main_instrument_totals"] = [{"instrument": k, "songs": int(v)} for k, v in
                                     df["main_instrument"].value_counts().head(30).items()]

    # Beard timeline by month
    months = sorted(df["year_month"].unique())
    beard_states = ["Beard", "Shadow", "Clean", "Mustache", "Goatee"]
    agg["beard_by_month"] = {
        "months": months, "states": beard_states,
        "counts": matrix(df, "beard", "year_month", beard_states, months),
        "layout": "states x months",
        "dominant": [df.loc[df["year_month"] == m, "beard"].mode().iloc[0]
                     if df.loc[df["year_month"] == m, "beard"].notna().any() else None
                     for m in months]}

    # Genre mix by year
    genre_counts = df["genre"].value_counts()
    top_genres = genre_counts.index[:8].tolist()
    g_any = df.assign(genre_any=df["genre"].where(df["genre"].isin(top_genres), "Other"))
    agg["genre_by_year"] = {"years": years, "genres": top_genres + ["Other"],
                            "counts": matrix(g_any, "genre_any", "year", top_genres + ["Other"],
                                             years), "layout": "genres x years"}

    # Topics and proper nouns
    tp = df[["year", "number", "topics"]].explode("topics").dropna().reset_index(drop=True)
    tcount = tp["topics"].value_counts()
    agg["topics_top"] = [
        {"topic": t, "songs": int(c), "first_year": int(tp.loc[tp["topics"] == t, "year"].min()),
         "last_year": int(tp.loc[tp["topics"] == t, "year"].max()),
         "median_rel_views": r(df.loc[df["topics"].apply(lambda ts, t=t: t in ts),
                                      "rel_views"].median(), 3)}
        for t, c in tcount.head(60).items()]
    agg["topics_by_year"] = {str(y): [[t, int(c)] for t, c in
                                      tp.loc[tp["year"] == y, "topics"].value_counts().head(12)
                                      .items()] for y in years}
    pn = df[["year", "proper_nouns"]].explode("proper_nouns").dropna().reset_index(drop=True)
    agg["proper_nouns_top"] = [{"name": k, "songs": int(v)} for k, v in
                               pn["proper_nouns"].value_counts().head(60).items()]
    agg["proper_nouns_by_year"] = {
        "tagged_songs": {str(y): int((df.loc[df["year"] == y, "proper_nouns"].str.len() > 0)
                                     .sum()) for y in years},
        "top": {str(y): [[k, int(v)] for k, v in
                         pn.loc[pn["year"] == y, "proper_nouns"].value_counts().head(10).items()]
                for y in years},
        "note": "proper nouns are tagged on only about a quarter of songs; tagged_songs says "
                "how many per year"}

    # Locations
    locs = []
    for place, g in df.groupby("place"):
        g = g.sort_values("number")
        locs.append({"place": place, "lat": r(g["place_lat"].iloc[0], 4),
                     "lon": r(g["place_lon"].iloc[0], 4), "city": g["place_city"].iloc[0],
                     "region": g["place_region"].iloc[0], "country": g["place_country"].iloc[0],
                     "songs": int(len(g)), "home_songs": int(g["is_home"].sum()),
                     "first_date": str(g["date"].iloc[0].date()),
                     "last_date": str(g["date"].iloc[-1].date()),
                     "first_number": int(g["number"].iloc[0]),
                     "last_number": int(g["number"].iloc[-1]),
                     "eras": sorted(g["home_era"].unique().tolist(), key=ERAS.index)})
    locs.sort(key=lambda d: -d["songs"])
    agg["locations"] = locs
    agg["countries"] = [{"country": k, "songs": int(v)} for k, v in
                        df["place_country"].value_counts().items()]

    # Weekdays
    agg["weekday"] = summary_by(df, "weekday", WEEKDAYS, extra=lambda g: {
        "tired_or_sad_share": r(g["tired_or_sad"].mean(), 4),
        "mood_shares": {m: r((g["mood12"] == m).mean(), 4) for m in MOOD_ORDER}})

    # Views
    v = df[df["views"].notna()].sort_values("views", ascending=False)
    agg["views_top50"] = [{"number": int(x.number), "title": x.title,
                           "date": str(x.date.date()), "views": int(x.views),
                           "topic": x.main_topic, "mood": x.mood, "genre": x.genre,
                           "place": x.place} for x in v.head(50).itertuples()]
    ok = df[df["views_ok"]]
    agg["views_by_year"] = {
        "years": years, "songs": [int((ok["year"] == y).sum()) for y in years],
        "median": [r(ok.loc[ok["year"] == y, "views"].median(), 0) for y in years],
        "q1": [r(ok.loc[ok["year"] == y, "views"].quantile(0.25), 0) for y in years],
        "q3": [r(ok.loc[ok["year"] == y, "views"].quantile(0.75), 0) for y in years],
        "total": [r(df.loc[df["year"] == y, "views"].sum(), 0) for y in years],
        "max": [r(df.loc[df["year"] == y, "views"].max(), 0) for y in years],
        "note": "median/q1/q3 use songs whose video is up, was uploaded within 30 days and has "
                "been online 30+ days; total/max use every counted video"}
    topic_rows = []
    for t, c in tcount.items():
        if c < 25:
            continue
        g = ok[ok["topics"].apply(lambda ts, t=t: t in ts)]
        topic_rows.append({"topic": t, "songs": int(len(g)),
                           "median_views": r(g["views"].median(), 0),
                           "median_rel_views": r(g["rel_views"].median(), 3)})
    agg["views_by_topic"] = sorted(topic_rows, key=lambda d: -(d["median_rel_views"] or 0))
    agg["views_by_mood"] = [{"mood": m, "songs": int((ok["mood12"] == m).sum()),
                             "median_views": r(ok.loc[ok["mood12"] == m, "views"].median(), 0),
                             "median_rel_views": r(ok.loc[ok["mood12"] == m, "rel_views"]
                                                   .median(), 3)} for m in MOOD_ORDER]
    edges = [0, 60, 90, 120, 150, 180, 240, 300, 10000]
    labels = ["<1:00", "1:00-1:30", "1:30-2:00", "2:00-2:30", "2:30-3:00", "3:00-4:00",
              "4:00-5:00", "5:00+"]
    lb = pd.cut(ok["length_raw"], edges, labels=labels, right=False)
    agg["views_by_length"] = [{"bucket": lab, "songs": int((lb == lab).sum()),
                               "median_views": r(ok.loc[lb == lab, "views"].median(), 0),
                               "median_rel_views": r(ok.loc[lb == lab, "rel_views"].median(), 3)}
                              for lab in labels]
    agg["views_by_genre"] = [{"genre": gname, "songs": int((ok["genre"] == gname).sum()),
                              "median_rel_views": r(ok.loc[ok["genre"] == gname, "rel_views"]
                                                    .median(), 3)} for gname in top_genres]
    agg["views_by_instrument"] = [
        {"instrument": i, "songs": int((ok["main_instrument"] == i).sum()),
         "median_rel_views": r(ok.loc[ok["main_instrument"] == i, "rel_views"].median(), 3)}
        for i in df["main_instrument"].value_counts().index[:15]]

    # Moon
    agg["moon_phase_mood"] = {"phases": MOON_PHASES, "moods": MOOD_ORDER,
                              "counts": matrix(df, "moon_phase", "mood12", MOON_PHASES,
                                               MOOD_ORDER), "layout": "phases x moods"}
    agg["moon_phase_summary"] = (
        summary_by(df, "moon_phase", MOON_PHASES)
        + summary_by(df[df["supermoon"] == 1].assign(sm="supermoon (full)"), "sm",
                     ["supermoon (full)"])
        + summary_by(df[df["full_moon"] == 1].assign(fm="full-moon day"), "fm",
                     ["full-moon day"]))
    agg["moon_sign_mood"] = {"signs": SIGNS, "moods": MOOD_ORDER,
                             "counts": matrix(df, "moon_sign", "mood12", SIGNS, MOOD_ORDER),
                             "layout": "signs x moods"}
    agg["sun_sign_mood"] = {"signs": SIGNS, "moods": MOOD_ORDER,
                            "counts": matrix(df, "sun_sign", "mood12", SIGNS, MOOD_ORDER),
                            "layout": "signs x moods"}
    agg["sun_sign_summary"] = summary_by(df, "sun_sign", SIGNS)
    agg["eclipses"] = [{"number": int(x.number), "date": str(x.date.date()), "kind": x.eclipse_kind,
                        "title": x.title, "mood": x.mood}
                       for x in df[df["eclipse"] == 1].itertuples()]
    agg["friday13"] = [{"number": int(x.number), "date": str(x.date.date()), "title": x.title,
                        "mood": x.mood} for x in df[df["friday13"] == 1].itertuples()]

    # Mercury, retrogrades, planets
    mer = df.assign(mer=df["mercury_retro"].map({1.0: "retrograde", 0.0: "direct"}))
    agg["mercury_summary"] = summary_by(mer, "mer", ["retrograde", "direct"], extra=lambda g: {
        "chaos_share": r(g["chaos"].mean(), 4),
        "mood_shares": {m: r((g["mood12"] == m).mean(), 4) for m in MOOD_ORDER}})
    agg["retrograde_summary"] = summary_by(df, "retro_count", sorted(df["retro_count"].unique()))
    arc_edges = list(range(60, 300, 30))
    arc_labels = [f"{a}-{b}" for a, b in zip(arc_edges[:-1], arc_edges[1:])]
    arc_bin = pd.cut(df["planet_arc"], arc_edges, labels=arc_labels, right=False)
    agg["planet_arc_binned"] = {
        "bin_edges": arc_edges,
        "rows": summary_by(df.assign(b=arc_bin.astype(object)), "b", arc_labels),
        "note": "arc in degrees; smaller = planets more bunched up (a 'planet parade')"}
    cbin = df["conj_pairs"].clip(upper=3).map({0: "0", 1: "1", 2: "2", 3: "3+"})
    agg["conjunction_summary"] = summary_by(df.assign(cb=cbin), "cb", ["0", "1", "2", "3+"],
                                            extra=lambda g: {"mood_shares": {
                                                m: r((g["mood12"] == m).mean(), 4)
                                                for m in MOOD_ORDER}})

    # Weather
    agg["weather_mood"] = {"labels": WEATHER_LABELS, "moods": MOOD_ORDER,
                           "counts": matrix(df, "weather_label", "mood12", WEATHER_LABELS,
                                            MOOD_ORDER), "layout": "labels x moods"}
    agg["weather_summary"] = summary_by(df, "weather_label", WEATHER_LABELS)
    t_edges = list(range(-20, 45, 5))
    t_labels = [f"{a} to {b} C" for a, b in zip(t_edges[:-1], t_edges[1:])]
    tb = pd.cut(df["temp"], t_edges, labels=t_labels, right=False).astype(object)
    t_rows = []
    for lab in t_labels:
        g = df[tb == lab]
        if len(g) < 10:
            continue
        q1, _, q3 = quantiles(g["tempo"])
        t_rows.append(dict(summary_by(g.assign(b=lab), "b", [lab])[0], tempo_q1=q1,
                           tempo_q3=q3, mean_tempo=r(g["tempo"].mean(), 1)))
    agg["temperature_binned"] = {
        "bin_edges_c": t_edges, "rows": t_rows,
        "note": "daily mean temperature; raw, not controlled for season or place (warm bins "
                "are mostly summer and Berkeley); see findings temp_tempo for the controlled "
                "slope"}
    p_edges = [0, 0.1, 1, 5, 15, 1000]
    p_labels = ["dry (<0.1 mm)", "trace (0.1-1 mm)", "light (1-5 mm)", "wet (5-15 mm)",
                "very wet (15+ mm)"]
    pb = pd.cut(df["precip"], p_edges, labels=p_labels, right=False).astype(object)
    agg["precip_binned"] = summary_by(df.assign(pb=pb), "pb", p_labels)

    # Month of year (season, daylight)
    agg["month_of_year"] = summary_by(df, "month", list(range(1, 13)), extra=lambda g: {
        "mean_daylight_h": r(g["daylight_h"].mean(), 2), "mean_temp_c": r(g["temp"].mean(), 1),
        "mood_shares": {m: r((g["mood12"] == m).mean(), 4) for m in MOOD_ORDER}})

    # Home, travel, eras, beard
    era_rows = []
    for e in ERAS:
        g = df[df["home_era"] == e]
        era_rows.append(dict(
            era=e, name=ERA_NAMES[e], songs=int(len(g)),
            first_number=int(g["number"].min()), last_number=int(g["number"].max()),
            first_date=str(g["date"].min().date()), last_date=str(g["date"].max().date()),
            home_share=r(g["is_home"].mean(), 4), minor_share=r(g["minor"].mean(), 4),
            wild_share=r(g["wild"].mean(), 4), dark_share=r(g["dark"].mean(), 4),
            median_tempo=r(g["tempo"].median(), 1), median_length=r(g["length_raw"].median(), 1),
            median_views=r(g.loc[g["views_ok"], "views"].median(), 0),
            mean_high_c=r(g["temp_max"].mean(), 1),
            mood_shares={m: r((g["mood12"] == m).mean(), 4) for m in MOOD_ORDER},
            top_topics=[[t, int(c)] for t, c in g["topics"].explode().dropna()
                        .value_counts().head(8).items()]))
    agg["era_summary"] = era_rows
    trav = df.assign(where_=df["traveling"].map({1.0: "traveling", 0.0: "home"}))
    agg["travel_summary"] = {
        "overall": summary_by(trav, "where_", ["home", "traveling"], extra=lambda g: {
            "mood_shares": {m: r((g["mood12"] == m).mean(), 4) for m in MOOD_ORDER}}),
        "by_era": {e: summary_by(trav[trav["home_era"] == e], "where_", ["home", "traveling"])
                   for e in ERAS}}
    agg["beard_summary"] = summary_by(df, "beard", beard_states, extra=lambda g: {
        "mood_shares": {m: r((g["mood12"] == m).mean(), 4) for m in MOOD_ORDER}})

    # News
    sec_cols = [c for c in df.columns if c.startswith("news_section_")]
    nm = df.groupby("year_month")
    agg["news_by_month"] = {
        "months": months, "mean_items": [r(nm["news_n_items"].mean()[m], 2) for m in months],
        "sections": {c.replace("news_section_", ""): [r(nm[c].mean()[m], 2) for m in months]
                     for c in sec_cols},
        "dark_share": [r(nm["dark"].mean()[m], 4) for m in months],
        "politics_song_share": [r(nm["politics_topic"].mean()[m], 4) for m in months],
        "note": "mean headline items per day on Wikipedia's Portal:Current events; coverage "
                "changes by year, so compare shapes, not levels across years. Sections before "
                "about April 2010 come from a classifier."}
    q = df.groupby("year_month")["news_n_items"].rank(pct=True)
    qb = pd.cut(q, [0, 0.2, 0.4, 0.6, 0.8, 1.0], labels=["Q1 quietest", "Q2", "Q3", "Q4",
                                                         "Q5 busiest"], include_lowest=True)
    agg["news_intensity_mood"] = summary_by(df.assign(qb=qb.astype(object)), "qb",
                                            ["Q1 quietest", "Q2", "Q3", "Q4", "Q5 busiest"],
                                            extra=lambda g: {
                                                "politics_song_share":
                                                    r(g["politics_topic"].mean(), 4)})
    ns = df[df["news_song"] == 1]
    agg["news_matched_by_year"] = {
        "years": years, "songs": [int((ns["year"] == y).sum()) for y in years],
        "share": [r((ns["year"] == y).sum() / (df["year"] == y).sum(), 4) for y in years],
        "median_rel_views": [r(ns.loc[ns["year"] == y, "rel_views"].median(), 3) for y in years],
        "top": {str(y): [{"number": int(x.number), "title": x.title,
                          "terms": x.news_terms.split("|")[:3],
                          "excess": r(x.news_excess, 2)}
                         for x in ns[ns["year"] == y].sort_values("news_excess",
                                                                  ascending=False).head(5)
                         .itertuples()] for y in years},
        "note": "news song = news_match_excess >= 1 (names that day's news clearly more than "
                "the same song would a year earlier or later)"}

    # Per-song compact table for scatter plots and calendars (column arrays, codes into
    # the label lists).
    def codes(series, labels):
        m = {lab: i for i, lab in enumerate(labels)}
        return [m.get(v, len(labels) - 1) if isinstance(v, str) and v else None for v in series]

    inst_labels = df["main_instrument"].value_counts().index[:15].tolist() + ["Other"]
    topic_labels = tcount.index[:40].tolist() + ["Other"]
    place_labels = [d["place"] for d in locs]
    agg["songs_compact"] = {
        "note": "one entry per song, ordered by number (starting at 1); *_code fields index "
                "the matching *_labels list; null = unknown",
        "first_number": int(df["number"].min()),
        "mood_labels": moods30 + ["Other"], "era_labels": ERAS,
        "beard_labels": beard_states, "genre_labels": top_genres + ["Other"],
        "instrument_labels": inst_labels, "topic_labels": topic_labels,
        "place_labels": place_labels,
        "mood_code": codes(mood_any, moods30 + ["Other"]),
        "tempo": [r(v, 0) for v in df["tempo"]],
        "length": [r(v, 0) for v in df["length_raw"]],
        "minor": [None if pd.isna(v) else int(v) for v in df["minor"]],
        "era_code": codes(df["home_era"], ERAS),
        "home": [int(v) for v in df["is_home"]],
        "views": [None if pd.isna(v) else int(v) for v in df["views"]],
        "beard_code": codes(df["beard"].fillna(""), beard_states),
        "genre_code": codes(df["genre"].where(df["genre"].isin(top_genres), "Other"),
                            top_genres + ["Other"]),
        "instrument_code": codes(df["main_instrument"].where(
            df["main_instrument"].isin(inst_labels), "Other"), inst_labels),
        "topic_code": codes(df["main_topic"].where(df["main_topic"].isin(topic_labels) |
                                                   (df["main_topic"] == ""), "Other"),
                            topic_labels),
        "place_code": codes(df["place"], place_labels),
        "temp_c": [r(v, 1) for v in df["temp"]],
        "moon_illum": [r(v, 2) for v in df["moon_illum"]],
    }
    return agg


# =======================================================================================
# Writing
# =======================================================================================

def clean_json(obj):
    """Make an object JSON-safe: numpy scalars to Python, NaN to None, floats rounded."""
    if isinstance(obj, dict):
        return {str(k): clean_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean_json(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (float, np.floating)):
        return None if not np.isfinite(obj) else float(f"{float(obj):.6g}")
    if isinstance(obj, np.bool_):
        return bool(obj)
    return obj


VERDICT_ORDER = ["real", "probably real", "confounded", "fun null", "noise"]


def brief(effect):
    """The core of an effect string: the biggest cell, or the estimate without its CI."""
    if "biggest cell " in effect:
        return effect.split("biggest cell ", 1)[1]
    return effect.split(" (95% CI")[0].split(";")[0]


def short_summary(f):
    """A one-line version of a finding's effect, for the summary at the top of findings.md."""
    st, kind, eff = f["stats"], f.get("kind"), f["effect"]
    if kind == "diff":
        if f["y_kind"] == "binary":
            return (f"{pct(st['mean_exposed'])} vs {pct(st['mean_other'])}, "
                    f"{100 * st['estimate']:+.1f} points like-for-like")
        if f["y_kind"] == "log_views":
            return f"{100 * (10 ** st['estimate'] - 1):+.0f}% views against same-month songs"
        u = f["y_unit"]
        return (f"{st['mean_exposed']:.1f} vs {st['mean_other']:.1f} {u}, "
                f"{st['estimate']:+.1f} {u} like-for-like")
    if kind == "anova":
        return eff.split("; ", 1)[1]
    if kind == "assoc":
        return "biggest departure " + eff.split("biggest cell ", 1)[1]
    if "; biggest: " in eff:
        head, tail = eff.split("; biggest: ", 1)
        return f"{head}; biggest: {tail.split(';')[0]}"
    return eff.split(";")[0]


def write_markdown(findings, diagnostics, model, n_tests, n_perm, path):
    by = {v: [f for f in findings if f["verdict"] == v] for v in VERDICT_ORDER}
    L = []
    L.append("# What the Song A Day data says")
    L.append("")
    L.append(f"{len(findings)} questions about {model['songs']:,} songs "
             f"(#1, 2009-01-01, to #{model['last']}, {model['last_date']}), each tested "
             f"against chance with the confounds held fixed. Made by `analysis/analyze.py` "
             f"from `dataset/songaday.csv`; every number here is in `findings.json`.")
    L.append("")
    L.append("**How to read it.** Each answer compares like with like: songs from the same "
             "year and home (and season, or month, when the question needs it), because his "
             "tagging, his home, the weather and YouTube all changed over 17 years. *p* is "
             "how often shuffled data looks as striking as the real data. *q* is *p* "
             f"corrected for running {n_tests} tests (Benjamini-Hochberg): with this many "
             "tests a few p-values under 0.05 turn up by luck alone, and *q* accounts for "
             "that. Verdicts: **real** q < 0.01, **probably real** q < 0.05, **confounded** "
             "(the raw pattern exists but is explained by something else), **fun null** (a "
             "famous superstition that shows nothing) and **noise**.")
    L.append("")

    def block(f, detail=True):
        out = [f"### {f['question']}", "",
               f"**{f['verdict']}** · q {eq(f['q_value'])} · p {eq(f['p_value'])} "
               f"· n = {f['n']:,}", "", f["answer"], "", f"*{f['verdict_reason']}*", ""]
        if detail:
            out.append(f"- Effect: {f['effect']}")
            out.append(f"- Controls: {f['controls']}")
            if f.get("raw_effect"):
                out.append(f"- Without controls: {f['raw_effect']} "
                           f"(raw p {eq(f['raw_p'])}, q {eq(f['raw_q_value'])})")
            if f.get("model_check"):
                out.append(f"- {f['model_check']}")
            if f.get("note"):
                out.append(f"- Note: {f['note']}")
            out.append(f"- Test: {f['test']}")
            out.append(f"- Chart: {f['chart']}")
            out.append("")
        return out

    def ranked(fs):
        return sorted(fs, key=lambda f: (-f.get("interest", 0), f["q_value"]))

    L.append("## In short")
    L.append("")
    for f in sorted(by["real"] + by["probably real"], key=lambda f: -f.get("interest", 0))[:10]:
        L.append(f"- **{f['question']}** {f['verdict'].capitalize()}: {short_summary(f)} "
                 f"(q {eq(f['q_value'])}).")
    for f in sorted(by["fun null"], key=lambda f: -f.get("interest", 0))[:6]:
        L.append(f"- **{f['question']}** No: {short_summary(f)} (q {eq(f['q_value'])}).")
    if by["confounded"]:
        for f in sorted(by["confounded"], key=lambda f: -f.get("interest", 0))[:4]:
            if f.get("model_check_q") is None and f.get("raw_effect"):
                L.append(f"- **{f['question']}** Confounded. Without controls: "
                         f"{brief(f['raw_effect'])} (q {eq(f['raw_q_value'])}); compared like "
                         f"with like: {brief(f['effect'])} (q {eq(f['q_value'])}).")
            else:
                L.append(f"- **{f['question']}** Confounded: {short_summary(f)}. "
                         f"{f['verdict_reason']}")
    L.append("")
    L.append("## The patterns that are real")
    L.append("")
    for f in ranked(by["real"] + by["probably real"]):
        L += block(f)
    L.append("## The funniest nulls")
    L.append("")
    fun_other = [f for f in findings if f["fun"] and f["verdict"] != "fun null"]
    if not fun_other:
        status = "None of them show anything. "
    elif all(f["verdict"] == "confounded" for f in fun_other):
        status = (f"{len(fun_other)} more only look like something until songs are compared "
                  f"like with like, and are under Confounded. ")
    else:
        status = (f"{len(fun_other)} of them show something and are listed under their "
                  f"verdicts. ")
    L.append("Famous superstitions, tested exactly like everything else. " + status
             + "The 95% CI says how big an effect could still be hiding.")
    L.append("")
    for f in sorted(by["fun null"], key=lambda f: (-f.get("interest", 0), -f["p_value"])):
        L += block(f)
    if by["confounded"]:
        L.append("## Confounded: real-looking, but something else explains it")
        L.append("")
        for f in ranked(by["confounded"]):
            L += block(f)
    L.append("## Noise")
    L.append("")
    L.append("Reasonable questions with no detectable answer.")
    L.append("")
    for f in ranked(by["noise"]):
        L += block(f)

    L.append("## What predicts views")
    L.append("")
    L.append(f"A regression of log views on every feature at once, with a dummy for each "
             f"month so songs only compete with songs of the same age ({model['n']:,} songs "
             f"with a normal upload). The month alone explains "
             f"{pct(model['r2_month_only'])} of the variation in log views "
             f"({pct(model['cv_r2_month_only'])} out of sample); adding topic, mood, length, "
             f"instrument, genre, travel, weekday, news and beard brings it to "
             f"{pct(model['r2_full'])} ({pct(model['cv_r2_full'])} out of sample). Home era "
             f"alone explains {pct(model['r2_era_only'])} and calendar year alone "
             f"{pct(model['r2_year_only'])}: the era differences in views are mostly the age "
             f"of the video and YouTube's own history, so era isn't tested separately.")
    L.append("")
    L.append("| Block | Adds (share of within-month variance) | Wald p | q |")
    L.append("| --- | --- | --- | --- |")
    block_q = {f["id"]: f["q_value"] for f in findings}
    block_q.update({d["id"]: d["q_value"] for d in diagnostics})
    block_id = {"topic": "views_topic", "mood": "views_mood", "length": "views_length",
                "instrument": "views_instrument", "genre": "views_genre"}
    for b, info in sorted(model["blocks"].items(), key=lambda kv: -kv[1]
                          ["partial_r2_within_month"]):
        qv = block_q.get(block_id.get(b, f"model:{b}"))
        L.append(f"| {b} | {pct(info['partial_r2_within_month'], 2)} | {fmt_p(info['p'])} | "
                 f"{fmt_p(qv)} |")
    L.append("")
    tops = sorted(model["blocks"]["topic"]["terms"], key=lambda t: -t["multiplier"])
    L.append("Topics, as a views multiplier against same-month songs on rarer topics (none of "
             "these 30), with mood, length, instrument and the rest held fixed (95% CI):")
    L.append("")
    L.append("| Topic | Songs | Multiplier | 95% CI |")
    L.append("| --- | --- | --- | --- |")
    for t in tops:
        L.append(f"| {t['term'].split(':', 1)[1]} | {t['n']} | x{t['multiplier']:.2f} | "
                 f"x{t['ci_low']:.2f} to x{t['ci_high']:.2f} |")
    L.append("")

    L.append("## Every test")
    L.append("")
    L.append("| Verdict | Question | Effect | n | p | q |")
    L.append("| --- | --- | --- | --- | --- | --- |")
    for f in sorted(findings, key=lambda f: (VERDICT_ORDER.index(f["verdict"]), f["q_value"])):
        eff = f["effect"].split(";")[0]
        L.append(f"| {f['verdict']} | {f['question']} | {eff} | {f['n']:,} | "
                 f"{fmt_p(f['p_value'])} | {fmt_p(f['q_value'])} |")
    L.append("")

    L.append("## Method")
    L.append("")
    L.append(f"- **Shuffling.** Each controlled test shuffles the exposure {n_perm:,} times "
             "within strata (songs of the same year and home era, plus season for the sky, "
             "or the same month of the same year for weather, views and news). For exposures "
             "that come in long runs (Mercury retrograde, planet positions, trips, beard, "
             "home era) the exposure is instead rotated in time by a random offset (a "
             "circular shift), which keeps the runs and any day-to-day resemblance between "
             "songs. Seasons, daylight and sun signs are shuffled as whole months or whole "
             "sign periods within a year.")
    L.append("- **Effects.** Differences are Mantel-Haenszel-weighted averages of "
             "within-stratum differences; slopes are fitted after removing each stratum's "
             "mean; mood mixes use a chi-square against within-stratum expected counts, "
             "summarised as Cramer's V next to the V that chance alone produces. 95% CIs invert "
             "the shuffle test: the estimate minus the 97.5th and 2.5th percentiles of the "
             "shuffled statistics.")
    L.append("- **Moods.** The 11 moods with 100+ songs are kept and the rest pooled as "
             "Other. High-energy: " + ", ".join(sorted(WILD_MOODS)) + ". Unhappy: "
             + ", ".join(sorted(DARK_MOODS)) + ".")
    L.append("- **Views.** log10(views + 1), only for videos that are up, were uploaded "
             "within 30 days of the song and have been online 30+ days, compared within the "
             "month of upload.")
    L.append("- **Lengths** are clipped to 30 s - 8 min in tests so a few very long songs "
             "don't swing the means. Minor-key tests use only songs with a known mode.")
    L.append("- **Views model check.** The weekday, travel, news-song and beard views tests are "
             "run again as blocks of the views regression, which also holds topic, mood, "
             "length, instrument and genre fixed. A views pattern that fades there (q >= 0.05) "
             "is labelled confounded: it is mostly what the songs are about.")
    L.append(f"- **Multiple testing.** q-values are Benjamini-Hochberg over all {n_tests} "
             "p-values the script computes: the controlled tests, their uncontrolled "
             "versions, the trends and the views model's blocks.")
    L.append("- **Trends** use one value per year (Kendall's test), because 6,500 "
             "neighbouring songs are not independent. Home-era tests treat the era as a "
             "stretch of time and compare it with eras cut at random points.")
    L.append("- **Caveats.** Mood, beard, key and tempo are Jonathan's own tags and the way he "
             "tagged drifted. Sky values are a 17:00 New York snapshot wherever he was. "
             "Weather is a reanalysis grid cell, not the room. News coverage on Wikipedia's "
             "Portal changes by year. Tests that find nothing don't prove there's nothing; "
             "the CI says how big an effect could hide.")
    L.append("")
    path.write_text("\n".join(L) + "\n", encoding="utf-8")


# Hand-written context for some findings, shown under them in findings.md. These are
# explanations, not results: every number is computed.
NOTES = {
    "era_minor": "The era is a stretch of time, so this can't say the move caused it; it "
                 "says the change is bigger than random cuts of the timeline produce.",
    "era_mood": "Mood tags drifted over the years (Happy was common in 2009 and rare after "
                "2017), so some of this is tagging, not feeling.",
    "daylight_sad": "Daylight is the season, so even a clear pattern couldn't be told apart "
                    "from holidays, the school year or the cold.",
    "daylight_minor": "Daylight is the season, so even a clear pattern couldn't be told apart "
                      "from holidays, the school year or the cold.",
    "travel_views": "Trips include conferences and events whose songs have their own "
                    "audience, so this is not 'travel makes better songs'.",
    "mercury_views": "Mercury's retrograde periods recur every ~116 days, so a time shift of "
                     "one cycle partly recreates them; the circular-shift null is cautious.",
    "sun_sign_mood": "Sun signs are calendar dates, so the season is held fixed: each sign is "
                     "compared only with the other two signs of its season.",
    "news_politics_topic": "Wikipedia's politics section and his Politics songs both peak on "
                           "election days, so this is mostly elections.",
    "beard_views": "He may shave for special videos (gigs, shoots, commissions), so the beard "
                   "could be a marker of the occasion rather than a cause. The model check "
                   "holds topic and mood fixed, but not the occasion.",
    "beard_mood": "Beard and mood are both his own tags, usually entered together, so a "
                  "tagging habit could produce part of this.",
    "weekday_views": "Views are compared within the month, so this is about the day a song "
                     "came out, not the era. Weekend songs are also quieter (fewer news songs "
                     "and high-energy moods, more Poetic and Life), which the model check "
                     "holds fixed.",
    "travel_length": "Trips include gigs, conferences and collaborations, which may run long.",
    "news_song_views": "A news song names that day's headlines more than it would a year "
                       "earlier or later. Matching is plain string matching, so it misses "
                       "songs that allude to the news without naming it.",
    "views_length": "Longer songs may be the ones with more effort or production, so length "
                    "may stand in for that.",
    "views_mood": "Mood is his own tag; silly songs are often the topical, shareable ones.",
    "trend_dark": "Moods are his own tags and the vocabulary shifted (Angry and Anxious grew), "
                  "so part of this may be tagging. Only 18 yearly values.",
    "friday13_dark": "Only 32 Friday-the-13ths since 2009, so the CI is wide.",
    "eclipse_dark": "Eclipse days are when an eclipse was visible somewhere on Earth, not "
                    "necessarily where he was.",
    "weekday_mood": "Seven days by twelve moods spreads the pattern thin; the single biggest "
                    "cell is shown.",
    "moon_full_wild": "The 'lunacy' claim: full moons make people wilder. High-energy moods "
                      "are the test.",
    "mercury_chaos": "Mercury retrograde is said to scramble communication; confused, "
                     "anxious, angry and annoyed moods are the test.",
}

# Editorial order within each verdict in findings.md (higher comes first). Not a result.
INTEREST = {
    "news_song_views": 100, "views_topic": 95, "weekday_views": 90, "travel_length": 85,
    "beard_views": 80, "views_length": 78, "views_mood": 76, "trend_dark": 74,
    "beard_mood": 70, "travel_views": 68, "era_minor": 66, "era_mood": 64,
    "weekday_mood": 60, "weekend_wild": 92, "news_politics_topic": 58, "season_mood": 55,
    "travel_mood": 50,
    "weekend_length": 48, "views_genre": 40,
    "moon_full_wild": 100, "mercury_chaos": 95, "friday13_dark": 90, "mercury_views": 88,
    "moon_phase_mood": 85, "mercury_minor": 80, "supermoon_wild": 75, "sun_sign_mood": 72,
    "arc_wild": 70, "eclipse_dark": 65, "monday_tired": 62, "moon_full_minor": 60,
    "mercury_mood": 58, "moon_sign_mood": 55, "conj_mood": 50, "arc_tempo": 48,
    "conj_tempo": 45, "retro_count_dark": 44, "moon_full_tempo": 40, "moon_full_length": 38,
    "rain_sad": 100, "temp_tempo": 90, "sunshine_sad": 85, "news_items_dark": 75,
    "news_conflict_dark": 70, "trend_minor": 65, "trend_tempo": 60, "trend_length": 58,
    "daylight_sad": 56, "snow_mood": 54, "weather_label_mood": 52,
}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--quick", action="store_true", help="10x fewer shuffles")
    args = ap.parse_args()
    n_perm = 499 if args.quick else N_PERM
    n_perm_raw = 199 if args.quick else N_PERM_RAW
    t0 = time.time()
    df = load_songs()
    print(f"Loaded {len(df):,} songs (#{df['number'].min()}-#{df['number'].max()}).")

    agg = build_aggregates(df)
    print(f"Running {len(TESTS)} permutation tests ({n_perm} shuffles each, raw versions "
          f"{n_perm_raw})...")
    findings, diagnostics = run_all_tests(df, n_perm, n_perm_raw)
    findings += trend_tests(df)
    model_tests, model, model_checks = views_model(df)
    findings += model_tests
    diagnostics += model_checks

    # Benjamini-Hochberg across every p-value computed: findings, raw diagnostics, model.
    all_p = [f["p"] for f in findings] + [d["p"] for d in diagnostics]
    q = bh_qvalues(all_p)
    for f, qv in zip(findings, q[:len(findings)]):
        f["q_value"] = float(qv)
    for d, qv in zip(diagnostics, q[len(findings):]):
        d["q_value"] = float(qv)
    raw = {d["of"]: d for d in diagnostics if d["id"].endswith(":raw")}
    checks = {d["of"]: d for d in diagnostics if d["id"].startswith("model:")}
    for f in findings:
        if f["id"] in raw:
            f["raw_q_value"] = raw[f["id"]]["q_value"]
        if f["id"] in checks:
            c = checks[f["id"]]
            f["model_check_q"] = c["q_value"]
            f["model_check"] = (f"In the full views model, which also holds topic, mood, "
                                f"length, instrument, genre and the rest fixed: {c['effect']} "
                                f"(block p {eq(c['p'])}, q {eq(c['q_value'])}).")
        f["p_value"] = f.pop("p")
        f["note"] = NOTES.get(f["id"])
        f["interest"] = INTEREST.get(f["id"], 0)
        f["verdict"], f["verdict_reason"] = verdict(f)
    n_tests = len(all_p)

    # Model numbers for the views section, and chart data for it.
    agg["views_model"] = {
        "n": model["n"], "r2_month_only": model["r2_month_only"], "r2_full": model["r2_full"],
        "cv_r2_month_only": model["cv_r2_month_only"], "cv_r2_full": model["cv_r2_full"],
        "r2_era_only": model["r2_era_only"], "r2_year_only": model["r2_year_only"],
        "blocks": [{"block": b, "partial_r2_within_month": i["partial_r2_within_month"],
                    "wald_p": i["p"], "df": i["df"]} for b, i in model["blocks"].items()],
        "terms": [dict(block=b, **t) for b, i in model["blocks"].items() for t in i["terms"]],
        "note": "multiplier = views relative to the baseline (Pensive / Acoustic Guitar / Folk "
                "/ rarer topics / Monday / at home / Beard) for a song from the same month, "
                "everything else held fixed"}
    agg["findings_index"] = [{"id": f["id"], "verdict": f["verdict"], "q": f["q_value"],
                              "chart": f["chart"]} for f in findings]
    agg = clean_json(agg)
    AGGREGATES_JSON.write_text(json.dumps(agg, separators=(",", ":"), ensure_ascii=False),
                               encoding="utf-8")

    meta = {"songs": int(len(df)), "last": int(df["number"].max()),
            "last_date": str(df["date"].max().date())}
    out = {"made_by": "analysis/analyze.py", "source": "dataset/songaday.csv",
           "songs": meta["songs"], "through": {"number": meta["last"], "date": meta["last_date"]},
           "n_pvalues_in_fdr": n_tests, "shuffles": n_perm, "shuffles_raw": n_perm_raw,
           "verdict_rules": {"real": "q < 0.01", "probably real": "q < 0.05",
                             "confounded": "raw (uncontrolled) q < 0.05 but controlled q >= "
                                           "0.05; or a views effect whose block in the full "
                                           "views model has q >= 0.05; or a controlled effect "
                                           "that can't be separated from another cause",
                             "fun null": "a superstition test with q >= 0.05",
                             "noise": "q >= 0.05"},
           "findings": findings, "raw_diagnostics": diagnostics,
           "views_model": {k: v for k, v in model.items() if k != "blocks"}}
    FINDINGS_JSON.write_text(json.dumps(clean_json(out), indent=1, ensure_ascii=False) + "\n",
                             encoding="utf-8")
    write_markdown(findings, diagnostics, dict(model, **meta), n_tests, n_perm, FINDINGS_MD)

    counts = pd.Series([f["verdict"] for f in findings]).value_counts().to_dict()
    print(f"\n{len(findings)} findings, {n_tests} p-values in the FDR family: {counts}")
    for f in sorted(findings, key=lambda f: f["q_value"]):
        print(f"  {f['verdict']:<14} q={fmt_p(f['q_value']):>8}  {f['id']:<22} "
              f"{f['effect'][:90]}")
    print(f"\nWrote {AGGREGATES_JSON.relative_to(ROOT)} "
          f"({AGGREGATES_JSON.stat().st_size / 1e6:.2f} MB), "
          f"{FINDINGS_JSON.relative_to(ROOT)}, {FINDINGS_MD.relative_to(ROOT)} "
          f"in {time.time() - t0:.0f} s.")


if __name__ == "__main__":
    sys.exit(main())
