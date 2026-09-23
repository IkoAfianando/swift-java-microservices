#!/usr/bin/env python3
"""
Aggregate the revision-3 benchmark runs into the tables the manuscript reports.

Every number the paper states comes out of this script, so the reported result
is regenerable from the committed raw data with one command.

What it produces, in results/analysis/:
  runs_long.csv           one row per individual run, every extracted metric
  aggregate.csv           per configuration and scenario: n, median, IQR,
                          bootstrap 95% confidence interval of the median
  significance.csv        Mann-Whitney U, Vapor against each Spring Boot
                          configuration, with effect size
  memory.csv              the distinct memory quantities, kept apart
  diagnostics.csv         CPU, GC, queue depth, busy threads, control-plane
                          responsiveness, database wait
  client_vs_server.csv    client-measured against server-measured percentiles
  endpoint_level.csv      per-endpoint percentiles, for the repository
  throughput_saturation.csv  throughput over time and the saturation point
  SUMMARY.md              a readable digest

Statistical choices, and why:
  * The unit of analysis is the run, not the request. Treating individual
    requests as independent observations would inflate the sample size by four
    orders of magnitude and manufacture significance out of nothing.
  * Latency distributions are skewed, so the centre is reported as a median and
    the spread as an interquartile range, and the comparison is Mann-Whitney U
    rather than a t-test.
  * The confidence interval of the median is obtained by bootstrap resampling
    because n is small and no distributional assumption is warranted.
  * With five repetitions per arm the smallest attainable two-sided p-value is
    2/C(10,5) = 0.0079. That is reported openly rather than hidden.
"""
import csv
import glob
import json
import math
import os
import re
import sys
from collections import defaultdict

import numpy as np
from scipy import stats

REV3 = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(REV3, "results")
OUT = os.path.join(RESULTS, "analysis")

CONFIG_ORDER = ["vapor", "boot-t200", "boot-t64", "boot-vt"]
CONFIG_LABEL = {
    "vapor": "Vapor",
    "boot-t200": "Spring Boot, Tomcat 200",
    "boot-t64": "Spring Boot, Tomcat 64",
    "boot-vt": "Spring Boot, virtual threads",
}
SCEN_ORDER = ["load", "stress", "spike", "soak"]
BOOT_RESAMPLES = 10000
RNG = np.random.default_rng(20260922)


# ----------------------------------------------------------------- helpers

def med_iqr_ci(vals):
    """Median, interquartile range and a bootstrap 95% CI of the median."""
    a = np.asarray([v for v in vals if v is not None and not (isinstance(v, float) and math.isnan(v))],
                   dtype=float)
    if a.size == 0:
        return (float("nan"),) * 6 + (0,)
    med = float(np.median(a))
    q1, q3 = (float(np.percentile(a, 25)), float(np.percentile(a, 75)))
    if a.size < 2:
        return med, q3 - q1, q1, q3, float("nan"), float("nan"), a.size
    idx = RNG.integers(0, a.size, size=(BOOT_RESAMPLES, a.size))
    meds = np.median(a[idx], axis=1)
    lo, hi = (float(np.percentile(meds, 2.5)), float(np.percentile(meds, 97.5)))
    return med, q3 - q1, q1, q3, lo, hi, a.size


def mannwhitney(a, b):
    """Two-sided Mann-Whitney U with a rank-biserial effect size."""
    a = np.asarray([x for x in a if x is not None and not math.isnan(x)], dtype=float)
    b = np.asarray([x for x in b if x is not None and not math.isnan(x)], dtype=float)
    if a.size < 2 or b.size < 2:
        return float("nan"), float("nan"), float("nan"), a.size, b.size
    method = "exact" if (a.size <= 20 and b.size <= 20) else "asymptotic"
    try:
        u, p = stats.mannwhitneyu(a, b, alternative="two-sided", method=method)
    except Exception:
        u, p = stats.mannwhitneyu(a, b, alternative="two-sided")
    rbc = 2.0 * float(u) / (a.size * b.size) - 1.0
    return float(u), float(p), rbc, a.size, b.size


def vargha_delaney_a12(rbc):
    """Vargha and Delaney's A12, the probability that a randomly drawn value
    from the first group exceeds one from the second. It is a monotone
    transform of the rank-biserial correlation, reported because a
    standardised effect size says more than a p-value when n is five."""
    if math.isnan(rbc):
        return float("nan")
    return (rbc + 1.0) / 2.0


def prom_quantile(buckets, q):
    """Percentile from cumulative histogram buckets.

    Reproduces the interpolation Prometheus histogram_quantile performs: locate
    the bucket in which the rank falls and interpolate linearly between that
    bucket's lower and upper boundary. The value is therefore bounded by the
    bucket resolution, which is exactly why it can differ from a client-side
    percentile computed over raw samples. buckets maps an upper boundary to a
    cumulative count.
    """
    finite = []
    inf_count = None
    for le, c in buckets.items():
        if le in ("+Inf", "Inf", "inf"):
            inf_count = c
            continue
        try:
            finite.append((float(le), float(c)))
        except ValueError:
            continue
    if not finite:
        return float("nan")
    finite.sort()
    total = inf_count if inf_count is not None else finite[-1][1]
    if not total or total <= 0:
        return float("nan")
    rank = q * total
    prev_bound, prev_count = 0.0, 0.0
    for bound, count in finite:
        if count >= rank:
            if count == prev_count:
                return bound
            frac = (rank - prev_count) / (count - prev_count)
            return prev_bound + frac * (bound - prev_bound)
        prev_bound, prev_count = bound, count
    return finite[-1][0]


def hist_delta(start_entry, end_entry):
    out = {}
    sb = start_entry.get("buckets", {})
    for le, c in end_entry.get("buckets", {}).items():
        out[le] = float(c) - float(sb.get(le, 0.0))
    return {
        "buckets": out,
        "count": float(end_entry.get("count", 0.0)) - float(start_entry.get("count", 0.0)),
        "sum": float(end_entry.get("sum", 0.0)) - float(start_entry.get("sum", 0.0)),
    }


OBSERVABILITY_PATHS = ("/actuator", "/health", "/metrics", "/prometheus")


def is_observability_series(series_key):
    """True when a histogram series describes probe or scrape traffic.

    Only works where the exposition carries a path label, which Micrometer does
    and the Vapor collector does not.
    """
    m = re.search(r'uri="([^"]*)"', series_key)
    if not m:
        return False
    uri = m.group(1)
    return any(uri.startswith(p) for p in OBSERVABILITY_PATHS)


def subtract_probe_traffic(merged, probe_csv, t_start, t_end, column="latency_ms"):
    """Remove this run's health-probe samples from a merged histogram."""
    if not os.path.exists(probe_csv):
        return
    lats = []
    with open(probe_csv) as fh:
        for r in csv.DictReader(fh):
            t = fnum(r.get("t"))
            v = fnum(r.get(column))
            if v is None:
                continue
            if t_start is not None and t is not None and not (t_start <= t <= t_end):
                continue
            lats.append(v / 1000.0)
    if not lats:
        return
    arr = np.asarray(lats, dtype=float)
    for le in list(merged["buckets"].keys()):
        if le in ("+Inf", "Inf", "inf"):
            merged["buckets"][le] = max(0.0, merged["buckets"][le] - arr.size)
            continue
        try:
            bound = float(le)
        except ValueError:
            continue
        n_below = int(np.count_nonzero(arr <= bound))
        merged["buckets"][le] = max(0.0, merged["buckets"][le] - n_below)
    merged["count"] = max(0.0, merged["count"] - arr.size)
    merged["sum"] = max(0.0, merged["sum"] - float(arr.sum()))


def read_csv_rows(path):
    if not os.path.exists(path):
        return []
    with open(path) as fh:
        return list(csv.DictReader(fh))


def fnum(x):
    try:
        v = float(x)
        return v if not math.isnan(v) else None
    except (TypeError, ValueError):
        return None


def steady_slice(ts, vals):
    """Middle half of the window, used as the steady-state estimate."""
    if not ts:
        return []
    t0, t1 = min(ts), max(ts)
    span = t1 - t0
    if span <= 0:
        return vals
    lo, hi = t0 + 0.25 * span, t0 + 0.75 * span
    return [v for t, v in zip(ts, vals) if lo <= t <= hi]


# ----------------------------------------------------------------- per run

def k6_metric(summary, name, key):
    m = (summary.get("metrics") or {}).get(name)
    if not m:
        return None
    vals = m.get("values", m)
    return fnum(vals.get(key))


def load_run(meta_path):
    with open(meta_path) as fh:
        meta = json.load(fh)
    run_id = meta["run_id"]
    base = os.path.join(RESULTS, run_id)
    row = {
        "run_id": run_id, "config": meta["config"], "scenario": meta["scenario"],
        "repetition": meta["repetition"], "target": meta["target"],
        "k6_returncode": meta.get("k6_returncode"),
        "k6_wall_seconds": meta.get("k6_wall_seconds"),
        "finished_iso": meta.get("finished_iso"),
    }

    # ---- client side, measured by the load generator
    sp = base + "_k6summary.json"
    if os.path.exists(sp):
        with open(sp) as fh:
            summ = json.load(fh)
        row["client_p50_ms"] = k6_metric(summ, "sut_request_duration", "med")
        row["client_p95_ms"] = k6_metric(summ, "sut_request_duration", "p(95)")
        row["client_p99_ms"] = k6_metric(summ, "sut_request_duration", "p(99)")
        row["client_avg_ms"] = k6_metric(summ, "sut_request_duration", "avg")
        row["client_max_ms"] = k6_metric(summ, "sut_request_duration", "max")
        row["requests_total"] = k6_metric(summ, "sut_requests_total", "count")
        row["throughput_rps"] = k6_metric(summ, "sut_requests_total", "rate")
        row["error_rate"] = k6_metric(summ, "sut_error_rate", "rate")
        # In a k6 Rate metric, "passes" counts the additions that were true.
        # The metric records true when a response was an error, so the number
        # of failed requests is "passes", not "fails".
        row["error_count"] = k6_metric(summ, "sut_error_rate", "passes")
        row["iterations"] = k6_metric(summ, "iterations", "count")
        row["vus_max"] = k6_metric(summ, "vus_max", "max") or k6_metric(summ, "vus_max", "value")
        for ep in ("ep_get_users", "ep_get_products", "ep_post_users", "ep_post_orders"):
            row[ep + "_p95_ms"] = k6_metric(summ, ep, "p(95)")
            row[ep + "_med_ms"] = k6_metric(summ, ep, "med")
            row[ep + "_count"] = k6_metric(summ, ep, "count")

    # ---- server side, from the histogram delta over the measured window
    hp = base + "_histograms.json"
    if os.path.exists(hp):
        with open(hp) as fh:
            hj = json.load(fh)
        row["window_seconds"] = hj.get("window_seconds")
        merged = {}
        for svc, end in (hj.get("end") or {}).items():
            start = (hj.get("start") or {}).get(svc, {"hist": {}})
            for series, e_entry in (end.get("hist") or {}).items():
                # Observability traffic is not application traffic. The health
                # probe and the metric scrape both pass through the same
                # instrumentation as a real request, and both are far faster
                # than one, so leaving them in pulls every server-side
                # percentile down. Where the exposition carries a path label
                # they are excluded here by name.
                if is_observability_series(series):
                    continue
                s_entry = (start.get("hist") or {}).get(series, {"buckets": {}, "count": 0, "sum": 0})
                d = hist_delta(s_entry, e_entry)
                if d["count"] <= 0:
                    continue
                for le, c in d["buckets"].items():
                    merged.setdefault("buckets", {})
                    merged["buckets"][le] = merged["buckets"].get(le, 0.0) + c
                merged["count"] = merged.get("count", 0.0) + d["count"]
                merged["sum"] = merged.get("sum", 0.0) + d["sum"]
        # No subtraction is applied to the Vapor histogram. Its middleware
        # already skips /health and /metrics before recording, so probe and
        # scrape traffic never enters it, and subtracting the probe latencies
        # removed roughly fifteen hundred samples per run that were never
        # there. The two stacks are symmetric in this respect: one excludes the
        # observability endpoints in the middleware, the other by uri label.

        # A scrape can fail exactly when it matters most. Under saturation the
        # metrics endpoint queues behind the same busy threads as the workload,
        # and a snapshot that times out leaves a histogram delta far smaller
        # than the number of requests the client actually sent. Such a run has
        # no usable server-side percentile, and including it would let a
        # near-empty histogram set the median for a whole cell.
        client_n = row.get("requests_total") or 0
        server_n = merged.get("count") or 0
        if client_n and server_n < 0.5 * client_n:
            row["server_metrics_incomplete"] = 1
            merged = {}
        else:
            row["server_metrics_incomplete"] = 0

        if merged.get("count") and merged["count"] > 0:
            row["server_p50_ms"] = prom_quantile(merged["buckets"], 0.50) * 1000.0
            row["server_p95_ms"] = prom_quantile(merged["buckets"], 0.95) * 1000.0
            row["server_p99_ms"] = prom_quantile(merged["buckets"], 0.99) * 1000.0
            row["server_mean_ms"] = (merged["sum"] / merged["count"]) * 1000.0
            row["server_request_count"] = merged["count"]

    # ---- container resources
    res = read_csv_rows(base + "_resources.csv")
    by_c = defaultdict(lambda: {"t": [], "cpu": [], "mem": []})
    for r in res:
        name = r["container"]
        if not (name.startswith("swift-") or name.startswith("java-")):
            continue
        t, cpu, mem = fnum(r["t"]), fnum(r["cpu_percent_of_one_core"]), fnum(r["mem_bytes"])
        if t is None:
            continue
        by_c[name]["t"].append(t)
        if cpu is not None:
            by_c[name]["cpu"].append(cpu)
        if mem is not None:
            by_c[name]["mem"].append(mem)
    cpu_all, mem_peak_all, mem_steady_all = [], [], []
    for name, d in by_c.items():
        if d["cpu"]:
            cpu_all.append(float(np.mean(d["cpu"])))
        if d["mem"]:
            mem_peak_all.append(float(np.max(d["mem"])))
            st = steady_slice(d["t"][:len(d["mem"])], d["mem"])
            mem_steady_all.append(float(np.median(st)) if st else float(np.median(d["mem"])))
    # Summed over the three services of the stack: the stack is what is deployed.
    row["rss_peak_bytes"] = float(np.sum(mem_peak_all)) if mem_peak_all else None
    row["rss_steady_bytes"] = float(np.sum(mem_steady_all)) if mem_steady_all else None
    row["cpu_mean_percent_of_one_core"] = float(np.sum(cpu_all)) if cpu_all else None
    row["cpu_quota_percent"] = 450.0  # three containers at 1.5 cores each

    # ---- load generator cost, disclosed rather than assumed negligible
    lg = read_csv_rows(base + "_loadgen.csv")
    lc = [fnum(r["k6_cpu_percent_of_one_core"]) for r in lg]
    lr = [fnum(r["k6_rss_bytes"]) for r in lg]
    lc = [v for v in lc if v is not None]
    lr = [v for v in lr if v is not None]
    row["k6_cpu_mean_percent_of_one_core"] = float(np.mean(lc)) if lc else None
    row["k6_cpu_peak_percent_of_one_core"] = float(np.max(lc)) if lc else None
    row["k6_rss_peak_bytes"] = float(np.max(lr)) if lr else None

    # ---- JVM and pool internals
    sm = read_csv_rows(base + "_server_metrics.csv")
    series = defaultdict(lambda: {"t": [], "v": []})
    heap_used = defaultdict(float)
    heap_comm = defaultdict(float)
    for r in sm:
        name, labels, t, v = r["metric"], r["labels"], fnum(r["t"]), fnum(r["value"])
        if t is None or v is None:
            continue
        if name in ("jvm_memory_used_bytes", "jvm_memory_committed_bytes"):
            if 'area="heap"' not in labels:
                continue
            key = (r["service"], round(t, 1))
            if name == "jvm_memory_used_bytes":
                heap_used[key] += v
            else:
                heap_comm[key] += v
            continue
        # When Tomcat runs on a virtual thread executor there is no bounded
        # pool, and the MBean reports -1 for every pool gauge. That is a real
        # signal that virtual threads are active, but it is not a measurement,
        # so it must not reach a table as if it were one.
        if name.startswith("tomcat_threads") and v < 0:
            continue
        series[name]["t"].append(t)
        series[name]["v"].append(v)

    def agg(name, how="median", steady=False):
        d = series.get(name)
        if not d or not d["v"]:
            return None
        vals = steady_slice(d["t"], d["v"]) if steady else d["v"]
        if not vals:
            return None
        if how == "median":
            return float(np.median(vals))
        if how == "max":
            return float(np.max(vals))
        if how == "delta":
            return float(np.max(vals) - np.min(vals))
        return None

    if heap_used:
        hv = list(heap_used.values())
        row["jvm_heap_used_steady_bytes"] = float(np.median(hv))
        row["jvm_heap_used_peak_bytes"] = float(np.max(hv))
    if heap_comm:
        cv = list(heap_comm.values())
        row["jvm_heap_committed_steady_bytes"] = float(np.median(cv))
        row["jvm_heap_committed_peak_bytes"] = float(np.max(cv))

    row["gc_pause_count"] = agg("jvm_gc_pause_seconds_count", "delta")
    row["gc_pause_total_seconds"] = agg("jvm_gc_pause_seconds_sum", "delta")
    row["tomcat_busy_threads_median"] = agg("tomcat_threads_busy_threads", "median", steady=True)
    row["tomcat_busy_threads_peak"] = agg("tomcat_threads_busy_threads", "max")
    row["tomcat_threads_max_config"] = agg("tomcat_threads_config_max_threads", "median")
    row["db_pool_pending_median"] = agg("hikaricp_connections_pending", "median", steady=True)
    row["db_pool_pending_peak"] = agg("hikaricp_connections_pending", "max")
    row["db_pool_active_peak"] = agg("hikaricp_connections_active", "max")
    acq_n = agg("hikaricp_connections_acquire_seconds_count", "delta")
    acq_s = agg("hikaricp_connections_acquire_seconds_sum", "delta")
    row["db_wait_mean_ms"] = (acq_s / acq_n * 1000.0) if acq_n else None
    row["swift_rss_internal_bytes"] = agg("process_resident_memory_bytes", "max")

    # ---- control-plane responsiveness, identical instrumentation on both stacks
    pr = read_csv_rows(base + "_health_probe.csv")
    lat = [fnum(r["latency_ms"]) for r in pr if r.get("status") == "200"]
    lat = [v for v in lat if v is not None]
    if lat:
        row["probe_p50_ms"] = float(np.percentile(lat, 50))
        row["probe_p95_ms"] = float(np.percentile(lat, 95))
        row["probe_p99_ms"] = float(np.percentile(lat, 99))
    row["probe_samples"] = len(pr)
    row["probe_failures"] = sum(1 for r in pr if r.get("status") != "200")

    # ---- throughput over time, for the saturation analysis
    th = read_csv_rows(base + "_throughput.csv")
    per_t = defaultdict(float)
    for r in th:
        t, c = fnum(r["t"]), fnum(r["cumulative_count"])
        if t is None or c is None:
            continue
        per_t[round(t, 0)] += c
    ts = sorted(per_t)
    rates = []
    for i in range(1, len(ts)):
        dt = ts[i] - ts[i - 1]
        dc = per_t[ts[i]] - per_t[ts[i - 1]]
        if dt > 0 and dc >= 0:
            rates.append((ts[i], dc / dt))
    if rates:
        rv = [r for _, r in rates]
        row["server_throughput_peak_rps"] = float(np.max(rv))
        row["server_throughput_p90_rps"] = float(np.percentile(rv, 90))
    row["_throughput_series"] = rates
    return row


# ----------------------------------------------------------------- reporting

NUMERIC_METRICS = [
    "client_p50_ms", "client_p95_ms", "client_p99_ms", "client_max_ms",
    "server_p50_ms", "server_p95_ms", "server_p99_ms", "server_mean_ms",
    "throughput_rps", "requests_total", "error_rate",
    "rss_peak_bytes", "rss_steady_bytes", "cpu_mean_percent_of_one_core",
    "jvm_heap_used_steady_bytes", "jvm_heap_used_peak_bytes",
    "jvm_heap_committed_steady_bytes", "jvm_heap_committed_peak_bytes",
    "gc_pause_count", "gc_pause_total_seconds",
    "tomcat_busy_threads_median", "tomcat_busy_threads_peak", "tomcat_threads_max_config",
    "db_pool_pending_median", "db_pool_pending_peak", "db_pool_active_peak", "db_wait_mean_ms",
    "probe_p50_ms", "probe_p95_ms", "probe_p99_ms",
    "k6_cpu_mean_percent_of_one_core", "k6_cpu_peak_percent_of_one_core", "k6_rss_peak_bytes",
    "server_throughput_peak_rps", "ep_get_users_p95_ms", "ep_get_products_p95_ms",
    "ep_post_users_p95_ms", "ep_post_orders_p95_ms",
]


def main():
    os.makedirs(OUT, exist_ok=True)
    metas = sorted(glob.glob(os.path.join(RESULTS, "*_meta.json")))
    if not metas:
        print("no runs found in", RESULTS)
        return 1
    rows = [load_run(m) for m in metas]
    print(f"loaded {len(rows)} runs")

    series_by_run = {r["run_id"]: r.pop("_throughput_series", []) for r in rows}

    incomplete = [r["run_id"] for r in rows if r.get("server_metrics_incomplete")]
    if incomplete:
        print(f"server-side metrics incomplete in {len(incomplete)} run(s), "
              f"client-side data retained: {', '.join(incomplete[:6])}"
              + (" ..." if len(incomplete) > 6 else ""))

    fields = ["run_id", "config", "scenario", "repetition", "target", "k6_returncode",
              "server_metrics_incomplete",
              "k6_wall_seconds", "window_seconds", "finished_iso", "iterations", "vus_max",
              "error_count", "server_request_count", "probe_samples", "probe_failures",
              "cpu_quota_percent", "tomcat_threads_max_config", "db_pool_active_peak",
              "swift_rss_internal_bytes", "server_throughput_p90_rps"] + NUMERIC_METRICS
    fields = list(dict.fromkeys(fields))
    with open(os.path.join(OUT, "runs_long.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in sorted(rows, key=lambda x: (x["scenario"], x["config"], x["repetition"])):
            w.writerow(r)

    grouped = defaultdict(list)
    for r in rows:
        grouped[(r["config"], r["scenario"])].append(r)

    with open(os.path.join(OUT, "aggregate.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["scenario", "config", "config_label", "metric", "n",
                    "median", "iqr", "q1", "q3", "ci95_low", "ci95_high"])
        for scen in SCEN_ORDER:
            for cfg in CONFIG_ORDER:
                g = grouped.get((cfg, scen), [])
                if not g:
                    continue
                for m in NUMERIC_METRICS:
                    med, iqr, q1, q3, lo, hi, n = med_iqr_ci([x.get(m) for x in g])
                    if n == 0:
                        continue
                    w.writerow([scen, cfg, CONFIG_LABEL[cfg], m, n,
                                f"{med:.4f}", f"{iqr:.4f}", f"{q1:.4f}", f"{q3:.4f}",
                                f"{lo:.4f}", f"{hi:.4f}"])

    with open(os.path.join(OUT, "significance.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["scenario", "metric", "config_a", "config_b", "n_a", "n_b",
                    "median_a", "median_b", "U", "p_value", "rank_biserial",
                    "vargha_delaney_a12", "significant_at_0.05", "direction"])
        for scen in SCEN_ORDER:
            for m in ["client_p95_ms", "client_p99_ms", "server_p95_ms",
                      "throughput_rps", "rss_steady_bytes", "rss_peak_bytes",
                      "error_rate", "probe_p95_ms"]:
                a_rows = grouped.get(("vapor", scen), [])
                a = [x.get(m) for x in a_rows]
                for cfg in CONFIG_ORDER[1:]:
                    b_rows = grouped.get((cfg, scen), [])
                    if not a_rows or not b_rows:
                        continue
                    b = [x.get(m) for x in b_rows]
                    u, p, rbc, na, nb = mannwhitney(a, b)
                    ma = med_iqr_ci(a)[0]
                    mb = med_iqr_ci(b)[0]
                    if math.isnan(p):
                        direction = "insufficient data"
                    elif math.isnan(ma) or math.isnan(mb):
                        direction = "insufficient data"
                    else:
                        direction = "vapor lower" if ma < mb else ("vapor higher" if ma > mb else "equal")
                    w.writerow([scen, m, "vapor", cfg, na, nb,
                                f"{ma:.4f}", f"{mb:.4f}",
                                "" if math.isnan(u) else f"{u:.1f}",
                                "" if math.isnan(p) else f"{p:.5f}",
                                "" if math.isnan(rbc) else f"{rbc:.3f}",
                                "" if math.isnan(rbc) else f"{vargha_delaney_a12(rbc):.3f}",
                                "" if math.isnan(p) else ("yes" if p < 0.05 else "no"),
                                direction])

    # Memory quantities kept strictly apart, so no ratio compares unlike things.
    with open(os.path.join(OUT, "memory.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["scenario", "config", "quantity", "definition", "n", "median_mb", "iqr_mb",
                    "ci95_low_mb", "ci95_high_mb"])
        QUANT = [
            ("rss_steady_bytes", "Resident set size, steady state, summed over the three service containers, from docker stats"),
            ("rss_peak_bytes", "Resident set size, peak, summed over the three service containers, from docker stats"),
            ("jvm_heap_used_steady_bytes", "JVM used heap, steady state, summed over the three services (JVM only)"),
            ("jvm_heap_used_peak_bytes", "JVM used heap, peak, summed over the three services (JVM only)"),
            ("jvm_heap_committed_steady_bytes", "JVM committed heap, steady state, summed over the three services (JVM only)"),
            ("jvm_heap_committed_peak_bytes", "JVM committed heap, peak, summed over the three services (JVM only)"),
        ]
        for scen in SCEN_ORDER:
            for cfg in CONFIG_ORDER:
                g = grouped.get((cfg, scen), [])
                if not g:
                    continue
                for key, definition in QUANT:
                    med, iqr, q1, q3, lo, hi, n = med_iqr_ci([x.get(key) for x in g])
                    if n == 0 or math.isnan(med):
                        continue
                    MB = 1024.0 * 1024.0
                    w.writerow([scen, cfg, key, definition, n,
                                f"{med/MB:.1f}", f"{iqr/MB:.1f}",
                                f"{lo/MB:.1f}", f"{hi/MB:.1f}"])

    with open(os.path.join(OUT, "diagnostics.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["scenario", "config", "metric", "n", "median", "iqr", "note"])
        DIAG = [
            ("cpu_mean_percent_of_one_core", "Mean CPU, percent of one core, summed over the three containers; the quota is 450"),
            ("gc_pause_count", "Garbage-collection pauses during the window (JVM only)"),
            ("gc_pause_total_seconds", "Total garbage-collection pause time in seconds (JVM only)"),
            ("tomcat_busy_threads_median", "Busy Tomcat threads, steady state (JVM only)"),
            ("tomcat_busy_threads_peak", "Busy Tomcat threads, peak (JVM only)"),
            ("db_pool_pending_median", "Threads waiting for a database connection, steady state (JVM only)"),
            ("db_pool_pending_peak", "Threads waiting for a database connection, peak (JVM only)"),
            ("db_wait_mean_ms", "Mean time to acquire a database connection, milliseconds (JVM only)"),
            ("probe_p50_ms", "Control-plane probe median, identical instrumentation on both stacks"),
            ("probe_p95_ms", "Control-plane probe 95th percentile, identical instrumentation on both stacks"),
            ("probe_p99_ms", "Control-plane probe 99th percentile, identical instrumentation on both stacks"),
        ]
        for scen in SCEN_ORDER:
            for cfg in CONFIG_ORDER:
                g = grouped.get((cfg, scen), [])
                if not g:
                    continue
                for key, note in DIAG:
                    med, iqr, q1, q3, lo, hi, n = med_iqr_ci([x.get(key) for x in g])
                    if n == 0 or math.isnan(med):
                        continue
                    w.writerow([scen, cfg, key, n, f"{med:.4f}", f"{iqr:.4f}", note])

    with open(os.path.join(OUT, "client_vs_server.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["scenario", "config", "n", "client_p95_ms_median", "server_p95_ms_median",
                    "difference_ms", "ratio_client_over_server",
                    "client_requests_median", "server_requests_median",
                    "server_minus_client", "probe_samples_median"])
        for scen in SCEN_ORDER:
            for cfg in CONFIG_ORDER:
                g = grouped.get((cfg, scen), [])
                if not g:
                    continue
                c = med_iqr_ci([x.get("client_p95_ms") for x in g])[0]
                s = med_iqr_ci([x.get("server_p95_ms") for x in g])[0]
                if math.isnan(c) or math.isnan(s):
                    continue
                cr = med_iqr_ci([x.get("requests_total") for x in g])[0]
                sr = med_iqr_ci([x.get("server_request_count") for x in g])[0]
                pr = med_iqr_ci([float(x.get("probe_samples") or 0) for x in g])[0]
                w.writerow([scen, cfg, len(g), f"{c:.2f}", f"{s:.2f}",
                            f"{c - s:.2f}", f"{(c/s if s else float('nan')):.2f}",
                            "" if math.isnan(cr) else f"{cr:.0f}",
                            "" if math.isnan(sr) else f"{sr:.0f}",
                            "" if (math.isnan(cr) or math.isnan(sr)) else f"{sr - cr:.0f}",
                            "" if math.isnan(pr) else f"{pr:.0f}"])

    with open(os.path.join(OUT, "endpoint_level.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["scenario", "config", "endpoint", "n", "p95_ms_median", "p95_ms_iqr",
                    "median_ms_median", "requests_median"])
        EPS = [("ep_get_users", "GET /users"), ("ep_get_products", "GET /products"),
               ("ep_post_users", "POST /users"), ("ep_post_orders", "POST /orders")]
        for scen in SCEN_ORDER:
            for cfg in CONFIG_ORDER:
                g = grouped.get((cfg, scen), [])
                if not g:
                    continue
                for key, label in EPS:
                    med, iqr, *_rest, n = med_iqr_ci([x.get(key + "_p95_ms") for x in g])
                    if n == 0 or math.isnan(med):
                        continue
                    m2 = med_iqr_ci([x.get(key + "_med_ms") for x in g])[0]
                    cnt = med_iqr_ci([x.get(key + "_count") for x in g])[0]
                    w.writerow([scen, cfg, label, n, f"{med:.2f}", f"{iqr:.2f}",
                                f"{m2:.2f}", f"{cnt:.0f}"])

    with open(os.path.join(OUT, "throughput_saturation.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["scenario", "config", "n", "peak_server_rps_median",
                    "client_rps_median", "error_rate_median",
                    "saturated", "note"])
        for scen in SCEN_ORDER:
            for cfg in CONFIG_ORDER:
                g = grouped.get((cfg, scen), [])
                if not g:
                    continue
                pk = med_iqr_ci([x.get("server_throughput_peak_rps") for x in g])[0]
                cr = med_iqr_ci([x.get("throughput_rps") for x in g])[0]
                er = med_iqr_ci([x.get("error_rate") for x in g])[0]
                sat = "yes" if (not math.isnan(er) and er > 0.01) else "no"
                note = ("errors exceed one percent, so offered load is beyond what the "
                        "configuration sustains") if sat == "yes" else "error rate at or below one percent"
                w.writerow([scen, cfg, len(g),
                            "" if math.isnan(pk) else f"{pk:.1f}",
                            "" if math.isnan(cr) else f"{cr:.1f}",
                            "" if math.isnan(er) else f"{er:.5f}", sat, note])

    with open(os.path.join(OUT, "throughput_timeseries.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["run_id", "config", "scenario", "repetition", "seconds_into_window", "server_rps"])
        for r in rows:
            ser = series_by_run.get(r["run_id"], [])
            if not ser:
                continue
            t0 = ser[0][0]
            for t, rate in ser:
                w.writerow([r["run_id"], r["config"], r["scenario"], r["repetition"],
                            f"{t - t0:.0f}", f"{rate:.2f}"])

    write_summary(rows, grouped)
    print("analysis written to", OUT)
    return 0


def write_summary(rows, grouped):
    lines = ["# Revision 3 measurement summary", ""]
    lines.append(f"Runs analysed: {len(rows)}")
    by_cfg = defaultdict(int)
    for r in rows:
        by_cfg[(r["config"], r["scenario"])] += 1
    lines.append("")
    lines.append("## Completed repetitions")
    lines.append("")
    lines.append("| scenario | " + " | ".join(CONFIG_LABEL[c] for c in CONFIG_ORDER) + " |")
    lines.append("|---" * (len(CONFIG_ORDER) + 1) + "|")
    for scen in SCEN_ORDER:
        lines.append("| " + scen + " | " + " | ".join(str(by_cfg.get((c, scen), 0)) for c in CONFIG_ORDER) + " |")

    lines += ["", "## Tail latency, client measured, milliseconds", "",
              "| scenario | config | n | median P95 | IQR | 95% CI of median |",
              "|---|---|---|---|---|---|"]
    for scen in SCEN_ORDER:
        for cfg in CONFIG_ORDER:
            g = grouped.get((cfg, scen), [])
            if not g:
                continue
            med, iqr, q1, q3, lo, hi, n = med_iqr_ci([x.get("client_p95_ms") for x in g])
            if n == 0 or math.isnan(med):
                continue
            lines.append(f"| {scen} | {CONFIG_LABEL[cfg]} | {n} | {med:.1f} | {iqr:.1f} | [{lo:.1f}, {hi:.1f}] |")

    lines += ["", "## Load generator cost on the shared host", "",
              "| scenario | config | mean k6 CPU, percent of one core | peak | peak RSS MB |",
              "|---|---|---|---|---|"]
    for scen in SCEN_ORDER:
        for cfg in CONFIG_ORDER:
            g = grouped.get((cfg, scen), [])
            if not g:
                continue
            a = med_iqr_ci([x.get("k6_cpu_mean_percent_of_one_core") for x in g])[0]
            b = med_iqr_ci([x.get("k6_cpu_peak_percent_of_one_core") for x in g])[0]
            c = med_iqr_ci([x.get("k6_rss_peak_bytes") for x in g])[0]
            if math.isnan(a):
                continue
            lines.append(f"| {scen} | {CONFIG_LABEL[cfg]} | {a:.0f} | {b:.0f} | {c/1048576:.0f} |")

    with open(os.path.join(OUT, "SUMMARY.md"), "w") as fh:
        fh.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    sys.exit(main())
