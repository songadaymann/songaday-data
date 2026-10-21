"""Check 2 / multiple comparisons: recompute the q-values in findings.json and see whether the
'real' and 'probably real' verdicts depend on how the test family was drawn.

analyze.py runs Benjamini-Hochberg (BH) over 124 p-values: the 67 findings plus 53 raw
(uncontrolled) versions and 4 views-model checks. The raw versions are near-copies of the
controlled tests, so they pad the family. Here BH is recomputed four ways:
  1. as published (124 p-values), to confirm the code;
  2. the 67 findings only (the hypotheses the report actually makes claims about);
  3. Benjamini-Yekutieli over the 124, which is valid under any dependence between tests;
  4. Holm (family-wise error) over the 67 findings.
Run: .venv/bin/python analysis/checks/check_2_fdr.py
"""

import json

import numpy as np

from check_2_common import ANALYSIS


def bh(p):
    p = np.asarray(p, float)
    n = len(p)
    o = np.argsort(p)
    r = p[o] * n / np.arange(1, n + 1)
    q = np.minimum.accumulate(r[::-1])[::-1]
    out = np.empty(n)
    out[o] = np.minimum(q, 1)
    return out


def by(p):
    n = len(p)
    return np.minimum(bh(p) * np.sum(1 / np.arange(1, n + 1)), 1)


def holm(p):
    p = np.asarray(p, float)
    n = len(p)
    o = np.argsort(p)
    adj = np.maximum.accumulate(p[o] * (n - np.arange(n)))
    out = np.empty(n)
    out[o] = np.minimum(adj, 1)
    return out


def main():
    F = json.loads((ANALYSIS / "findings.json").read_text())
    fs, diags = F["findings"], F["raw_diagnostics"]
    p_find = np.array([f["p_value"] for f in fs])
    p_all = np.concatenate([p_find, [d["p"] for d in diags]])
    print(f"{len(fs)} findings + {len(diags)} diagnostics = {len(p_all)} p-values "
          f"(findings.json says {F['n_pvalues_in_fdr']})")

    q_pub = bh(p_all)[:len(fs)]
    q_67 = bh(p_find)
    q_by = by(p_all)[:len(fs)]
    h_67 = holm(p_find)
    max_err = max(abs(q_pub[i] - f["q_value"]) for i, f in enumerate(fs))
    print(f"published BH reproduced: max |q - q_published| = {max_err:.2e}")
    print(f"BH discoveries (q<0.05): 124-family {int((q_pub < 0.05).sum())}, "
          f"67-family {int((q_67 < 0.05).sum())}, BY {int((q_by < 0.05).sum())}, "
          f"Holm {int((h_67 < 0.05).sum())}")
    out = []
    print(f"\n{'id':<22}{'verdict':<15}{'p':>9}{'q pub':>9}{'q 67':>9}{'q BY':>9}"
          f"{'Holm':>9}")
    for i, f in enumerate(fs):
        if f["verdict"] not in ("real", "probably real") and q_67[i] >= 0.05:
            continue
        row = dict(id=f["id"], verdict=f["verdict"], p=f["p_value"], q_published=q_pub[i],
                   q_findings_only=q_67[i], q_BY=q_by[i], holm=h_67[i])
        out.append(row)
        print(f"{f['id']:<22}{f['verdict']:<15}{f['p_value']:>9.2g}{q_pub[i]:>9.3g}"
              f"{q_67[i]:>9.3g}{q_by[i]:>9.3g}{h_67[i]:>9.3g}")
    (ANALYSIS / "checks" / "check_2_fdr.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
