"""Check 2 / loose ends:
  1. What the BH q-values become if the p-values of season_mood, era_mood and
     news_politics_topic are replaced by the re-tests in check_2_assoc.py and
     check_2_diffs.py (everything else as published).
  2. weekday_mood: is there a weekday pattern beyond weekend vs weekday? Mood mix across
     Monday-Friday only, and Saturday vs Sunday only (cluster-robust Wald, week FE).
Run after check_2_assoc.py and check_2_diffs.py:
  .venv/bin/python analysis/checks/check_2_misc.py
"""

import json

import numpy as np

from check_2_common import A, ANALYSIS, CHECKS, load, multi_outcome_wald
from check_2_fdr import bh


def main():
    F = json.loads((ANALYSIS / "findings.json").read_text())
    ids = [f["id"] for f in F["findings"]]
    p = np.array([f["p_value"] for f in F["findings"]] + [d["p"] for d in F["raw_diagnostics"]])
    assoc = json.loads((CHECKS / "check_2_assoc.json").read_text())
    diffs = {r["id"]: r for r in json.loads((CHECKS / "check_2_diffs.json").read_text())}
    swaps = {
        "season_mood": assoc["season_mood"][0]["p"],      # per-year month rotation
        "era_mood": assoc["era_mood"][0]["p"],            # random contiguous cuts
        # month-clustered regression with year-month FE, the published design
        "news_politics_topic": [r for r in diffs["news_politics_topic"]["rows"]
                                if r["method"].startswith("B")][0]["p"],
    }
    out = {}
    for label, sw in (("all three swapped", swaps),
                      ("only news_politics_topic swapped",
                       {"news_politics_topic": swaps["news_politics_topic"]})):
        p2 = p.copy()
        for k, v in sw.items():
            p2[ids.index(k)] = v
        q2 = bh(p2)
        print(f"\nBH q with {label}:")
        for k in swaps:
            i = ids.index(k)
            print(f"   {k:<22} p {p[i]:.4f} -> {p2[i]:.4f}   q {F['findings'][i]['q_value']:.4f}"
                  f" -> {q2[i]:.4f}")
        out[label] = {k: dict(p=float(p2[ids.index(k)]), q=float(q2[ids.index(k)]))
                      for k in swaps}

    df = load()
    df = df[df["mood12"].isin(A.MOOD_ORDER)].reset_index(drop=True)
    wd = df[df["weekday"].isin(A.WEEKDAYS[:5])]
    r = multi_outcome_wald(wd, "weekday", A.WEEKDAYS[:5], "mood12", A.MOOD_ORDER, [["week"]],
                           ["ym"])
    print(f"\nMonday-Friday only, week FE, cl. month: W={r['W']:.1f} on {r['q']} df, "
          f"p(F)={r['p_F']:.3g}")
    we = df[df["weekday"].isin(["Saturday", "Sunday"])]
    r2 = multi_outcome_wald(we, "weekday", ["Saturday", "Sunday"], "mood12", A.MOOD_ORDER,
                            [["week"]], ["ym"])
    print(f"Saturday vs Sunday only, week FE, cl. month: W={r2['W']:.1f} on {r2['q']} df, "
          f"p(F)={r2['p_F']:.3g}")
    df["weekend"] = df["weekday"].isin(["Saturday", "Sunday"]).astype(float)
    r3 = multi_outcome_wald(df.assign(we=df["weekend"]), "we", [0.0, 1.0], "mood12",
                            A.MOOD_ORDER, [["week"]], ["ym"])
    print(f"weekend vs weekday, week FE, cl. month: W={r3['W']:.1f} on {r3['q']} df, "
          f"p(F)={r3['p_F']:.3g}")
    out["weekday_beyond_weekend"] = dict(mon_fri_pF=r["p_F"], sat_vs_sun_pF=r2["p_F"],
                                         weekend_vs_weekday_pF=r3["p_F"])
    (CHECKS / "check_2_misc.json").write_text(json.dumps(out, indent=1, default=float))


if __name__ == "__main__":
    main()
