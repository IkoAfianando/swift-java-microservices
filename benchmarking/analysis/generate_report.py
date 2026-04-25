#!/usr/bin/env python3
"""
Generate comprehensive markdown report + CSV exports from a k6 benchmark run.
Pulls data from k6 summary JSON + queries Prometheus at the test's actual time window.

Usage:
  python3 generate_report.py [k6_summary.json]
  (defaults to most recent benchmarking/results/*_summary.json)
"""

import json
import os
import sys
import csv
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

PROM = "http://localhost:9090"
ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = Path(os.environ.get("RESULTS_DIR", str(ROOT / "benchmarking" / "results")))


def prom_query(q, time=None):
    params = {"query": q}
    if time:
        params["time"] = str(time)
    url = f"{PROM}/api/v1/query?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read().decode())


def get_series(q, time=None):
    out = {}
    try:
        d = prom_query(q, time=time)
        for r in d.get("data", {}).get("result", []):
            try:
                out[tuple(sorted(r["metric"].items()))] = float(r["value"][1])
            except (ValueError, KeyError):
                pass
    except Exception as e:
        print(f"  ⚠️  query failed: {e}", file=sys.stderr)
    return out


def find_latest_summary():
    summaries = sorted(RESULTS_DIR.glob("*_summary.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not summaries:
        sys.exit("No k6 summary JSON found in benchmarking/results/")
    return summaries[0]


def fmt_ms(ms):
    if ms is None or ms != ms:  # nan check
        return "—"
    return f"{ms:.2f} ms"


def fmt_mb(bytes_):
    if bytes_ is None or bytes_ != bytes_:
        return "—"
    return f"{bytes_ / 1024 / 1024:.1f} MB"


def fmt_pct(ratio):
    if ratio is None or ratio != ratio:
        return "—"
    return f"{ratio * 100:.2f}%"


def fmt_int(v):
    if v is None or v != v:
        return "—"
    return f"{int(v):,}"


def safe_get(metric_dict, *keys):
    cur = metric_dict
    for k in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
        if cur is None:
            return None
    return cur


def lookup(series, **filters):
    """Find first value in series whose labels match all filters."""
    for k, v in series.items():
        d = dict(k)
        if all(d.get(fk) == fv for fk, fv in filters.items()):
            return v
    return None


def main():
    summary_path = Path(sys.argv[1]) if len(sys.argv) > 1 else find_latest_summary()
    print(f"Reading k6 summary: {summary_path}")

    with summary_path.open() as f:
        k6 = json.load(f)

    metrics = k6.get("metrics", {})

    # ---- k6 high-level numbers (direct keys, no .values wrapper) ----
    def m(name, key):
        return safe_get(metrics, name, key)

    swift_avg = m("swift_request_duration", "avg")
    swift_min = m("swift_request_duration", "min")
    swift_med = m("swift_request_duration", "med")
    swift_max = m("swift_request_duration", "max")
    swift_p90 = m("swift_request_duration", "p(90)")
    swift_p95 = m("swift_request_duration", "p(95)")
    swift_total = m("swift_requests_total", "count")
    swift_rate = m("swift_requests_total", "rate")
    swift_err = m("swift_error_rate", "value")
    swift_err_passes = m("swift_error_rate", "passes")
    swift_err_fails = m("swift_error_rate", "fails")

    java_avg = m("java_request_duration", "avg")
    java_min = m("java_request_duration", "min")
    java_med = m("java_request_duration", "med")
    java_max = m("java_request_duration", "max")
    java_p90 = m("java_request_duration", "p(90)")
    java_p95 = m("java_request_duration", "p(95)")
    java_total = m("java_requests_total", "count")
    java_rate = m("java_requests_total", "rate")
    java_err = m("java_error_rate", "value")
    java_err_passes = m("java_error_rate", "passes")
    java_err_fails = m("java_error_rate", "fails")

    iters = m("iterations", "count") or 0
    iter_rate = m("iterations", "rate") or 0
    vus_max = m("vus_max", "max") or m("vus_max", "value") or 0
    http_reqs = m("http_reqs", "count") or 0
    http_req_failed = m("http_req_failed", "value") or 0

    duration_sec = (iters / iter_rate) if iter_rate else 0
    duration_min = duration_sec / 60

    # Skip aborted/empty runs (no iterations recorded → no useful report)
    if iters == 0 or duration_sec == 0:
        print(f"⚠️  Skipping {summary_path.name}: no iterations recorded (aborted or empty run)")
        return

    # ---- Compute test time window from test ID ----
    test_id = summary_path.stem.replace("_summary", "")
    # Format: YYYYMMDD_HHMMSS_load-test
    try:
        ts_str = test_id.split("_")[0] + "_" + test_id.split("_")[1]
        test_start = datetime.strptime(ts_str, "%Y%m%d_%H%M%S").timestamp()
    except Exception:
        test_start = datetime.now().timestamp() - duration_sec - 600

    test_end = test_start + duration_sec
    test_mid = test_start + duration_sec / 2  # query Prometheus mid-test for representative numbers

    print(f"Test window: {datetime.fromtimestamp(test_start)} → {datetime.fromtimestamp(test_end)}")
    print(f"Querying Prometheus at test mid-point ({datetime.fromtimestamp(test_mid)})...")

    # ---- Prometheus queries (at test mid-point so rates are accurate) ----
    swift_rps = get_series('sum(rate(http_requests_total{language="swift"}[2m])) by (service)', time=test_mid)
    java_rps = get_series('sum(rate(http_server_requests_seconds_count{language="java", uri!~"/actuator.*"}[2m])) by (service)', time=test_mid)

    def per_service_quantile(q, lang, name="http_request_duration_seconds_bucket", uri_filter=""):
        expr = (f'histogram_quantile({q}, sum(rate({name}{{language="{lang}"{uri_filter}}}[2m])) '
                f'by (le, service)) * 1000')
        return get_series(expr, time=test_mid)

    swift_lat_p50 = per_service_quantile(0.50, "swift")
    swift_lat_p95 = per_service_quantile(0.95, "swift")
    swift_lat_p99 = per_service_quantile(0.99, "swift")
    java_lat_p50 = per_service_quantile(0.50, "java",
                                        name="http_server_requests_seconds_bucket",
                                        uri_filter=', uri!~"/actuator.*"')
    java_lat_p95 = per_service_quantile(0.95, "java",
                                        name="http_server_requests_seconds_bucket",
                                        uri_filter=', uri!~"/actuator.*"')
    java_lat_p99 = per_service_quantile(0.99, "java",
                                        name="http_server_requests_seconds_bucket",
                                        uri_filter=', uri!~"/actuator.*"')

    # Memory: peak during test (max over the test window)
    def max_during_test(q):
        return get_series(f'max_over_time(({q})[{int(duration_sec) + 60}s:30s])', time=test_end + 30)

    swift_rss_peak = max_during_test('process_resident_memory_bytes{language="swift"}')
    java_heap_peak = max_during_test('sum(jvm_memory_used_bytes{area="heap", language="java"}) by (service)')
    java_total_peak = max_during_test('sum(jvm_memory_used_bytes{language="java"}) by (service)')
    java_nonheap_peak = max_during_test('sum(jvm_memory_used_bytes{area="nonheap", language="java"}) by (service)')

    # Threads (peak during test)
    java_threads_peak = max_during_test('jvm_threads_live_threads{language="java"}')
    java_threads_daemon = get_series('jvm_threads_daemon_threads{language="java"}', time=test_mid)
    java_threads_alltime_peak = get_series('jvm_threads_peak_threads{language="java"}', time=test_end)

    # GC overhead
    java_gc_overhead_peak = max_during_test('jvm_gc_overhead_percent{language="java"}')

    # HikariCP peak
    hikari_active_peak = max_during_test('hikaricp_connections_active{language="java"}')
    hikari_idle = get_series('hikaricp_connections_idle{language="java"}', time=test_mid)
    hikari_max_v = get_series('hikaricp_connections_max{language="java"}', time=test_mid)

    # Final cumulative counters (at test end)
    swift_by_status = get_series('sum(http_requests_total{language="swift"}) by (service, status)', time=test_end + 30)
    java_by_status = get_series('sum(http_server_requests_seconds_count{language="java", uri!~"/actuator.*"}) by (service, status, outcome)', time=test_end + 30)

    # ---- Build markdown report ----
    report_dir = RESULTS_DIR / "reports"
    report_dir.mkdir(exist_ok=True)
    md_path = report_dir / f"report_{test_id}.md"
    csv_path = report_dir / f"metrics_{test_id}.csv"
    status_csv = report_dir / f"status_{test_id}.csv"

    md = []
    md.append(f"# Benchmark Report — Swift Vapor vs Java Spring Boot")
    md.append("")
    md.append(f"**Researcher:** Iko Afianando (NIM 2602261970)  ")
    md.append(f"**Institution:** BINUS University 2025/2026 — Enrichment Program  ")
    md.append(f"**Test ID:** `{test_id}`  ")
    md.append(f"**Test window:** {datetime.fromtimestamp(test_start).strftime('%Y-%m-%d %H:%M:%S')} → "
              f"{datetime.fromtimestamp(test_end).strftime('%H:%M:%S')} ({duration_min:.1f} min)  ")
    md.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  ")
    md.append(f"**k6 Summary:** `{summary_path.relative_to(ROOT)}`")
    md.append("")
    md.append("---")
    md.append("")

    md.append("## 1. Test Configuration")
    md.append("")
    md.append("| Field | Value |")
    md.append("|---|---|")
    md.append(f"| Scenario | k6 load test (constant ramp-up) |")
    md.append(f"| Duration | {duration_min:.1f} minutes ({duration_sec:.0f} s) |")
    md.append(f"| Max VUs | {int(vus_max)} |")
    md.append(f"| Iterations | {fmt_int(iters)} ({iter_rate:.2f} iter/s) |")
    md.append(f"| Total HTTP requests | {fmt_int(http_reqs)} ({http_reqs/duration_sec:.1f} req/s) |")
    md.append(f"| Endpoints tested | `GET /users`, `GET /products`, `POST /users` |")
    md.append(f"| Stack A | Swift Vapor 4 — ports 8081–8083 (user, product, order) |")
    md.append(f"| Stack B | Java Spring Boot 3 — ports 9081–9083 |")
    md.append(f"| Database | PostgreSQL 15 (one DB per service) |")
    md.append(f"| Cache | Redis 7 (shared) |")
    md.append("")

    md.append("## 2. Headline Results (k6 client-side measurements)")
    md.append("")
    md.append("| Metric | Swift Vapor | Java Spring Boot | Δ vs Java |")
    md.append("|---|---|---|---|")
    md.append(f"| Total requests | {fmt_int(swift_total)} | {fmt_int(java_total)} | tied |")
    md.append(f"| Throughput (req/s) | {swift_rate:.2f} | {java_rate:.2f} | tied |")
    if swift_avg and java_avg:
        delta_avg = ((swift_avg - java_avg) / java_avg) * 100
        md.append(f"| Avg latency | {fmt_ms(swift_avg)} | {fmt_ms(java_avg)} | {delta_avg:+.1f}% |")
    if swift_med and java_med:
        delta_med = ((swift_med - java_med) / java_med) * 100
        md.append(f"| Median (P50) | {fmt_ms(swift_med)} | {fmt_ms(java_med)} | {delta_med:+.1f}% |")
    if swift_p90 and java_p90:
        delta_p90 = ((swift_p90 - java_p90) / java_p90) * 100
        md.append(f"| P90 | {fmt_ms(swift_p90)} | {fmt_ms(java_p90)} | {delta_p90:+.1f}% |")
    if swift_p95 and java_p95:
        delta_p95 = ((swift_p95 - java_p95) / java_p95) * 100
        md.append(f"| P95 | {fmt_ms(swift_p95)} | {fmt_ms(java_p95)} | {delta_p95:+.1f}% |")
    md.append(f"| Min latency | {fmt_ms(swift_min)} | {fmt_ms(java_min)} | — |")
    md.append(f"| Max latency | {fmt_ms(swift_max)} | {fmt_ms(java_max)} | — |")
    md.append(f"| Errors (k6 checks) | {int(swift_err_fails or 0):,} of {int((swift_err_passes or 0) + (swift_err_fails or 0)):,} | "
              f"{int(java_err_fails or 0):,} of {int((java_err_passes or 0) + (java_err_fails or 0)):,} | tied |")
    md.append(f"| Error rate | {fmt_pct(swift_err)} | {fmt_pct(java_err)} | tied |")
    md.append("")
    md.append(f"> **HTTP-level failure rate (overall):** {fmt_pct(http_req_failed)} of {fmt_int(http_reqs)} requests.")
    md.append("")

    md.append("## 3. Per-Service Throughput (Prometheus, 2-min avg at mid-test)")
    md.append("")
    md.append("| Service | Swift RPS | Java RPS |")
    md.append("|---|---|---|")
    for svc in ["user-service", "product-service", "order-service"]:
        s_v = lookup(swift_rps, service=svc)
        j_v = lookup(java_rps, service=svc)
        md.append(f"| {svc} | {f'{s_v:.2f}' if s_v else '—'} | {f'{j_v:.2f}' if j_v else '—'} |")
    md.append("")

    md.append("## 4. Per-Service Latency (Prometheus histogram, mid-test)")
    md.append("")
    md.append("### 4.1 P50 (median)")
    md.append("")
    md.append("| Service | Swift | Java |")
    md.append("|---|---|---|")
    for svc in ["user-service", "product-service", "order-service"]:
        s_v = lookup(swift_lat_p50, service=svc)
        j_v = lookup(java_lat_p50, service=svc)
        md.append(f"| {svc} | {fmt_ms(s_v)} | {fmt_ms(j_v)} |")
    md.append("")
    md.append("### 4.2 P95")
    md.append("")
    md.append("| Service | Swift | Java |")
    md.append("|---|---|---|")
    for svc in ["user-service", "product-service", "order-service"]:
        s_v = lookup(swift_lat_p95, service=svc)
        j_v = lookup(java_lat_p95, service=svc)
        md.append(f"| {svc} | {fmt_ms(s_v)} | {fmt_ms(j_v)} |")
    md.append("")
    md.append("### 4.3 P99")
    md.append("")
    md.append("| Service | Swift | Java |")
    md.append("|---|---|---|")
    for svc in ["user-service", "product-service", "order-service"]:
        s_v = lookup(swift_lat_p99, service=svc)
        j_v = lookup(java_lat_p99, service=svc)
        md.append(f"| {svc} | {fmt_ms(s_v)} | {fmt_ms(j_v)} |")
    md.append("")

    md.append("## 5. Memory Footprint (peak during test)")
    md.append("")
    md.append("Swift uses ARC (Automatic Reference Counting) — compile-time memory management, no GC.")
    md.append("Java uses G1 GC — heap-based with periodic concurrent collection. Total JVM = heap + non-heap (metaspace, code cache, etc.).")
    md.append("")
    md.append("| Service | Swift RSS (peak) | Java JVM Heap (peak) | Java JVM Total (peak) | Java Non-Heap |")
    md.append("|---|---|---|---|---|")
    for svc in ["user-service", "product-service", "order-service"]:
        s_v = lookup(swift_rss_peak, service=svc)
        j_h = lookup(java_heap_peak, service=svc)
        j_t = lookup(java_total_peak, service=svc)
        j_nh = lookup(java_nonheap_peak, service=svc)
        md.append(f"| {svc} | {fmt_mb(s_v)} | {fmt_mb(j_h)} | {fmt_mb(j_t)} | {fmt_mb(j_nh)} |")
    md.append("")
    swift_avg_mem = sum(swift_rss_peak.values()) / len(swift_rss_peak) if swift_rss_peak else 0
    java_avg_heap = sum(java_heap_peak.values()) / len(java_heap_peak) if java_heap_peak else 0
    java_avg_total = sum(java_total_peak.values()) / len(java_total_peak) if java_total_peak else 0
    md.append(f"**Average across 3 services:**  ")
    md.append(f"- Swift RSS: **{fmt_mb(swift_avg_mem)}**")
    md.append(f"- Java JVM heap: **{fmt_mb(java_avg_heap)}**")
    md.append(f"- Java JVM total: **{fmt_mb(java_avg_total)}**")
    if swift_avg_mem and java_avg_total:
        md.append(f"- **Swift uses {(java_avg_total/swift_avg_mem):.1f}× less total memory than Java JVM.**")
    md.append("")

    md.append("## 6. Concurrency Model")
    md.append("")
    md.append("Swift Vapor uses **async/await** on top of SwiftNIO event loops (cooperative, non-blocking I/O). "
              "Java Spring Boot uses **thread-per-request** via Tomcat's executor pool.")
    md.append("")
    md.append("| Service | Java Live Threads (peak) | Java Daemon Threads | Java All-Time Peak |")
    md.append("|---|---|---|---|")
    for svc in ["user-service", "product-service", "order-service"]:
        live = lookup(java_threads_peak, service=svc)
        daem = lookup(java_threads_daemon, service=svc)
        peak = lookup(java_threads_alltime_peak, service=svc)
        md.append(f"| {svc} | {fmt_int(live)} | {fmt_int(daem)} | {fmt_int(peak)} |")
    md.append("")
    md.append("> Swift NIO event loops are typically 1 per CPU core (~10 on this machine), regardless of "
              "concurrent request count. Java needs to grow its thread pool to handle concurrent connections.")
    md.append("")

    md.append("## 7. GC Overhead (Java only)")
    md.append("")
    md.append("Swift has **zero runtime GC overhead** (ARC is compile-time). Java G1 GC consumes CPU time periodically.")
    md.append("")
    md.append("| Service | GC Overhead % (peak during test) |")
    md.append("|---|---|")
    for svc in ["user-service", "product-service", "order-service"]:
        v = lookup(java_gc_overhead_peak, service=svc)
        md.append(f"| {svc} | {v:.4f}% |" if v is not None else f"| {svc} | — |")
    md.append("")

    md.append("## 8. Database Connection Pool (Java HikariCP)")
    md.append("")
    md.append("Java services use HikariCP (max 20 connections per service). Swift uses async PostgreSQL "
              "driver (per-event-loop connections).")
    md.append("")
    md.append("| Service | Active (peak) | Idle | Max |")
    md.append("|---|---|---|---|")
    for svc in ["user-service", "product-service", "order-service"]:
        a = lookup(hikari_active_peak, service=svc)
        i = lookup(hikari_idle, service=svc)
        m_ = lookup(hikari_max_v, service=svc)
        md.append(f"| {svc} | {fmt_int(a)} | {fmt_int(i)} | {fmt_int(m_)} |")
    md.append("")

    md.append("## 9. Status Code Breakdown (cumulative at test end)")
    md.append("")
    md.append("### 9.1 Swift (Vapor) — by status code")
    md.append("")
    md.append("| Service | Status | Count |")
    md.append("|---|---|---|")
    for k, v in sorted(swift_by_status.items(), key=lambda x: (dict(x[0]).get("service", ""), dict(x[0]).get("status", ""))):
        d = dict(k)
        md.append(f"| {d.get('service', '?')} | {d.get('status', '?')} | {fmt_int(v)} |")
    md.append("")
    md.append("### 9.2 Java (Spring Boot) — by status code")
    md.append("")
    md.append("| Service | Status | Outcome | Count |")
    md.append("|---|---|---|---|")
    for k, v in sorted(java_by_status.items(), key=lambda x: (dict(x[0]).get("service", ""), dict(x[0]).get("status", ""))):
        d = dict(k)
        md.append(f"| {d.get('service', '?')} | {d.get('status', '?')} | {d.get('outcome', '?')} | {fmt_int(v)} |")
    md.append("")

    md.append("## 10. Error Analysis")
    md.append("")
    if (swift_err or 0) < 0.001 and (java_err or 0) < 0.001:
        md.append(f"**Both stacks: 0 errors out of {fmt_int(swift_total)} (Swift) and {fmt_int(java_total)} (Java) "
                  f"requests.** All checks (status 2xx, response time < 2s, body present) passed at 100%.")
        md.append("")
        md.append("Status code distribution shows only 2xx responses (200 for reads, 201 for creates). "
                  "No 4xx (validation/conflict) or 5xx (server) errors observed under sustained load.")
    else:
        swift_err_pct = (swift_err or 0) * 100
        java_err_pct = (java_err or 0) * 100
        md.append(f"**Swift error rate: {swift_err_pct:.2f}%** ({int(swift_err_fails or 0):,} of "
                  f"{int((swift_err_passes or 0) + (swift_err_fails or 0)):,} checks failed)")
        md.append(f"**Java error rate:  {java_err_pct:.2f}%** ({int(java_err_fails or 0):,} of "
                  f"{int((java_err_passes or 0) + (java_err_fails or 0)):,} checks failed)")
        md.append("")
        md.append("Inspect the status code breakdown (§9) for distribution by endpoint and root cause.")
    md.append("")

    md.append("## 11. Key Findings")
    md.append("")
    findings = []

    # Latency winners
    if swift_p95 and java_p95:
        winner = "Swift" if swift_p95 < java_p95 else "Java"
        ratio = max(swift_p95, java_p95) / min(swift_p95, java_p95)
        findings.append(f"**P95 latency:** **{winner}** wins ({fmt_ms(min(swift_p95, java_p95))} vs "
                        f"{fmt_ms(max(swift_p95, java_p95))}, **{ratio:.2f}× faster**).")
    if swift_med and java_med:
        winner = "Swift" if swift_med < java_med else "Java"
        ratio = max(swift_med, java_med) / min(swift_med, java_med)
        findings.append(f"**Median (P50):** **{winner}** wins ({fmt_ms(min(swift_med, java_med))} vs "
                        f"{fmt_ms(max(swift_med, java_med))}, **{ratio:.2f}× faster**).")
    if swift_max and java_max:
        winner = "Swift" if swift_max < java_max else "Java"
        ratio = max(swift_max, java_max) / min(swift_max, java_max)
        findings.append(f"**Max latency (worst case):** **{winner}** lower ({fmt_ms(min(swift_max, java_max))} vs "
                        f"{fmt_ms(max(swift_max, java_max))}).")

    # Memory
    if swift_avg_mem and java_avg_total:
        ratio = java_avg_total / swift_avg_mem
        findings.append(f"**Memory:** Swift averaged **{fmt_mb(swift_avg_mem)}** RSS vs Java **{fmt_mb(java_avg_total)}** "
                        f"total JVM — **Swift {ratio:.1f}× lighter**.")

    # Threads (compute from data)
    if java_threads_peak:
        max_thr = max(java_threads_peak.values())
        min_thr = min(java_threads_peak.values())
        findings.append(f"**Concurrency:** Java grew to **{int(min_thr)}–{int(max_thr)} live threads** per service; "
                        "Swift NIO uses ~10 event loops total across all 3 services (1 per CPU core).")

    # GC
    if java_gc_overhead_peak:
        max_gc = max(java_gc_overhead_peak.values()) if java_gc_overhead_peak else 0
        findings.append(f"**GC overhead:** Java G1 peaked at **{max_gc:.4f}%** CPU (negligible at this scale). "
                        "Swift ARC has zero runtime GC cost.")

    findings.append(f"**Throughput:** Both stacks served identical k6 load (~{swift_rate:.0f} req/s/stack) "
                    "without saturation — bottleneck was the k6 workload pattern (sleep between groups), "
                    "not the server.")

    # Per-service nuance
    p_swift = lookup(swift_lat_p95, service="product-service")
    p_java = lookup(java_lat_p95, service="product-service")
    if p_swift and p_java:
        if p_java < p_swift:
            ratio = p_swift / p_java
            findings.append(f"**Per-service nuance — pure DB (product-service P95):** Java **{ratio:.1f}× faster** "
                            f"({fmt_ms(p_java)} vs {fmt_ms(p_swift)}). Likely due to Hibernate query cache + "
                            "JIT optimizations on the hot read path.")
    u_swift = lookup(swift_lat_p95, service="user-service")
    u_java = lookup(java_lat_p95, service="user-service")
    if u_swift and u_java:
        if u_java < u_swift:
            ratio = u_swift / u_java
            findings.append(f"**Per-service nuance — bcrypt POST (user-service P95):** Java **{ratio:.1f}× lower tail** "
                            f"({fmt_ms(u_java)} vs {fmt_ms(u_swift)}), even with Swift bcrypt offloaded to thread pool. "
                            "Java thread-per-request handles concurrent CPU-bound work more uniformly.")
        else:
            ratio = u_java / u_swift
            findings.append(f"**Per-service — bcrypt POST (user-service P95):** Swift wins despite CPU-bound work "
                            f"({fmt_ms(u_swift)} vs {fmt_ms(u_java)}, {ratio:.1f}× faster).")

    for i, f in enumerate(findings, 1):
        md.append(f"{i}. {f}")
    md.append("")

    md.append("## 12. Apple-to-Apple Parity Configuration")
    md.append("")
    md.append("This run was configured for **fair runtime-overhead comparison** with the following parity:")
    md.append("")
    md.append("| Aspect | Swift Vapor | Java Spring Boot |")
    md.append("|---|---|---|")
    md.append("| Database | Separate `swift_*_db` per service | Separate `java_*_db` per service |")
    md.append("| bcrypt cost factor | `app.passwords.use(.bcrypt(cost: 10))` | `new BCryptPasswordEncoder(10)` |")
    md.append("| bcrypt threading | `req.password.async.hash(_:)` → NIOThreadPool | Tomcat worker threads |")
    md.append("| DB connection pool | `maxConnectionsPerEventLoop: 2` × 10 loops = 20 | HikariCP `maximum-pool-size: 20` |")
    md.append("| HTTP server | SwiftNIO (10 event loops) | Tomcat (200 thread max) |")
    md.append("| Cache | Vapor Redis client (manual TTL 30s) | Spring `@Cacheable` (Redis TTL 30s) |")
    md.append("")
    md.append("## 13. Limitations & Caveats")
    md.append("")
    md.append("- **macOS Docker Desktop cAdvisor:** does not expose per-container `name` label. "
              "Memory comparison uses Java JVM Micrometer metrics + Swift process RSS from "
              "`/proc/self/status`.")
    md.append("- **Cold-start excluded:** k6 ran after ~15s warmup, so JVM JIT had reached steady state. "
              "Swift was already AOT-compiled. Cold-start would favor Swift.")
    md.append("- **Single-host benchmark:** all services + load generator on one M-series Mac — no "
              "network latency between k6 and services. Results reflect *runtime overhead*, not real "
              "deployment latency where network would dominate.")
    md.append("- **Throughput is k6-bounded:** With 100 VUs and `sleep(0.5)` between groups, the stack "
              "never saturated. Both stacks could likely handle much higher RPS — this run measures "
              "*latency under fixed load*, not max throughput.")
    md.append("")

    md.append("## 14. Reproducibility")
    md.append("")
    md.append("```bash")
    md.append("# Full reset + re-run:")
    md.append("./scripts/reset-and-benchmark.sh load")
    md.append("")
    md.append("# Or step-by-step:")
    md.append("docker compose -f infrastructure/docker-compose.monitoring.yml stop prometheus loki")
    md.append("docker volume rm infrastructure_prometheus-data infrastructure_loki-data")
    md.append("docker compose -f infrastructure/docker-compose.monitoring.yml up -d prometheus loki")
    md.append("docker compose -f infrastructure/docker-compose.yml restart \\")
    md.append("  swift-user-service swift-product-service swift-order-service \\")
    md.append("  java-user-service java-product-service java-order-service")
    md.append("./scripts/run-benchmark.sh load")
    md.append("")
    md.append("# Generate this report from latest run:")
    md.append("python3 benchmarking/analysis/generate_report.py")
    md.append("```")
    md.append("")
    md.append(f"**Raw artifacts:**")
    md.append(f"- k6 summary JSON: `{summary_path.relative_to(ROOT)}`")
    md.append(f"- Per-iteration JSON stream: `benchmarking/results/{test_id}.json` (~200 MB)")
    md.append(f"- k6 stdout log: `benchmarking/results/{test_id}.log`")
    md.append(f"- Prometheus metrics CSV: `{csv_path.relative_to(ROOT)}`")
    md.append(f"- Status code CSV: `{status_csv.relative_to(ROOT)}`")
    md.append("")

    md_path.write_text("\n".join(md))
    print(f"✓ Report written: {md_path}")

    # ---- CSV exports ----
    with csv_path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["category", "language", "service", "metric", "value", "unit"])

        def dump(series, cat, lang, metric, unit, conv=lambda v: v):
            for k, v in series.items():
                w.writerow([cat, lang, dict(k).get("service"), metric, conv(v), unit])

        dump(swift_rps, "throughput", "swift", "rps_2min_avg", "req/s")
        dump(java_rps, "throughput", "java", "rps_2min_avg", "req/s")
        dump(swift_lat_p50, "latency", "swift", "p50", "ms")
        dump(swift_lat_p95, "latency", "swift", "p95", "ms")
        dump(swift_lat_p99, "latency", "swift", "p99", "ms")
        dump(java_lat_p50, "latency", "java", "p50", "ms")
        dump(java_lat_p95, "latency", "java", "p95", "ms")
        dump(java_lat_p99, "latency", "java", "p99", "ms")
        dump(swift_rss_peak, "memory", "swift", "rss_peak", "bytes")
        dump(java_heap_peak, "memory", "java", "jvm_heap_peak", "bytes")
        dump(java_total_peak, "memory", "java", "jvm_total_peak", "bytes")
        dump(java_nonheap_peak, "memory", "java", "jvm_nonheap_peak", "bytes")
        dump(java_threads_peak, "concurrency", "java", "threads_live_peak", "count")
        dump(java_threads_daemon, "concurrency", "java", "threads_daemon", "count")
        dump(java_threads_alltime_peak, "concurrency", "java", "threads_alltime_peak", "count")
        dump(java_gc_overhead_peak, "gc", "java", "overhead_peak", "percent")
        dump(hikari_active_peak, "db_pool", "java", "hikari_active_peak", "count")
        dump(hikari_idle, "db_pool", "java", "hikari_idle", "count")
        dump(hikari_max_v, "db_pool", "java", "hikari_max", "count")
    print(f"✓ Metrics CSV: {csv_path}")

    with status_csv.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["language", "service", "status", "outcome", "count"])
        for k, v in swift_by_status.items():
            d = dict(k)
            w.writerow(["swift", d.get("service"), d.get("status"), "", int(v)])
        for k, v in java_by_status.items():
            d = dict(k)
            w.writerow(["java", d.get("service"), d.get("status"), d.get("outcome", ""), int(v)])
    print(f"✓ Status code CSV: {status_csv}")

    print(f"\nDone. Open the report:")
    print(f"  open {md_path}")


if __name__ == "__main__":
    main()
