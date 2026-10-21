"""Check 2 / power of the fun nulls: were the superstition tests strong enough to see an
effect if there were one, and how big an effect could they have missed?

Two of the headline nulls are simulated in full:
  moon_full_wild   share of high-energy moods on full-moon days (220 songs), stratified
                   permutation within year x season x home era
  mercury_chaos    share of Anxious/Confused/Angry/Annoyed moods during Mercury retrograde
                   (1,243 songs), circular-shift null
Each simulated dataset keeps the real songs but replaces the real exposure with a placebo
drawn from the test's own null scheme (full-moon days shuffled within the strata; the
Mercury retrograde series rotated by a random offset), so every dataset gets fresh chance
noise of the right size and structure. A true effect of d percentage points is then planted
on the placebo-exposed songs (songs without the mood are switched to it at random until the
exposed share rises by d on average), and analyze.py's own test (its run_permutation, 499
shuffles) is rerun. Power is the share of 200 datasets with p < 0.05, and with p < 0.005
(about what one more finding would need to reach q < 0.05 among 124 tests with ~17
discoveries). d = 0 checks the test's size (should be about 5%).

Every 'diff' fun null also gets the normal-approximation minimum detectable effect from its
published null SD: MDE80 = (1.96 + 0.84) x SD at alpha 0.05, and (2.81 + 0.84) x SD at
alpha 0.005.
Run: .venv/bin/python analysis/checks/check_2_power.py
"""

import json
import zlib

import numpy as np

from check_2_common import A, CHECKS, findings, load

N_SIM = 200
N_PERM = 499


def placebo(df, spec, rng):
    """One draw of the exposure from the test's own null scheme."""
    x = df[spec["x"]].to_numpy(float)
    if spec["null"] == "perm":
        strata = A.stratum_codes(df, spec["strata"])
        out = x.copy()
        for idx in A.group_indices(strata):
            out[idx] = rng.permutation(x[idx])
        return out
    n = len(x)
    ms = spec.get("min_shift", 30)
    return np.roll(x, -int(rng.integers(ms, n - ms + 1)))


def plant(df, spec, d, rng):
    """Copy of df with a placebo exposure, and the placebo-exposed songs' binary outcome
    share raised by about d."""
    out = df.copy()
    out[spec["x"]] = placebo(df, spec, rng)
    x, y = spec["x"], spec["y"]
    exposed = (out[x] == 1) & out[y].notna()
    if d > 0:
        base = out.loc[exposed, y].mean()
        zeros = exposed & (out[y] == 0)
        flip = zeros & (rng.random(len(out)) < d / (1 - base))
        out.loc[flip, y] = 1.0
    return out


def simulate(df, spec, deltas, seed):
    rng = np.random.default_rng(seed)
    rows = []
    for d in deltas:
        ps, ests = [], []
        for _ in range(N_SIM):
            sim = plant(df, spec, d, rng)
            res = A.run_permutation(spec, sim, spec["strata"], N_PERM)
            ps.append(res["p"])
            ests.append(res["observed"])
        ps = np.array(ps)
        ests = np.array(ests)
        rows.append(dict(delta_points=100 * d, power_05=float((ps < 0.05).mean()),
                         power_005=float((ps < 0.005).mean()),
                         mean_estimate_points=100 * float(ests.mean()),
                         sd_estimate_points=100 * float(ests.std()), sims=len(ps)))
        print(f"   planted {100 * d:+5.1f} pts: estimate {100 * ests.mean():+5.1f} "
              f"(SD {100 * ests.std():.1f}), power(p<0.05)={rows[-1]['power_05']:.2f}, "
              f"power(p<0.005)={rows[-1]['power_005']:.2f}", flush=True)
    return rows


def main():
    df = load()
    F = findings()
    spec = {t["id"]: t for t in A.TESTS}
    out = {"analytic": [], "simulated": {}}

    print("Minimum detectable effects (80% power) from each fun null's published null SD:")
    for fid, f in F.items():
        if not f["fun"] or f["kind"] not in ("diff", "slope"):
            continue
        sd = f["stats"]["null_sd"]
        step = f["stats"].get("per_step", 1.0)
        scale = abs(step) * (100 if f["y_kind"] == "binary" else 1)
        mde05, mde005 = 2.80 * sd * scale, 3.65 * sd * scale
        if f["y_kind"] == "log_views":
            mde05, mde005 = 100 * (10 ** (2.80 * sd) - 1), 100 * (10 ** (3.65 * sd) - 1)
        unit = {"binary": "pts", "log_views": "% views"}.get(f["y_kind"], f["y_unit"])
        base = f["stats"].get("mean_other")
        print(f"   {fid:<18} {f['verdict']:<10} MDE80 {mde05:6.2f} {unit} (alpha .05), "
              f"{mde005:6.2f} (alpha .005); baseline {base}")
        out["analytic"].append(dict(id=fid, verdict=f["verdict"], null_sd=sd,
                                    mde80_alpha05=mde05, mde80_alpha005=mde005, unit=unit,
                                    baseline=base))

    for fid, deltas in (("moon_full_wild", [0, 0.04, 0.07, 0.10, 0.13]),
                        ("mercury_chaos", [0, 0.01, 0.02, 0.03, 0.04])):
        print(f"\n{fid}: power by simulation ({N_SIM} datasets x {N_PERM} shuffles)")
        out["simulated"][fid] = simulate(df, spec[fid], deltas, seed=zlib.crc32(fid.encode()))
    (CHECKS / "check_2_power.json").write_text(json.dumps(out, indent=1, default=float))


if __name__ == "__main__":
    main()
