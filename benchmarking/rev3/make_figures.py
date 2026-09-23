#!/usr/bin/env python3
"""
Build the manuscript figures from the analysis output.

Every value plotted is read from results/analysis/*.csv, so no number in a
figure is typed by hand and a figure can never drift away from the table it
illustrates.

Figures produced, at 600 dpi:
  fig_latency_throughput.png  two panels, double column: tail latency with
                              confidence intervals, and sustained throughput
                              with error rate. This replaces the two separate
                              single-column figures of the previous version.
  fig_memory.png              memory with the distinct quantities kept apart,
                              so nothing compares a resident set size against a
                              heap figure.
  fig_diagnostics.png         the measurements behind the saturation
                              explanation, per scenario.
"""
import csv
import math
import os
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

REV3 = os.path.dirname(os.path.abspath(__file__))
ANA = os.path.join(REV3, "results", "analysis")
OUT = os.path.join(REV3, "results", "figures")

CONFIGS = ["vapor", "boot-t200", "boot-t64", "boot-vt"]
LABELS = {"vapor": "Vapor", "boot-t200": "Spring Boot\nTomcat 200",
          "boot-t64": "Spring Boot\nTomcat 64", "boot-vt": "Spring Boot\nvirtual threads"}
COLORS = {"vapor": "#1f5fa8", "boot-t200": "#b0561a", "boot-t64": "#d9a23b", "boot-vt": "#3f8f5d"}
SCEN = ["load", "stress", "spike", "soak"]
SCEN_LABEL = {"load": "Load", "stress": "Stress", "spike": "Spike", "soak": "Sustained"}

plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Times New Roman", "DejaVu Serif"],
    "font.size": 8,
    "axes.labelsize": 8,
    "axes.titlesize": 8.5,
    "xtick.labelsize": 7.5,
    "ytick.labelsize": 7.5,
    "legend.fontsize": 7.5,
    "axes.linewidth": 0.6,
    "grid.linewidth": 0.4,
})


def load_aggregate():
    d = defaultdict(dict)
    path = os.path.join(ANA, "aggregate.csv")
    if not os.path.exists(path):
        return d
    with open(path) as fh:
        for r in csv.DictReader(fh):
            try:
                d[(r["scenario"], r["config"])][r["metric"]] = {
                    "median": float(r["median"]), "iqr": float(r["iqr"]),
                    "lo": float(r["ci95_low"]), "hi": float(r["ci95_high"]),
                    "n": int(r["n"]),
                }
            except (ValueError, KeyError):
                continue
    return d


def get(agg, scen, cfg, metric, field="median"):
    v = agg.get((scen, cfg), {}).get(metric)
    if not v:
        return float("nan")
    x = v[field]
    return x if not math.isnan(x) else float("nan")


def grouped_bars(ax, agg, metric, ylabel, title, scale=1.0, logy=False, errorbars=True):
    x = np.arange(len(SCEN))
    w = 0.2
    any_data = False
    for i, cfg in enumerate(CONFIGS):
        med = [get(agg, s, cfg, metric) * scale for s in SCEN]
        lo = [get(agg, s, cfg, metric, "lo") * scale for s in SCEN]
        hi = [get(agg, s, cfg, metric, "hi") * scale for s in SCEN]
        if all(math.isnan(v) for v in med):
            continue
        any_data = True
        pos = x + (i - 1.5) * w
        err = None
        if errorbars:
            lower = [max(0.0, m - l) if not (math.isnan(m) or math.isnan(l)) else 0.0
                     for m, l in zip(med, lo)]
            upper = [max(0.0, h - m) if not (math.isnan(m) or math.isnan(h)) else 0.0
                     for m, h in zip(med, hi)]
            err = [lower, upper]
        ax.bar(pos, [0 if math.isnan(v) else v for v in med], w,
               yerr=err, capsize=1.8, error_kw={"elinewidth": 0.6, "capthick": 0.6},
               label=LABELS[cfg].replace("\n", " "), color=COLORS[cfg],
               edgecolor="white", linewidth=0.4)
    if not any_data:
        ax.text(0.5, 0.5, "no data", ha="center", va="center", transform=ax.transAxes)
    if logy:
        ax.set_yscale("log")
    ax.set_xticks(x)
    ax.set_xticklabels([SCEN_LABEL[s] for s in SCEN])
    ax.set_ylabel(ylabel)
    ax.set_title(title, fontweight="bold")
    ax.grid(axis="y", alpha=0.3, linewidth=0.4)
    ax.set_axisbelow(True)


def fig_latency_throughput(agg):
    fig, axes = plt.subplots(1, 2, figsize=(7.0, 2.7))
    grouped_bars(axes[0], agg, "client_p95_ms",
                 "95th percentile latency (ms)",
                 "(a) Tail latency, client measured", logy=True)
    grouped_bars(axes[1], agg, "throughput_rps",
                 "Completed requests per second",
                 "(b) Sustained throughput")
    h, l = axes[0].get_legend_handles_labels()
    if h:
        fig.legend(h, l, loc="lower center", ncol=4, frameon=False,
                   bbox_to_anchor=(0.5, -0.06))
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "fig_latency_throughput.png"), dpi=600, bbox_inches="tight")
    plt.close(fig)
    print("  fig_latency_throughput.png")


def fig_memory(agg):
    MB = 1024.0 * 1024.0
    fig, axes = plt.subplots(1, 2, figsize=(7.0, 2.6))
    grouped_bars(axes[0], agg, "rss_steady_bytes", "Resident set size (MB)",
                 "(a) Resident set size, steady state", scale=1.0 / MB)

    # Heap only exists on the JVM, so it is shown on its own axes rather than
    # placed beside a resident set size, which is what produced the inconsistent
    # ratios in the previous version.
    x = np.arange(len(SCEN))
    w = 0.26
    plotted = False
    for i, cfg in enumerate(CONFIGS[1:]):
        used = [get(agg, s, cfg, "jvm_heap_used_steady_bytes") / MB for s in SCEN]
        comm = [get(agg, s, cfg, "jvm_heap_committed_steady_bytes") / MB for s in SCEN]
        if all(math.isnan(v) for v in used):
            continue
        plotted = True
        pos = x + (i - 1) * w
        axes[1].bar(pos, [0 if math.isnan(v) else v for v in used], w,
                    color=COLORS[cfg], edgecolor="white", linewidth=0.4,
                    label=LABELS[cfg].replace("\n", " ") + ", used")
        # The committed heap is drawn as the band above the used heap, so the
        # bar height is the difference and never negative.
        axes[1].bar(pos, [max(0.0, (0.0 if math.isnan(c) else c) - (0.0 if math.isnan(u) else u))
                          for u, c in zip(used, comm)], w,
                    bottom=[0 if math.isnan(v) else v for v in used],
                    color=COLORS[cfg], alpha=0.35, edgecolor="white", linewidth=0.4,
                    label=LABELS[cfg].replace("\n", " ") + ", committed")
    if not plotted:
        axes[1].text(0.5, 0.5, "no data", ha="center", va="center", transform=axes[1].transAxes)
    axes[1].set_xticks(x)
    axes[1].set_xticklabels([SCEN_LABEL[s] for s in SCEN])
    axes[1].set_ylabel("JVM heap (MB)")
    axes[1].set_title("(b) JVM heap, used and committed", fontweight="bold")
    axes[1].grid(axis="y", alpha=0.3, linewidth=0.4)
    axes[1].set_axisbelow(True)
    axes[1].legend(fontsize=5.8, frameon=False, ncol=1, loc="upper left")

    h, l = axes[0].get_legend_handles_labels()
    if h:
        fig.legend(h, l, loc="lower center", ncol=4, frameon=False, bbox_to_anchor=(0.5, -0.07))
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "fig_memory.png"), dpi=600, bbox_inches="tight")
    plt.close(fig)
    print("  fig_memory.png")


def fig_diagnostics(agg):
    fig, axes = plt.subplots(1, 3, figsize=(7.0, 2.3))
    grouped_bars(axes[0], agg, "cpu_mean_percent_of_one_core",
                 "CPU, percent of one core", "(a) CPU against a 450 percent quota")
    for a in (axes[0],):
        a.axhline(450, color="#666", linestyle=":", linewidth=0.7)
    grouped_bars(axes[1], agg, "probe_p95_ms",
                 "Probe latency (ms)", "(b) Control-plane responsiveness", logy=True)
    grouped_bars(axes[2], agg, "error_rate", "Error rate", "(c) Error rate")
    h, l = axes[0].get_legend_handles_labels()
    if h:
        fig.legend(h, l, loc="lower center", ncol=4, frameon=False, bbox_to_anchor=(0.5, -0.1))
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "fig_diagnostics.png"), dpi=600, bbox_inches="tight")
    plt.close(fig)
    print("  fig_diagnostics.png")


def main():
    os.makedirs(OUT, exist_ok=True)
    agg = load_aggregate()
    if not agg:
        print("no aggregate.csv yet, run analyze.py first")
        return 1
    fig_latency_throughput(agg)
    fig_memory(agg)
    fig_diagnostics(agg)
    print("figures written to", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
