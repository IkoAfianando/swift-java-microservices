#!/usr/bin/env python3
"""
Research Analysis Script
Swift vs Java Microservices Performance Comparison
Iko Afianando (2602261970) – BINUS University 2025/2026

Usage:
    python3 compare.py --results-dir ../results --timestamp 20250101_120000
    python3 compare.py --results-dir ../results  # analyze all JSON files
"""

import argparse
import json
import os
import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
import statistics

try:
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    import numpy as np
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False
    print("Warning: matplotlib not found. Install: pip install matplotlib numpy")

# ──────────────────────────────────────────────────────────

@dataclass
class BenchmarkResult:
    language: str       # "swift" or "java"
    scenario: str
    p50_ms: float = 0
    p95_ms: float = 0
    p99_ms: float = 0
    avg_ms: float = 0
    rps: float = 0
    error_rate: float = 0
    max_ms: float = 0


def parse_k6_summary(filepath: Path) -> dict:
    """Parse a k6 JSON summary export file."""
    with open(filepath) as f:
        return json.load(f)


def extract_metrics(summary: dict, language: str, scenario: str) -> BenchmarkResult:
    """Extract research metrics from a k6 summary."""
    result = BenchmarkResult(language=language, scenario=scenario)

    metrics = summary.get("metrics", {})
    key = f"{language}_request_duration"

    if key in metrics:
        m = metrics[key]
        result.p50_ms  = m.get("values", {}).get("p(50)", 0)
        result.p95_ms  = m.get("values", {}).get("p(95)", 0)
        result.p99_ms  = m.get("values", {}).get("p(99)", 0)
        result.avg_ms  = m.get("values", {}).get("avg", 0)
        result.max_ms  = m.get("values", {}).get("max", 0)
    elif "http_req_duration" in metrics:
        # Fallback to global metric if custom not present
        m = metrics["http_req_duration"]
        result.p50_ms  = m.get("values", {}).get("p(50)", 0)
        result.p95_ms  = m.get("values", {}).get("p(95)", 0)
        result.p99_ms  = m.get("values", {}).get("p(99)", 0)
        result.avg_ms  = m.get("values", {}).get("avg", 0)
        result.max_ms  = m.get("values", {}).get("max", 0)

    rps_key = f"{language}_requests_total"
    if rps_key in metrics:
        result.rps = metrics[rps_key].get("values", {}).get("rate", 0)
    elif "http_reqs" in metrics:
        result.rps = metrics["http_reqs"].get("values", {}).get("rate", 0)

    err_key = f"{language}_error_rate"
    if err_key in metrics:
        result.error_rate = metrics[err_key].get("values", {}).get("rate", 0)
    elif "http_req_failed" in metrics:
        result.error_rate = metrics["http_req_failed"].get("values", {}).get("rate", 0)

    return result


def print_comparison_table(swift: BenchmarkResult, java: BenchmarkResult):
    """Print a formatted comparison table to stdout."""
    def diff(s, j, lower_is_better=True):
        if j == 0:
            return "N/A"
        pct = ((s - j) / j) * 100
        if lower_is_better:
            symbol = "✓ SWIFT WINS" if pct < 0 else ("✓ JAVA WINS" if pct > 5 else "≈ TIED")
        else:
            symbol = "✓ SWIFT WINS" if pct > 0 else ("✓ JAVA WINS" if pct < -5 else "≈ TIED")
        return f"{pct:+.1f}% ({symbol})"

    print(f"\n{'='*65}")
    print(f"  SCENARIO: {swift.scenario.upper()}")
    print(f"{'='*65}")
    print(f"  {'Metric':<25} {'Swift':>12} {'Java':>12} {'Comparison':>15}")
    print(f"  {'-'*60}")
    print(f"  {'Throughput (RPS)':<25} {swift.rps:>10.1f} {java.rps:>10.1f}   {diff(swift.rps, java.rps, False)}")
    print(f"  {'P50 Latency (ms)':<25} {swift.p50_ms:>10.1f} {java.p50_ms:>10.1f}   {diff(swift.p50_ms, java.p50_ms)}")
    print(f"  {'P95 Latency (ms)':<25} {swift.p95_ms:>10.1f} {java.p95_ms:>10.1f}   {diff(swift.p95_ms, java.p95_ms)}")
    print(f"  {'P99 Latency (ms)':<25} {swift.p99_ms:>10.1f} {java.p99_ms:>10.1f}   {diff(swift.p99_ms, java.p99_ms)}")
    print(f"  {'Avg Latency (ms)':<25} {swift.avg_ms:>10.1f} {java.avg_ms:>10.1f}   {diff(swift.avg_ms, java.avg_ms)}")
    print(f"  {'Max Latency (ms)':<25} {swift.max_ms:>10.1f} {java.max_ms:>10.1f}   {diff(swift.max_ms, java.max_ms)}")
    print(f"  {'Error Rate':<25} {swift.error_rate:>9.2%} {java.error_rate:>10.2%}   {diff(swift.error_rate, java.error_rate)}")
    print(f"{'='*65}")


def plot_comparison(results: list[tuple[BenchmarkResult, BenchmarkResult]], output_dir: Path):
    """Generate comparison bar charts."""
    if not HAS_MATPLOTLIB:
        print("Skipping plots – matplotlib not installed")
        return

    scenarios = [s.scenario for s, j in results]
    swift_p95 = [s.p95_ms for s, j in results]
    java_p95  = [j.p95_ms for s, j in results]
    swift_rps = [s.rps for s, j in results]
    java_rps  = [j.rps for s, j in results]
    swift_err = [s.error_rate * 100 for s, j in results]
    java_err  = [j.error_rate * 100 for s, j in results]

    x = np.arange(len(scenarios))
    width = 0.35

    fig, axes = plt.subplots(1, 3, figsize=(18, 6))
    fig.suptitle("Swift vs Java Microservices – Research Benchmark\nIko Afianando (2602261970) – BINUS University 2025/2026",
                 fontsize=13, fontweight="bold")

    # P95 Latency
    ax = axes[0]
    b1 = ax.bar(x - width/2, swift_p95, width, label="Swift (Vapor)", color="#FF6B35", alpha=0.85)
    b2 = ax.bar(x + width/2, java_p95,  width, label="Java (Spring Boot)", color="#4A90D9", alpha=0.85)
    ax.set_xlabel("Scenario"); ax.set_ylabel("P95 Latency (ms)")
    ax.set_title("P95 Latency Comparison\n(lower is better)")
    ax.set_xticks(x); ax.set_xticklabels(scenarios, rotation=15)
    ax.legend(); ax.bar_label(b1, fmt="%.0f"); ax.bar_label(b2, fmt="%.0f")

    # Throughput (RPS)
    ax = axes[1]
    b1 = ax.bar(x - width/2, swift_rps, width, label="Swift (Vapor)", color="#FF6B35", alpha=0.85)
    b2 = ax.bar(x + width/2, java_rps,  width, label="Java (Spring Boot)", color="#4A90D9", alpha=0.85)
    ax.set_xlabel("Scenario"); ax.set_ylabel("Requests per Second")
    ax.set_title("Throughput Comparison\n(higher is better)")
    ax.set_xticks(x); ax.set_xticklabels(scenarios, rotation=15)
    ax.legend(); ax.bar_label(b1, fmt="%.0f"); ax.bar_label(b2, fmt="%.0f")

    # Error Rate
    ax = axes[2]
    b1 = ax.bar(x - width/2, swift_err, width, label="Swift (Vapor)", color="#FF6B35", alpha=0.85)
    b2 = ax.bar(x + width/2, java_err,  width, label="Java (Spring Boot)", color="#4A90D9", alpha=0.85)
    ax.set_xlabel("Scenario"); ax.set_ylabel("Error Rate (%)")
    ax.set_title("Error Rate Comparison\n(lower is better)")
    ax.set_xticks(x); ax.set_xticklabels(scenarios, rotation=15)
    ax.legend(); ax.bar_label(b1, fmt="%.2f%%"); ax.bar_label(b2, fmt="%.2f%%")

    plt.tight_layout()
    outfile = output_dir / "benchmark_comparison.png"
    plt.savefig(outfile, dpi=150, bbox_inches="tight")
    print(f"\nChart saved: {outfile}")
    plt.close()


def generate_csv(results: list[tuple[BenchmarkResult, BenchmarkResult]], output_dir: Path, timestamp: str):
    """Export results to CSV for inclusion in paper."""
    outfile = output_dir / f"{timestamp}_comparison.csv"
    with open(outfile, "w") as f:
        f.write("scenario,language,rps,p50_ms,p95_ms,p99_ms,avg_ms,error_rate\n")
        for swift, java in results:
            for r in (swift, java):
                f.write(f"{r.scenario},{r.language},{r.rps:.2f},{r.p50_ms:.2f},"
                        f"{r.p95_ms:.2f},{r.p99_ms:.2f},{r.avg_ms:.2f},{r.error_rate:.4f}\n")
    print(f"CSV exported: {outfile}")


def main():
    parser = argparse.ArgumentParser(description="Analyze Swift vs Java benchmark results")
    parser.add_argument("--results-dir", default="../results", help="Directory containing k6 JSON summary files")
    parser.add_argument("--timestamp", default=None, help="Specific run timestamp to analyze (e.g. 20250101_120000)")
    args = parser.parse_args()

    results_dir = Path(args.results_dir)
    if not results_dir.exists():
        print(f"Results directory not found: {results_dir}")
        sys.exit(1)

    # Find summary JSON files
    pattern = f"{args.timestamp}_*_summary.json" if args.timestamp else "*_summary.json"
    summary_files = list(results_dir.glob(pattern))

    if not summary_files:
        print(f"No summary files found in {results_dir} matching '{pattern}'")
        print("Run benchmarks first: ./run-all.sh")
        sys.exit(0)

    print(f"\nFound {len(summary_files)} summary file(s)")

    paired_results = []
    scenarios_seen = {}

    for f in sorted(summary_files):
        # Extract scenario name from filename: TIMESTAMP_SCENARIONAME_summary.json
        parts = f.stem.replace("_summary", "").split("_", 2)
        if len(parts) < 3:
            continue
        scenario = parts[2]

        try:
            summary = parse_k6_summary(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Could not parse {f}: {e}")
            continue

        swift_result = extract_metrics(summary, "swift", scenario)
        java_result  = extract_metrics(summary, "java",  scenario)
        paired_results.append((swift_result, java_result))
        scenarios_seen[scenario] = (swift_result, java_result)
        print_comparison_table(swift_result, java_result)

    if paired_results:
        ts = args.timestamp or "latest"
        plot_comparison(paired_results, results_dir)
        generate_csv(paired_results, results_dir, ts)
        print("\n✓ Analysis complete. Review results for your paper!")


if __name__ == "__main__":
    main()
