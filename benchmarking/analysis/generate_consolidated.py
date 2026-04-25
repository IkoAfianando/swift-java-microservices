#!/usr/bin/env python3
"""
Consolidated multi-scenario report.
Finds all k6 summary JSONs sharing a timestamp prefix (one full benchmark suite),
generates per-scenario reports + a master comparison.

Usage:
  python3 generate_consolidated.py [TIMESTAMP_PREFIX]
  (defaults to most recent timestamp prefix in benchmarking/results/)
"""

import json
import os
import sys
import subprocess
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = Path(os.environ.get("RESULTS_DIR", str(ROOT / "benchmarking" / "results")))
REPORTS_DIR = RESULTS_DIR / "reports"
GENERATE = Path(__file__).parent / "generate_report.py"


def find_timestamp_groups():
    """Group summary files by their timestamp prefix (YYYYMMDD_HHMMSS)."""
    groups = {}
    for p in RESULTS_DIR.glob("*_summary.json"):
        parts = p.stem.split("_")
        if len(parts) >= 3:
            prefix = parts[0] + "_" + parts[1]
            groups.setdefault(prefix, []).append(p)
    return groups


def main():
    REPORTS_DIR.mkdir(exist_ok=True)

    # --all collapses every summary in the folder into one master report.
    combine_all = "--all" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--all"]

    if combine_all:
        summaries = sorted(RESULTS_DIR.glob("*_summary.json"))
        if not summaries:
            sys.exit("No summary JSONs found.")
        prefix = "FINAL_SUITE"
        print(f"Processing ALL summaries in {RESULTS_DIR} ({len(summaries)} files):")
    else:
        groups = find_timestamp_groups()
        if not groups:
            sys.exit("No summary JSONs found.")
        if args:
            prefix = args[0]
            if prefix not in groups:
                sys.exit(f"No summaries found for prefix {prefix}. Available: {list(groups.keys())}")
        else:
            prefix = sorted(groups.keys())[-1]
        summaries = sorted(groups[prefix])
        print(f"Processing suite '{prefix}' — {len(summaries)} scenario(s):")

    for s in summaries:
        print(f"  - {s.name}")

    scenario_data = []
    for s in summaries:
        stem = s.stem.replace("_summary", "")
        # Stem looks like "20260425_141231_spike-test"; drop the first two segments.
        parts = stem.split("_")
        scenario_name = "_".join(parts[2:]) if len(parts) >= 3 else stem
        # Keep timestamp for unique filenames in --all mode
        scenario_label = f"{parts[0]}_{parts[1]}_{scenario_name}" if combine_all else scenario_name
        print(f"\n→ Generating per-scenario report for {scenario_label}...")
        result = subprocess.run(["python3", str(GENERATE), str(s)], cwd=ROOT,
                                capture_output=True, text=True)
        if result.returncode != 0:
            print(f"   ⚠️  generate_report.py failed for {s.name}, skipping. Stderr:")
            print(f"   {result.stderr.splitlines()[-1] if result.stderr else 'unknown'}")
            continue
        print(result.stdout.strip().split('\n')[-3] if result.stdout else "")

        with s.open() as f:
            k6 = json.load(f)
        m = k6.get("metrics", {})

        # Skip aborted/empty runs in master report aggregation too
        if not m.get("iterations", {}).get("count"):
            print(f"   ⚠️  {s.name}: aborted/empty run, excluding from master report")
            continue
        scenario_data.append({
            "name": scenario_name,
            "file_prefix": f"{parts[0]}_{parts[1]}",
            "summary_path": s,
            "iters": m.get("iterations", {}).get("count", 0),
            "iter_rate": m.get("iterations", {}).get("rate", 0),
            "http_reqs": m.get("http_reqs", {}).get("count", 0),
            "http_failed": m.get("http_req_failed", {}).get("value", 0),
            "vus_max": m.get("vus_max", {}).get("max", 0),
            "swift": {
                "med": m.get("swift_request_duration", {}).get("med"),
                "p90": m.get("swift_request_duration", {}).get("p(90)"),
                "p95": m.get("swift_request_duration", {}).get("p(95)"),
                "avg": m.get("swift_request_duration", {}).get("avg"),
                "max": m.get("swift_request_duration", {}).get("max"),
                "err_rate": m.get("swift_error_rate", {}).get("value"),
                "total": m.get("swift_requests_total", {}).get("count"),
                "rate": m.get("swift_requests_total", {}).get("rate"),
            },
            "java": {
                "med": m.get("java_request_duration", {}).get("med"),
                "p90": m.get("java_request_duration", {}).get("p(90)"),
                "p95": m.get("java_request_duration", {}).get("p(95)"),
                "avg": m.get("java_request_duration", {}).get("avg"),
                "max": m.get("java_request_duration", {}).get("max"),
                "err_rate": m.get("java_error_rate", {}).get("value"),
                "total": m.get("java_requests_total", {}).get("count"),
                "rate": m.get("java_requests_total", {}).get("rate"),
            },
        })

    # Build master comparison report
    md_path = REPORTS_DIR / f"MASTER_REPORT_{prefix}.md"
    md = []

    md.append(f"# MASTER REPORT — Swift Vapor vs Java Spring Boot")
    md.append("")
    md.append(f"**Researcher:** Iko Afianando (NIM 2602261970)  ")
    md.append(f"**Institution:** BINUS University 2025/2026 — Enrichment Program  ")
    md.append(f"**Suite ID:** `{prefix}`  ")
    md.append(f"**Scenarios run:** {len(scenario_data)}  ")
    md.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    md.append("")
    md.append("---")
    md.append("")

    md.append("## 1. Suite Summary")
    md.append("")
    md.append("| Scenario | VUs (max) | Iterations | Total Reqs | Duration | HTTP Failed |")
    md.append("|---|---|---|---|---|---|")
    for s in scenario_data:
        dur = s["iters"] / s["iter_rate"] if s["iter_rate"] else 0
        md.append(f"| **{s['name']}** | {int(s['vus_max'])} | {int(s['iters']):,} | {int(s['http_reqs']):,} | "
                  f"{dur/60:.1f} min | {s['http_failed']*100:.2f}% |")
    md.append("")

    md.append("## 2. Latency Comparison Across Scenarios (k6 client-side)")
    md.append("")
    md.append("### 2.1 Median (P50)")
    md.append("")
    md.append("| Scenario | Swift P50 | Java P50 | Winner | Margin |")
    md.append("|---|---|---|---|---|")
    for s in scenario_data:
        sw, ja = s["swift"]["med"], s["java"]["med"]
        if sw and ja:
            winner = "🟢 Swift" if sw < ja else "🔴 Java"
            margin = f"{max(sw,ja)/min(sw,ja):.2f}× faster"
            md.append(f"| {s['name']} | {sw:.2f} ms | {ja:.2f} ms | {winner} | {margin} |")
    md.append("")
    md.append("### 2.2 P95")
    md.append("")
    md.append("| Scenario | Swift P95 | Java P95 | Winner | Margin |")
    md.append("|---|---|---|---|---|")
    for s in scenario_data:
        sw, ja = s["swift"]["p95"], s["java"]["p95"]
        if sw and ja:
            winner = "🟢 Swift" if sw < ja else "🔴 Java"
            margin = f"{max(sw,ja)/min(sw,ja):.2f}× faster"
            md.append(f"| {s['name']} | {sw:.2f} ms | {ja:.2f} ms | {winner} | {margin} |")
    md.append("")
    md.append("### 2.3 Max latency (worst-case observed)")
    md.append("")
    md.append("| Scenario | Swift Max | Java Max | Winner |")
    md.append("|---|---|---|---|")
    for s in scenario_data:
        sw, ja = s["swift"]["max"], s["java"]["max"]
        if sw and ja:
            winner = "🟢 Swift" if sw < ja else "🔴 Java"
            md.append(f"| {s['name']} | {sw:.2f} ms | {ja:.2f} ms | {winner} |")
    md.append("")

    md.append("## 3. Throughput & Error Rate")
    md.append("")
    md.append("| Scenario | Swift RPS | Java RPS | Swift Err % | Java Err % |")
    md.append("|---|---|---|---|---|")
    for s in scenario_data:
        md.append(f"| {s['name']} | {s['swift']['rate']:.2f} | {s['java']['rate']:.2f} | "
                  f"{(s['swift']['err_rate'] or 0)*100:.2f}% | {(s['java']['err_rate'] or 0)*100:.2f}% |")
    md.append("")

    md.append("## 4. Verdict per Scenario")
    md.append("")
    for s in scenario_data:
        md.append(f"### {s['name']}")
        md.append("")
        wins = []
        sw_p95, ja_p95 = s["swift"]["p95"], s["java"]["p95"]
        sw_med, ja_med = s["swift"]["med"], s["java"]["med"]
        sw_max, ja_max = s["swift"]["max"], s["java"]["max"]
        sw_err, ja_err = (s["swift"]["err_rate"] or 0), (s["java"]["err_rate"] or 0)

        if sw_med and ja_med:
            wins.append(("P50", "Swift" if sw_med < ja_med else "Java",
                         f"{min(sw_med, ja_med):.2f}ms vs {max(sw_med, ja_med):.2f}ms"))
        if sw_p95 and ja_p95:
            wins.append(("P95", "Swift" if sw_p95 < ja_p95 else "Java",
                         f"{min(sw_p95, ja_p95):.2f}ms vs {max(sw_p95, ja_p95):.2f}ms"))
        if sw_max and ja_max:
            wins.append(("Max", "Swift" if sw_max < ja_max else "Java",
                         f"{min(sw_max, ja_max):.2f}ms vs {max(sw_max, ja_max):.2f}ms"))
        wins.append(("Errors", "Swift" if sw_err < ja_err else ("Java" if ja_err < sw_err else "Tied"),
                     f"{sw_err*100:.2f}% vs {ja_err*100:.2f}%"))

        md.append("| Metric | Winner | Detail |")
        md.append("|---|---|---|")
        for metric, winner, detail in wins:
            md.append(f"| {metric} | **{winner}** | {detail} |")
        md.append("")
        md.append(f"*See: [report_{s['file_prefix']}_{s['name']}.md](./report_{s['file_prefix']}_{s['name']}.md)*")
        md.append("")

    md.append("## 5. Apple-to-Apple Parity Configuration")
    md.append("")
    md.append("All scenarios in this suite use the SAME parity setup:")
    md.append("")
    md.append("| Aspect | Swift Vapor | Java Spring Boot |")
    md.append("|---|---|---|")
    md.append("| Database | Separate `swift_*_db` per service | Separate `java_*_db` per service |")
    md.append("| bcrypt cost factor | `app.passwords.use(.bcrypt(cost: 10))` | `new BCryptPasswordEncoder(10)` |")
    md.append("| bcrypt threading | `req.password.async.hash(_:)` → NIOThreadPool | Tomcat worker threads |")
    md.append("| DB connection pool | `maxConnectionsPerEventLoop: 2` × 10 = 20 | HikariCP `maximum-pool-size: 20` |")
    md.append("| HTTP server | SwiftNIO (10 event loops) | Tomcat (200 thread max) |")
    md.append("| Histogram buckets | **72 buckets matching Micrometer defaults** | Spring Boot Micrometer defaults |")
    md.append("| Cache | Vapor Redis client (manual TTL 30s) | Spring `@Cacheable` (Redis TTL 30s) |")
    md.append("")
    md.append("> Histogram buckets are **bit-for-bit identical** between stacks, ensuring "
              "`histogram_quantile()` interpolation produces objective and comparable percentiles.")
    md.append("")

    md.append("## 6. Per-Scenario Reports")
    md.append("")
    for s in scenario_data:
        md.append(f"- [{s['name']}](./report_{s['file_prefix']}_{s['name']}.md)")
    md.append("")

    md_path.write_text("\n".join(md))
    print(f"\n✅ Master report: {md_path}")
    print(f"   Per-scenario reports: {REPORTS_DIR}/report_{prefix}_*.md")
    print(f"\nOpen master report:\n  open {md_path}")


if __name__ == "__main__":
    main()
