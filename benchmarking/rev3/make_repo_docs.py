#!/usr/bin/env python3
"""
Regenerate the repository's results documentation from the analysis output.

The previous release carried headline numbers typed into FINDINGS.md and
README.md by hand. They then drifted from the paper, so a reviewer following
the open data link would have found the repository contradicting the
manuscript. Generating them from the same CSV files the paper reads removes
that possibility.
"""
import csv
import math
import os
from collections import defaultdict

REV3 = os.path.dirname(os.path.abspath(__file__))
ANA = os.path.join(REV3, "results", "analysis")
ROOT = os.path.dirname(os.path.dirname(REV3))

CONFIGS = ["vapor", "boot-t200", "boot-t64", "boot-vt"]
LABEL = {"vapor": "Vapor", "boot-t200": "Spring Boot, Tomcat 200",
         "boot-t64": "Spring Boot, Tomcat 64", "boot-vt": "Spring Boot, virtual threads"}
SCEN = ["load", "stress", "spike", "soak"]
TITLE = {"load": "Load", "stress": "Stress", "spike": "Spike", "soak": "Sustained"}


def rows(name):
    p = os.path.join(ANA, name)
    if not os.path.exists(p):
        return []
    with open(p) as fh:
        return list(csv.DictReader(fh))


def load_agg():
    out = {}
    for r in rows("aggregate.csv"):
        try:
            out[(r["scenario"], r["config"], r["metric"])] = {
                "median": float(r["median"]), "iqr": float(r["iqr"]),
                "lo": float(r["ci95_low"]), "hi": float(r["ci95_high"]), "n": int(r["n"])}
        except ValueError:
            continue
    return out


def cell(agg, scen, cfg, metric, digits=1, scale=1.0):
    e = agg.get((scen, cfg, metric))
    if not e or e["median"] is None or math.isnan(e["median"]):
        return "n/a"
    m = e["median"] * scale
    if e["lo"] is None or math.isnan(e["lo"]):
        return f"{m:.{digits}f}"
    return f"{m:.{digits}f} [{e['lo']*scale:.{digits}f}, {e['hi']*scale:.{digits}f}]"


def build_findings():
    agg = load_agg()
    if not agg:
        return None
    sig = {(r["scenario"], r["metric"], r["config_b"]): r for r in rows("significance.csv")}
    n_runs = len(rows("runs_long.csv"))
    reps = sorted({v["n"] for k, v in agg.items() if k[2] == "client_p95_ms"})

    L = []
    L.append("# Findings")
    L.append("")
    L.append("Every number on this page is produced by `benchmarking/rev3/analyze.py` from the raw")
    L.append("run output in `benchmarking/rev3/results/`. Nothing here is typed by hand. Rebuild it")
    L.append("with `./scripts/reproduce.sh --analyse-only`.")
    L.append("")
    L.append(f"Runs analysed: **{n_runs}**. Repetitions per configuration and scenario: "
             f"**{reps[0] if reps else 0}**"
             + ("" if len(reps) <= 1 else f" to {reps[-1]}") + ".")
    L.append("")
    L.append("## How to read this")
    L.append("")
    L.append("The unit of analysis is the run, not the request. Latency distributions are skewed, so")
    L.append("the centre is a median and the interval is a bootstrap 95 percent interval of the")
    L.append("median over 10,000 resamples. Configurations are compared with a two sided")
    L.append("Mann-Whitney U test, with the Vargha and Delaney A12 effect size beside it. With five")
    L.append("observations per side the smallest attainable p value is 0.008, so a non significant")
    L.append("result means the design could not resolve the difference, not that none exists.")
    L.append("")
    L.append("Results describe the tested configurations and workloads on the hardware recorded in")
    L.append("`benchmarking/rev3/results/environment.json`. They are not claims about Swift Vapor or")
    L.append("Spring Boot in general.")
    L.append("")

    L.append("## Tail latency, client measured, milliseconds")
    L.append("")
    L.append("| Scenario | " + " | ".join(LABEL[c] for c in CONFIGS) + " |")
    L.append("|---" * (len(CONFIGS) + 1) + "|")
    for s in SCEN:
        L.append(f"| {TITLE[s]} | " + " | ".join(cell(agg, s, c, "client_p95_ms") for c in CONFIGS) + " |")
    L.append("")
    L.append("Median P95 with its 95 percent interval. Full per run values are in")
    L.append("`results/analysis/runs_long.csv`.")
    L.append("")

    L.append("## Throughput, requests per second")
    L.append("")
    L.append("| Scenario | " + " | ".join(LABEL[c] for c in CONFIGS) + " |")
    L.append("|---" * (len(CONFIGS) + 1) + "|")
    for s in SCEN:
        L.append(f"| {TITLE[s]} | " + " | ".join(cell(agg, s, c, "throughput_rps") for c in CONFIGS) + " |")
    L.append("")

    L.append("## Memory, megabytes")
    L.append("")
    L.append("Resident set size is summed over the three service containers of a stack and is the")
    L.append("only quantity compared across stacks, because a resident set size and a virtual machine")
    L.append("heap are not the same thing. Heap figures exist only on the JVM and are listed")
    L.append("separately in `results/analysis/memory.csv`.")
    L.append("")
    L.append("| Scenario | " + " | ".join(LABEL[c] for c in CONFIGS) + " |")
    L.append("|---" * (len(CONFIGS) + 1) + "|")
    MB = 1024.0 * 1024.0
    for s in SCEN:
        L.append(f"| {TITLE[s]} | " + " | ".join(
            cell(agg, s, c, "rss_steady_bytes", 0, 1.0 / MB) for c in CONFIGS) + " |")
    L.append("")

    L.append("## Significance, Vapor against each Spring Boot configuration")
    L.append("")
    L.append("| Scenario | Comparison | median Vapor | median other | p | A12 | separated at 0.05 |")
    L.append("|---|---|---|---|---|---|---|")
    any_sig = False
    for s in SCEN:
        for c in CONFIGS[1:]:
            r = sig.get((s, "client_p95_ms", c))
            if not r:
                continue
            any_sig = True
            L.append(f"| {TITLE[s]} | Vapor vs {LABEL[c]} | {r.get('median_a','')} | "
                     f"{r.get('median_b','')} | {r.get('p_value','')} | "
                     f"{r.get('vargha_delaney_a12','')} | {r.get('significant_at_0.05','')} |")
    if not any_sig:
        L.append("| n/a | n/a | n/a | n/a | n/a | n/a | n/a |")
    L.append("")

    L.append("## What changed from the first release")
    L.append("")
    L.append("The first release reported single runs. Two defects were found while preparing this one")
    L.append("and both are reported rather than quietly fixed.")
    L.append("")
    L.append("1. **The list endpoints did not return the same result set.** The Vapor services")
    L.append("   returned a bounded, ordered page while the Spring services returned the whole table,")
    L.append("   which grew as the workload inserted rows. Part of the difference the first release")
    L.append("   attributed to concurrency architecture was a serialisation cost the benchmark itself")
    L.append("   created.")
    L.append("2. **The measurement window counted traffic the client never issued.** Warm-up requests")
    L.append("   and the health probe reached the service histograms without reaching the client")
    L.append("   metrics, and both are much faster than a real request, so the server side percentiles")
    L.append("   were pulled down. Warm-up now runs in a separate process before the window opens, and")
    L.append("   probe and scrape traffic is removed from the server side figures.")
    L.append("")
    L.append("Every number on this page comes from runs made after both fixes. The numbers in the")
    L.append("first release are superseded and should not be cited.")
    L.append("")
    return "\n".join(L) + "\n"


def main():
    text = build_findings()
    if text is None:
        print("no analysis output yet, run analyze.py first")
        return 1
    out = os.path.join(REV3, "results", "FINDINGS.generated.md")
    with open(out, "w") as fh:
        fh.write(text)
    print("written", out)

    # Also write it where the working copy keeps its findings page, so the sync
    # to the public repository replaces the superseded numbers instead of
    # leaving them next to the new ones.
    top = os.path.join(ROOT, "FINDINGS.md")
    with open(top, "w") as fh:
        fh.write(text)
    print("written", top)
    print(f"  {len(text.splitlines())} lines")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
