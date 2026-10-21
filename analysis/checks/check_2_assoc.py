"""Check 2 / mood mixes: re-test the 'real' and 'probably real' mood-mix associations
(weekday_mood, beard_mood, travel_mood, season_mood, era_mood) with different methods.

Two kinds of re-test:
  Wald   one linear-probability model per mood (11 moods, 'Other' left out) on dummies
         for the exposure, inside fixed effects, stacked and tested jointly with
         standard errors clustered by calendar month. The F version corrects the Wald
         statistic for the number of clusters.
  perm   analyze.py's own chi-square statistic, but with a null that keeps more of the time
         structure:
           weekday_mood  weekday labels shuffled only inside each calendar week
           season_mood   each year's months rotated by a random 0-11 months (seasons stay
                         blocks of three adjacent months; analyze.py shuffled single months,
                         which breaks up slow within-year drift and can overstate seasons)
           era_mood      the timeline cut at three random points into four contiguous eras
                         of at least a year each (analyze.py's circular shift wraps one era
                         round from 2026 back to 2009, mixing the two ends of a drifting
                         series, which makes real contiguous eras look more special)
           beard/travel  analyze.py's circular shift, but with year-month strata instead
                         of year + home era
Run: .venv/bin/python analysis/checks/check_2_assoc.py
"""

import json
import math
import zlib

import numpy as np
import pandas as pd

from check_2_common import A, CHECKS, codes_of, load, multi_outcome_wald

N_PERM = 4999
MOODS = A.MOOD_ORDER   # 11 top moods + Other


def assoc_stat(sub, x_col, x_levels, strata_cols):
    """analyze.py's chi-square statistic for sub, as a function of exposure codes."""
    y = pd.Categorical(sub["mood12"], categories=MOODS).codes.astype(np.int64)
    strata = codes_of(sub, strata_cols) if strata_cols else np.zeros(len(sub), int)
    f = A.make_statistic("assoc", y, strata, n_x=len(x_levels), n_y=len(MOODS))
    x = pd.Categorical(sub[x_col], categories=x_levels).codes.astype(np.int64)
    return f, x


def perm_p(f, x, draws_fn, n_perm, rng):
    obs = float(f(x[None, :])[0])
    null = []
    for start in range(0, n_perm, 500):
        size = min(500, n_perm - start)
        null.append(f(draws_fn(size, rng)))
    null = np.concatenate(null)
    p = (1 + np.sum(null >= obs - 1e-12)) / (n_perm + 1)
    return obs, null, float(p)


def cramers_v(chi2, n, a, c):
    return math.sqrt(max(chi2, 0) / (n * (min(a, c) - 1)))


def wald_rows(df, x_col, x_levels, fes):
    out = []
    for fe, cl in fes:
        r = multi_outcome_wald(df, x_col, x_levels, "mood12", MOODS, fe, [cl])
        label = ("+".join("x".join(c) for c in fe) or "none") + f" FE, cl. {cl}"
        print(f"   Wald {label:<40} W={r['W']:.1f} on {r['q']} df, G={r['G']}: "
              f"p(chi2)={r['p_chi2']:.3g}, p(F)={r['p_F']:.3g}", flush=True)
        out.append(dict(method="Wald " + label, W=r["W"], df=r["q"], G=r["G"],
                        p_chi2=r["p_chi2"], p_F=r["p_F"]))
    return out


def main():
    df = load()
    df = df[df["mood12"].isin(MOODS)].reset_index(drop=True)
    res = {}

    # ---- weekday_mood -------------------------------------------------------------------
    print("\nweekday_mood", flush=True)
    rows = wald_rows(df, "weekday", A.WEEKDAYS, [([["year", "home_era"]], "ym"),
                                                  ([["week"]], "ym")])
    f, x = assoc_stat(df, "weekday", A.WEEKDAYS, ["year", "home_era"])
    groups = [g.to_numpy() for _, g in df.groupby("week").groups.items()]
    groups = [np.asarray(df.index[df["week"] == w]) for w in df["week"].unique()]

    def within_week(size, rng):
        out = np.tile(x, (size, 1))
        for idx in groups:
            out[:, idx] = rng.permuted(np.tile(x[idx], (size, 1)), axis=1)
        return out
    rng = np.random.default_rng(zlib.crc32(b"weekday_mood_week"))
    obs, null, p = perm_p(f, x, within_week, N_PERM, rng)
    v = cramers_v(obs, len(x), 7, 12)
    v0 = cramers_v(null.mean(), len(x), 7, 12)
    print(f"   perm within calendar weeks: V={v:.3f} vs chance {v0:.3f}, p={p:.4f}")
    rows.append(dict(method="perm: weekday shuffled within calendar week", V=v, V_chance=v0,
                     p=p))
    res["weekday_mood"] = rows

    # ---- beard_mood ---------------------------------------------------------------------
    print("\nbeard_mood", flush=True)
    bd = df[df["beard3"].isin(["Beard", "Shadow", "Clean"])].reset_index(drop=True)
    levels = ["Beard", "Shadow", "Clean"]
    rows = wald_rows(bd, "beard3", levels, [([["year", "home_era"]], "ym"),
                                            ([["ym"]], "ym"), ([["week"]], "ym")])
    for strata_cols, ms in ((["ym"], 90),):
        f, x = assoc_stat(bd, "beard3", levels, strata_cols)
        rng = np.random.default_rng(zlib.crc32(b"beard_mood_ym"))
        obs, null, p = perm_p(f, x, lambda s, r: A.circular_shift(x, s, r, ms), N_PERM, rng)
        v, v0 = cramers_v(obs, len(x), 3, 12), cramers_v(null.mean(), len(x), 3, 12)
        print(f"   circular shift, year-month strata: V={v:.3f} vs chance {v0:.3f}, p={p:.4f}")
        rows.append(dict(method="perm: circular shift, year-month strata", V=v, V_chance=v0,
                         p=p))
    res["beard_mood"] = rows

    # ---- travel_mood --------------------------------------------------------------------
    print("\ntravel_mood", flush=True)
    rows = wald_rows(df, "traveling", [0.0, 1.0], [([["year", "home_era"]], "ym"),
                                                   ([["ym"]], "ym"), ([["year", "home_era"]],
                                                                      "year")])
    f, x = assoc_stat(df, "traveling", [0.0, 1.0], ["ym"])
    rng = np.random.default_rng(zlib.crc32(b"travel_mood_ym"))
    obs, null, p = perm_p(f, x, lambda s, r: A.circular_shift(x, s, r, 30), N_PERM, rng)
    v, v0 = cramers_v(obs, len(x), 2, 12), cramers_v(null.mean(), len(x), 2, 12)
    print(f"   circular shift, year-month strata: V={v:.3f} vs chance {v0:.3f}, p={p:.4f}")
    rows.append(dict(method="perm: circular shift, year-month strata", V=v, V_chance=v0, p=p))
    res["travel_mood"] = rows

    # ---- season_mood --------------------------------------------------------------------
    print("\nseason_mood", flush=True)
    month_season = {m: s for m, s in zip(range(1, 13), ["winter", "winter", "spring",
                    "spring", "spring", "summer", "summer", "summer", "fall", "fall", "fall",
                    "winter"])}
    assert all(df["season"] == df["month"].map(month_season))
    f, x = assoc_stat(df, "season", A.SEASONS, ["year"])
    season_code = np.array([A.SEASONS.index(month_season[m]) for m in range(1, 13)])
    months0 = df["month"].to_numpy() - 1
    ycode = codes_of(df, ["year"])
    ny = ycode.max() + 1

    def rotate(size, rng):
        k = rng.integers(0, 12, size=(size, ny))             # one rotation per year
        return season_code[(months0[None, :] + k[:, ycode]) % 12]
    rng = np.random.default_rng(zlib.crc32(b"season_mood_rotate"))
    obs, null, p = perm_p(f, x, rotate, N_PERM, rng)
    v, v0 = cramers_v(obs, len(x), 4, 12), cramers_v(null.mean(), len(x), 4, 12)
    print(f"   per-year month rotation: V={v:.3f} vs chance {v0:.3f}, p={p:.4f}")
    rows = [dict(method="perm: each year's months rotated 0-11", V=v, V_chance=v0, p=p)]

    # The same rotation, but excluding 2026 (a partial year: January-October only).
    sub = df[df["year"] < 2026].reset_index(drop=True)
    f2, x2 = assoc_stat(sub, "season", A.SEASONS, ["year"])
    m2 = sub["month"].to_numpy() - 1
    y2 = codes_of(sub, ["year"])

    def rotate2(size, rng):
        k = rng.integers(0, 12, size=(size, y2.max() + 1))
        return season_code[(m2[None, :] + k[:, y2]) % 12]
    rng = np.random.default_rng(zlib.crc32(b"season_mood_rotate_full_years"))
    obs2, null2, p2 = perm_p(f2, x2, rotate2, N_PERM, rng)
    v2, v02 = cramers_v(obs2, len(x2), 4, 12), cramers_v(null2.mean(), len(x2), 4, 12)
    print(f"   per-year rotation, 2009-2025 only: V={v2:.3f} vs chance {v02:.3f}, p={p2:.4f}")
    rows.append(dict(method="perm: rotation, full years 2009-2025", V=v2, V_chance=v02, p=p2))

    # Split-half replication: is the season x mood pattern (observed minus expected within
    # year) in odd years correlated with the one in even years?
    def resid_table(d):
        yy = pd.Categorical(d["mood12"], categories=MOODS).codes
        xx = pd.Categorical(d["season"], categories=A.SEASONS).codes
        st = codes_of(d, ["year"])
        S = st.max() + 1
        cc = np.bincount(st * 12 + yy, minlength=S * 12).reshape(S, 12)
        rc = np.bincount(st * 4 + xx, minlength=S * 4).reshape(S, 4)
        E = rc.T @ (cc / cc.sum(1)[:, None])
        O = np.bincount(xx * 12 + yy, minlength=48).reshape(4, 12)
        return ((O - E) / np.sqrt(E)).ravel()
    odd = resid_table(df[df["year"] % 2 == 1])
    even = resid_table(df[df["year"] % 2 == 0])
    r_split = float(np.corrcoef(odd, even)[0, 1])
    print(f"   split-half (odd vs even years) correlation of the 48 cell residuals: "
          f"r={r_split:+.3f}")
    rows.append(dict(method="split-half odd vs even years, cell-residual correlation",
                     r=r_split))
    res["season_mood"] = rows

    # ---- era_mood -----------------------------------------------------------------------
    print("\nera_mood", flush=True)
    y = pd.Categorical(df["mood12"], categories=MOODS).codes.astype(np.int64)
    x = pd.Categorical(df["home_era"], categories=A.ERAS).codes.astype(np.int64)
    f = A.make_statistic("assoc", y, np.zeros(len(y), int), n_x=4, n_y=12)
    n = len(y)
    min_len = 365

    def random_cuts(size, rng):
        out = np.empty((size, n), dtype=np.int64)
        filled = 0
        while filled < size:
            c = np.sort(rng.integers(1, n, size=3))
            seg = np.diff(np.concatenate([[0], c, [n]]))
            if seg.min() < min_len:
                continue
            out[filled] = np.repeat(np.arange(4), seg)
            filled += 1
        return out
    rng = np.random.default_rng(zlib.crc32(b"era_mood_cuts"))
    obs, null, p = perm_p(f, x, random_cuts, N_PERM, rng)
    v, v0 = cramers_v(obs, n, 4, 12), cramers_v(null.mean(), n, 4, 12)
    print(f"   random contiguous cuts (each era >= {min_len} songs): V={v:.3f} vs chance "
          f"{v0:.3f}, p={p:.4f}, share of null >= observed {np.mean(null >= obs):.3f}")
    rows = [dict(method="perm: 3 random contiguous cut points, eras >= 365 songs", V=v,
                 V_chance=v0, p=p)]
    # analyze.py's circular shift, reproduced, to show the difference the wrap makes.
    rng = np.random.default_rng(zlib.crc32(b"era_mood_shift"))
    obs_s, null_s, p_s = perm_p(f, x, lambda s, r: A.circular_shift(x, s, r, 365), N_PERM,
                                rng)
    print(f"   analyze.py's circular shift reproduced: chance V="
          f"{cramers_v(null_s.mean(), n, 4, 12):.3f}, p={p_s:.4f}")
    rows.append(dict(method="perm: circular shift >= 365 (as analyze.py)",
                     V=cramers_v(obs_s, n, 4, 12),
                     V_chance=cramers_v(null_s.mean(), n, 4, 12), p=p_s))
    # Contiguous cuts that keep the real era lengths but slide all three boundaries by the
    # same random offset (no wrap): the closest analogue of "move the moves in time".
    lens = np.bincount(x, minlength=4)
    bounds = np.cumsum(lens)[:-1]
    rows_slide = []
    for off in range(-int(lens[0]) + min_len, int(lens[3]) - min_len + 1, 7):
        c = bounds + off
        seg = np.diff(np.concatenate([[0], c, [n]]))
        rows_slide.append(f(np.repeat(np.arange(4), seg)[None, :])[0])
    rows_slide = np.array(rows_slide)
    p_slide = float((1 + np.sum(rows_slide >= obs - 1e-12)) / (len(rows_slide) + 1))
    print(f"   real era lengths, boundaries slid together ({len(rows_slide)} offsets): "
          f"p={p_slide:.4f}")
    rows.append(dict(method="slide all era boundaries by a common offset", p=p_slide,
                     n_offsets=len(rows_slide)))
    # Within-era drift: the same statistic for 4 equal-length chunks inside the two longest
    # eras, to show how big arbitrary contiguous chunks of one home get.
    for era in ("hartford", "jersey_city"):
        e = df[df["home_era"] == era].reset_index(drop=True)
        ye = pd.Categorical(e["mood12"], categories=MOODS).codes.astype(np.int64)
        chunks = np.repeat(np.arange(4), np.diff(np.linspace(0, len(e), 5).astype(int)))
        fe_ = A.make_statistic("assoc", ye, np.zeros(len(e), int), n_x=4, n_y=12)
        ve = cramers_v(fe_(chunks[None, :])[0], len(e), 4, 12)
        print(f"   inside {era}: 4 equal contiguous chunks give V={ve:.3f}")
        rows.append(dict(method=f"inside {era}: V of 4 equal contiguous chunks", V=ve))
    res["era_mood"] = rows

    (CHECKS / "check_2_assoc.json").write_text(json.dumps(res, indent=1, default=float))


if __name__ == "__main__":
    main()
