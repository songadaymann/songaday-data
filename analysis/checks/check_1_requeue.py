"""Skeptic check: what q-value would a rerun p-value get in the findings' own FDR family?

Takes every p-value in findings.json (the 67 findings plus the 57 raw and model
diagnostics, 124 in all), swaps in one replacement p for one finding, and recomputes the
Benjamini-Hochberg q for that finding. Replacement p-values come from the other check_1
scripts (printed there).
"""

import json

import numpy as np

from check_1_common import ROOT, analyze

F = json.loads((ROOT / "analysis" / "findings.json").read_text())
ids = [f["id"] for f in F["findings"]]
ps = [f["p_value"] for f in F["findings"]] + [d["p"] for d in F["raw_diagnostics"]]
print(f"{len(ps)} p-values in the family (findings say {F['n_pvalues_in_fdr']})")
q0 = analyze.bh_qvalues(ps)
REPLACE = {
    "season_mood": [("rotation null (adjacent-month drift kept)", 0.0797),
                    ("home songs only", 0.0424)],
    "news_politics_topic": [("US election and inauguration windows dropped", 0.0185),
                            ("election windows and inferred-section period dropped", 0.0175)],
    "trend_dark": [("Politics/Trump songs dropped", 0.0813),
                   ("only the 2009-2021 sheet years", 0.0216)],
    "era_mood": [("random non-wrapping partitions null", 0.6863)],
    "travel_mood": [("strata + season", 0.0010)],
}
for fid, reps in REPLACE.items():
    i = ids.index(fid)
    print(f"{fid}: published p={ps[i]:.4f} q={q0[i]:.4f}")
    for lab, p in reps:
        pp = list(ps)
        pp[i] = p
        q = analyze.bh_qvalues(pp)[i]
        print(f"   {lab:<55} p={p:.4f} -> q={q:.4f}")
