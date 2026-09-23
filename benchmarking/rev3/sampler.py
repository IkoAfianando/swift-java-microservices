#!/usr/bin/env python3
"""
Resource and server-side metric sampler for one benchmark run.

Runs alongside k6 and records, for the exact measured window:

  * per-container CPU quota utilisation and resident set size (docker stats)
  * the resident set size of the load generator itself, so the cost of k6 on
    the shared host is disclosed rather than assumed away
  * cumulative server-side latency histograms, snapshotted at the start and at
    the end of the window, so percentiles are computed over a stated window
    from a stated bucket set instead of over the process lifetime
  * JVM heap (used and committed), garbage-collection pause count and time,
    busy Tomcat threads, HikariCP pending connections and acquire time
  * a control-plane responsiveness probe: a trivial health endpoint is polled
    at a fixed interval on both stacks, so a stack whose request-servicing
    machinery is saturated shows up symmetrically on either side

Standard library only.
"""
import argparse
import csv
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
import urllib.request
import urllib.error

SWIFT_SERVICES = {
    "swift-user-service":    ("http://localhost:8081/metrics", "http://localhost:8081/health"),
    "swift-product-service": ("http://localhost:8082/metrics", "http://localhost:8082/health"),
    "swift-order-service":   ("http://localhost:8083/metrics", "http://localhost:8083/health"),
}
JAVA_SERVICES = {
    "java-user-service":    ("http://localhost:9081/actuator/prometheus", "http://localhost:9081/actuator/health"),
    "java-product-service": ("http://localhost:9082/actuator/prometheus", "http://localhost:9082/actuator/health"),
    "java-order-service":   ("http://localhost:9083/actuator/prometheus", "http://localhost:9083/actuator/health"),
}

# Gauges and counters pulled out of the scrape, by metric-name prefix.
SCALAR_METRICS = [
    "jvm_memory_used_bytes",
    "jvm_memory_committed_bytes",
    "jvm_gc_pause_seconds_count",
    "jvm_gc_pause_seconds_sum",
    "tomcat_threads_busy_threads",
    "tomcat_threads_current_threads",
    "tomcat_threads_config_max_threads",
    "hikaricp_connections_active",
    "hikaricp_connections_pending",
    "hikaricp_connections_acquire_seconds_count",
    "hikaricp_connections_acquire_seconds_sum",
    "hikaricp_connections_usage_seconds_count",
    "hikaricp_connections_usage_seconds_sum",
    "process_cpu_usage",
    "system_cpu_usage",
    "process_resident_memory_bytes",
]

HIST_PREFIXES = ("http_server_requests_seconds", "http_request_duration_seconds")


def fetch(url, timeout=5.0):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.read().decode("utf-8", "replace")
    except Exception:
        return None


def parse_prom(text):
    """Return (scalars, histogram) from a Prometheus exposition payload.

    scalars   -> list of (name, labels_string, value)
    histogram -> {series_key: {"buckets": {le: count}, "sum": float, "count": float}}
    """
    scalars = []
    hist = {}
    if not text:
        return scalars, hist
    for line in text.splitlines():
        if not line or line[0] == "#":
            continue
        m = re.match(r'^([a-zA-Z_:][a-zA-Z0-9_:]*)(\{.*\})?\s+(.+)$', line)
        if not m:
            continue
        name, labels, raw = m.group(1), m.group(2) or "", m.group(3).strip()
        try:
            val = float(raw.split()[0])
        except ValueError:
            continue

        base = None
        for p in HIST_PREFIXES:
            if name.startswith(p):
                base = p
                break
        if base is not None:
            # Strip the le label so all buckets of one series group together.
            le = None
            lm = re.search(r'le="([^"]+)"', labels)
            if lm:
                le = lm.group(1)
            key_labels = re.sub(r',?le="[^"]*"', "", labels)
            key = base + key_labels
            entry = hist.setdefault(key, {"buckets": {}, "sum": 0.0, "count": 0.0})
            if name.endswith("_bucket") and le is not None:
                entry["buckets"][le] = val
            elif name.endswith("_sum"):
                entry["sum"] = val
            elif name.endswith("_count"):
                entry["count"] = val
            continue

        if name in SCALAR_METRICS:
            scalars.append((name, labels, val))
    return scalars, hist


def snapshot(services):
    out = {}
    for svc, (murl, _) in services.items():
        scal, hist = parse_prom(fetch(murl, timeout=10.0))
        out[svc] = {"scalars": scal, "hist": hist, "t": time.time()}
    return out


def docker_stats():
    try:
        p = subprocess.run(
            ["docker", "stats", "--no-stream", "--format",
             "{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}\t{{.PIDs}}"],
            capture_output=True, text=True, timeout=25)
    except Exception:
        return []
    rows = []
    for line in p.stdout.strip().splitlines():
        parts = line.split("\t")
        if len(parts) < 5:
            continue
        name, cpu, mem, memp, pids = parts[:5]
        try:
            cpu_v = float(cpu.strip().rstrip("%"))
        except ValueError:
            cpu_v = float("nan")
        used = mem.split("/")[0].strip()
        rows.append((name, cpu_v, parse_bytes(used), memp.strip().rstrip("%"), pids.strip()))
    return rows


def parse_bytes(s):
    m = re.match(r'^([0-9.]+)\s*([KMGT]?i?B)$', s.strip(), re.I)
    if not m:
        return float("nan")
    v = float(m.group(1))
    unit = m.group(2).upper().replace("I", "")
    mult = {"B": 1, "KB": 1024, "MB": 1024 ** 2, "GB": 1024 ** 3, "TB": 1024 ** 4}
    return v * mult.get(unit, 1)


_K6_PREV = {"t": None, "cpu_seconds": 0.0}


def _parse_cputime(s):
    """ps cputime, as [dd-]hh:mm:ss.ff or mm:ss.ff, into seconds."""
    s = s.strip()
    days = 0.0
    if "-" in s:
        d, s = s.split("-", 1)
        try:
            days = float(d)
        except ValueError:
            days = 0.0
    parts = s.split(":")
    try:
        parts = [float(x) for x in parts]
    except ValueError:
        return None
    sec = 0.0
    for x in parts:
        sec = sec * 60.0 + x
    return sec + days * 86400.0


def k6_process_usage():
    """(cpu_percent_of_one_core, rss_bytes) over every running k6 process.

    The percentage is derived from the change in accumulated processor time
    between two samples, so it reflects what the load generator used during
    the interval rather than an average over its whole lifetime.
    """
    try:
        p = subprocess.run(["ps", "-Ao", "comm=,cputime=,rss="],
                           capture_output=True, text=True, timeout=10)
    except Exception:
        return float("nan"), float("nan")
    cpu_seconds = 0.0
    rss = 0.0
    found = False
    for line in p.stdout.splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        comm = " ".join(parts[:-2])
        if os.path.basename(comm.strip()) != "k6":
            continue
        found = True
        c = _parse_cputime(parts[-2])
        if c is not None:
            cpu_seconds += c
        try:
            rss += float(parts[-1]) * 1024
        except ValueError:
            pass
    now = time.time()
    prev_t, prev_c = _K6_PREV["t"], _K6_PREV["cpu_seconds"]
    _K6_PREV["t"], _K6_PREV["cpu_seconds"] = now, cpu_seconds
    if not found:
        return 0.0, 0.0
    if prev_t is None or now <= prev_t or cpu_seconds < prev_c:
        return float("nan"), rss
    return (cpu_seconds - prev_c) / (now - prev_t) * 100.0, rss


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True, choices=["swift", "java"])
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--stats-interval", type=float, default=2.0)
    ap.add_argument("--metrics-interval", type=float, default=5.0)
        # The probe is load on the system under test as well as a measurement of
    # it. At a tenth of a second across three services it was issuing roughly
    # twenty five requests a second against a stack serving fifty, which is
    # interference, not observation. Half a second gives more than a thousand
    # samples over a run, which is ample for a percentile, at a fraction of the
    # cost.
    ap.add_argument("--probe-interval", type=float, default=0.5)
    args = ap.parse_args()

    services = SWIFT_SERVICES if args.target == "swift" else JAVA_SERVICES
    os.makedirs(args.outdir, exist_ok=True)
    stop = threading.Event()

    # Opening histogram snapshot: everything reported is a delta against this,
    # which is what makes the aggregation window explicit.
    start_snap = snapshot(services)
    t_start = time.time()

    stats_f = open(os.path.join(args.outdir, f"{args.run_id}_resources.csv"), "w", newline="")
    stats_w = csv.writer(stats_f)
    stats_w.writerow(["t", "container", "cpu_percent_of_one_core", "mem_bytes", "mem_percent_of_limit", "pids"])

    k6_f = open(os.path.join(args.outdir, f"{args.run_id}_loadgen.csv"), "w", newline="")
    k6_w = csv.writer(k6_f)
    k6_w.writerow(["t", "k6_cpu_percent_of_one_core", "k6_rss_bytes"])

    scal_f = open(os.path.join(args.outdir, f"{args.run_id}_server_metrics.csv"), "w", newline="")
    scal_w = csv.writer(scal_f)
    scal_w.writerow(["t", "service", "metric", "labels", "value"])

    probe_f = open(os.path.join(args.outdir, f"{args.run_id}_health_probe.csv"), "w", newline="")
    probe_w = csv.writer(probe_f)
    probe_w.writerow(["t", "service", "latency_ms", "status"])

    # Cumulative request counter per scrape. Differencing it gives throughput
    # over time, which is what identifies the offered load at which a stack
    # stops converting extra concurrency into extra completed work.
    thr_f = open(os.path.join(args.outdir, f"{args.run_id}_throughput.csv"), "w", newline="")
    thr_w = csv.writer(thr_f)
    thr_w.writerow(["t", "service", "series", "cumulative_count", "cumulative_sum_seconds"])

    # The metric scrape is itself a request the service serves and records, so
    # its latency is timed here and subtracted later, exactly as the health
    # probe is. Leaving it in would bias the server-side percentile by about a
    # percent of the sample.
    scr_f = open(os.path.join(args.outdir, f"{args.run_id}_scrape_latency.csv"), "w", newline="")
    scr_w = csv.writer(scr_f)
    scr_w.writerow(["t", "service", "latency_ms"])

    def stats_loop():
        while not stop.is_set():
            t = time.time()
            for name, cpu, mem, memp, pids in docker_stats():
                stats_w.writerow([f"{t:.3f}", name, cpu, mem, memp, pids])
            c, r = k6_process_usage()
            k6_w.writerow([f"{t:.3f}", c, r])
            stats_f.flush()
            k6_f.flush()
            stop.wait(args.stats_interval)

    def metrics_loop():
        while not stop.is_set():
            t = time.time()
            for svc, (murl, _) in services.items():
                _t0 = time.perf_counter()
                payload = fetch(murl, timeout=5.0)
                scr_w.writerow([f"{time.time():.3f}", svc,
                                f"{(time.perf_counter() - _t0) * 1000.0:.3f}"])
                scal, hist = parse_prom(payload)
                for name, labels, val in scal:
                    scal_w.writerow([f"{t:.3f}", svc, name, labels, val])
                for series, entry in hist.items():
                    thr_w.writerow([f"{t:.3f}", svc, series, entry["count"], entry["sum"]])
            scal_f.flush()
            thr_f.flush()
            scr_f.flush()
            stop.wait(args.metrics_interval)

    def probe_loop():
        # Identical instrumentation on both stacks: a trivial endpoint polled at
        # a fixed rate. Its latency reflects how long new work waits before the
        # server can touch it, whether that server uses an event loop or a
        # thread pool.
        urls = [(svc, h) for svc, (_m, h) in services.items()]
        while not stop.is_set():
            for svc, h in urls:
                t0 = time.perf_counter()
                status = 0
                try:
                    with urllib.request.urlopen(h, timeout=10.0) as r:
                        r.read(64)
                        status = r.status
                except urllib.error.HTTPError as e:
                    status = e.code
                except Exception:
                    status = 0
                dt = (time.perf_counter() - t0) * 1000.0
                probe_w.writerow([f"{time.time():.3f}", svc, f"{dt:.3f}", status])
            probe_f.flush()
            stop.wait(args.probe_interval)

    threads = [threading.Thread(target=f, daemon=True) for f in (stats_loop, metrics_loop, probe_loop)]
    for th in threads:
        th.start()

    shutdown = threading.Event()

    def _handle(_signum, _frame):
        shutdown.set()

    signal.signal(signal.SIGINT, _handle)
    signal.signal(signal.SIGTERM, _handle)

    # The driver signals this process once k6 exits.
    try:
        while not shutdown.wait(0.5):
            pass
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        for th in threads:
            th.join(timeout=5)
        end_snap = snapshot(services)
        t_end = time.time()
        out_path = os.path.join(args.outdir, f"{args.run_id}_histograms.json")
        with open(out_path, "w") as fh:
            json.dump({
                "run_id": args.run_id,
                "target": args.target,
                "window_start_unix": t_start,
                "window_end_unix": t_end,
                "window_seconds": t_end - t_start,
                "start": start_snap,
                "end": end_snap,
            }, fh)
        for f in (stats_f, k6_f, scal_f, probe_f, thr_f, scr_f):
            f.close()
        sys.stderr.write(f"sampler wrote {out_path}\n")
        sys.stderr.flush()


if __name__ == "__main__":
    main()
