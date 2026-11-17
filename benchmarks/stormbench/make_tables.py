"""Print the Markdown tables of docs/benchmarks/stormbench.md from results/summary.json.

cd packages/stormbench && uv run python ../../benchmarks/stormbench/make_tables.py
"""

import json
from pathlib import Path

RES = Path(__file__).resolve().parent / "results" / "summary.json"


def f(x, nd=4):
    if x is None:
        return "n/a"
    if isinstance(x, float):
        return f"{x:.{nd}g}"
    return str(x)


def main() -> None:
    s = json.loads(RES.read_text(encoding="utf-8"))
    cases = s["cases"]
    print("| case | recall@k (DC) | Kendall tau (DC) | Spearman (DC) |")
    print("|---|---|---|---|")
    for c in cases:
        d = c["screening_vs_dc"]
        print(
            f"| {c['case']} | {f(d['recall_at_k'])} | {f(d['kendall_tau'])} | {f(d['spearman'])} |"
        )
    print()
    print(
        "| case | tie groups / tied pairs: screening | DC exact | AC exact | "
        "widest tie group (pp) | smallest margin to tolerance (pp) |"
    )
    print("|---|---|---|---|---|---|")
    for c in cases:
        sd, sa = c["screening_vs_dc"]["ties"], c["screening_vs_ac"]["ties"]
        sides = (sd["screening"], sd["reference"], sa["reference"])
        span = max(t["max_group_span_pct"] for t in sides)
        margin = min(t["tolerance_margin_pct"] for t in sides)
        print(
            f"| {c['case']} | "
            + " | ".join(f"{t['tie_groups']} / {t['tied_pairs']}" for t in sides)
            + f" | {f(span)} | {f(margin)} |"
        )
    print()
    print("| case | buses | branches | RATE_A=0 | islanding | screened | operating point |")
    print("|---|---|---|---|---|---|---|")
    for c in cases:
        n = c["counts"]
        print(
            f"| {c['case']} | {n['buses']} | {n['branches']} | {n['rate_a_zero']} | "
            f"{n['islanding']} | {n['screened']} | {c['operating_point']['method']} |"
        )
    print()
    print(
        "| case | max PTDF diff vs pandapower | max LODF diff vs pandapower | "
        "max flow error vs DC re-solve (MW) | mean flow error (MW) |"
    )
    print("|---|---|---|---|---|")
    for c in cases:
        v = c["validation"]
        print(
            f"| {c['case']} | {f(v['ptdf_max_abs_diff_vs_pandapower'])} | "
            f"{f(v['lodf_max_abs_diff_vs_pandapower'])} | {f(c['flow_error_mw']['max'])} | "
            f"{f(c['flow_error_mw']['mean'])} |"
        )
    print()
    print(
        "| case | overloading: screening / DC exact / AC exact | vs DC: precision | recall | "
        "vs AC: precision | recall | recall@k (AC, k) | Kendall tau (AC) | Spearman (AC) |"
    )
    print("|---|---|---|---|---|---|---|---|---|")
    for c in cases:
        o, d, a = c["overloading_contingencies"], c["screening_vs_dc"], c["screening_vs_ac"]
        print(
            f"| {c['case']} | {o['screening']} / {o['dc_exact']} / {o['ac_exact']} | "
            f"{f(d['precision'])} | {f(d['recall'])} | {f(a['precision'])} | {f(a['recall'])} | "
            f"{f(a['recall_at_k'])} ({a['k']}) | {f(a['kendall_tau'])} | {f(a['spearman'])} |"
        )
    print()
    print(
        "| case | AC converged | converged on retry | not converged | AC base overloads | "
        "new-V-violation contingencies | of which not flagged by screening |"
    )
    print("|---|---|---|---|---|---|---|")
    for c in cases:
        a = c["ac"]
        print(
            f"| {c['case']} | {a['converged']} | {a['converged_retry']} | {a['not_converged']} | "
            f"{c['counts']['ac_base_overloaded_branches']} | "
            f"{a['new_voltage_violation_contingencies']} | "
            f"{a['new_voltage_violation_not_flagged_by_screening']} |"
        )
    print()
    print(
        "| case | screening (s) | exact DC (s) | exact AC (s) | speed-up vs DC | speed-up vs AC | "
        "peak tracemalloc screening / DC / AC (MiB) | RSS end (MiB) |"
    )
    print("|---|---|---|---|---|---|---|---|")
    for c in cases:
        r, m = c["runtime"], c["memory"]
        print(
            f"| {c['case']} | {f(r['screening_median_s'])} | {f(r['dc_exact_median_s'])} | "
            f"{f(r['ac_exact_median_s'])} | "
            f"{r['dc_exact_median_s'] / r['screening_median_s']:.0f}x | "
            f"{r['ac_exact_median_s'] / r['screening_median_s']:.0f}x | "
            f"{f(m.get('screening_peak_tracemalloc_mib'), 3)} / "
            f"{f(m.get('dc_exact_peak_tracemalloc_mib'), 3)} / "
            f"{f(m.get('ac_exact_peak_tracemalloc_mib'), 3)} | "
            f"{f(m.get('process_rss_end_mib'), 4)} |"
        )


if __name__ == "__main__":
    main()
