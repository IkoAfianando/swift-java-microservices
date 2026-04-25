# Tutorial — Running the Swift vs Java Benchmark End-to-End

This walkthrough takes you from a fresh clone to a complete benchmark report. Allow about 1 hour total: 5 minutes for setup, 30 minutes for the core suite, plus an optional 40-minute soak test.

## 1. Prerequisites

| Tool | Minimum version | Why |
|---|---|---|
| **Docker Desktop** | 4.30+ (Compose v2 built-in) | Runs everything as containers |
| **k6** | 0.50+ | Load generator |
| **Python** | 3.10+ | Report generation scripts |
| **bash** / zsh | any modern shell | Wrapper scripts |
| **curl** | any | Smoke tests |

```bash
# macOS install
brew install --cask docker
brew install k6 python@3.12
```

Recommended hardware: a machine with at least **8 CPU cores and 16 GB of RAM**. The benchmark stresses Postgres + Redis + 6 services + the load generator on the same host, so an underpowered machine will conflate runtime overhead with CPU contention.

## 2. First-Time Setup

```bash
cd swift-vs-java-microservices

# Creates the two external Docker networks (microservices-net, monitoring-net)
# and copies infrastructure/.env.example to infrastructure/.env
./scripts/setup.sh
```

If `./scripts/setup.sh` reports the networks already exist, that's fine — they're idempotent.

**About ports**: the project uses non-default host ports to avoid conflicts with anything else you might have running:

| Service | Host port | Reason |
|---|---|---|
| PostgreSQL | `5433` (→ container 5432) | Avoid clashing with a local Postgres on 5432 |
| Redis | `6380` (→ container 6379) | Avoid clashing with a local Redis on 6379 |
| Grafana | `3000` |  |
| Prometheus | `9090` |  |
| Loki | `3100` |  |
| Swift services | `8081` (user), `8082` (product), `8083` (order) |  |
| Java services | `9081` (user), `9082` (product), `9083` (order) |  |

If any of those host ports are in use, edit `infrastructure/.env` to override them.

## 3. Bring Everything Up

```bash
cd infrastructure

# Start the monitoring stack first (Prometheus, Grafana, Loki, Promtail, cAdvisor, Alertmanager, Node Exporter)
docker compose -f docker-compose.monitoring.yml up -d

# Then the services + their dependencies (Postgres, Redis, 3 Swift services, 3 Java services)
docker compose up -d

# Watch them become healthy — should take 20–30 seconds
docker compose ps
cd ..
```

You're looking for **all 6 service containers reporting `(healthy)`**. If any is still `(starting)` or `(unhealthy)` after 60 s, check its logs:

```bash
docker compose -f infrastructure/docker-compose.yml logs swift-user-service --tail=50
docker compose -f infrastructure/docker-compose.yml logs java-user-service --tail=50
```

### Smoke test

Make sure both stacks accept requests:

```bash
# Swift user-service
curl -X POST http://localhost:8081/users \
  -H "Content-Type: application/json" \
  -d '{"name":"Smoke","email":"s1@test.com","password":"Test1234!"}'

# Java user-service
curl -X POST http://localhost:9081/users \
  -H "Content-Type: application/json" \
  -d '{"name":"Smoke","email":"s2@test.com","password":"Test1234!"}'
```

Both should return HTTP 201 with a JSON body containing a UUID. If you get 500 instead, inspect the container logs — the most common cause is a stale `infrastructure_postgres-data` volume from a different schema, fixed by the reset commands in §6.

### Open Grafana

```bash
open http://localhost:3000
```

Login with `admin` / `admin` (change this if you ever expose Grafana publicly). The "Swift vs Java Microservices – Research Benchmark" dashboard is auto-provisioned from `monitoring/grafana/dashboards/microservices-comparison.json`.

While the system is idle you'll see "No data" on most panels. That's expected — they populate once a benchmark starts firing requests.

## 4. Run the Benchmark

The fastest path is the wrapper script:

```bash
./scripts/run-final-suite.sh
```

This runs three scenarios sequentially, writes everything to `benchmarking/results/final/`, then auto-generates per-scenario reports + a master comparison.

| Scenario | Duration | What it measures |
|---|---|---|
| `load` | ~10 min, ramps 0 → 100 → 0 VUs | Realistic steady-state load — both stacks should sail through |
| `stress` | ~13 min, ramps 50 → 1000 VUs | Saturation behaviour — finds where each stack falls over |
| `spike` | ~5.5 min, 20 → 200 VUs sudden burst | Recovery after a flash-traffic event |

Total: **~30 minutes**.

### Optional: also run the soak test

The soak test is the 80/20 read-write endurance run, useful for memory-leak evidence in your paper. It's skipped from `--all` because the default duration is 2 hours. Run it explicitly with a shorter duration:

```bash
SOAK_DURATION=30m ./scripts/run-final-suite.sh soak
```

That's a 40-minute total wall-clock (5 min ramp-up + 30 min hold + 5 min ramp-down). After it finishes, regenerate the master report so it includes all four scenarios:

```bash
./scripts/regen-final-report.sh
```

### Run a single scenario only

```bash
./scripts/run-final-suite.sh load
./scripts/run-final-suite.sh stress
./scripts/run-final-suite.sh spike
SOAK_DURATION=30m ./scripts/run-final-suite.sh soak
```

### Watch it live

While the benchmark is running, keep Grafana open. The most informative panels are:

- **Request Rate (req/s)** — confirms both stacks are receiving the same load
- **P95 Latency** — the headline number you'll cite in the paper
- **JVM Threads** — watch Java grow under load
- **Memory: Java JVM Heap vs Swift RSS** — the Swift line stays flat; Java zigzags from GC

## 5. Read the Reports

```bash
open benchmarking/results/final/reports/MASTER_REPORT_FINAL_SUITE.md
```

The folder structure looks like this after a complete suite:

```
benchmarking/results/final/
├── 20260425_133214_load-test_summary.json     ← k6 aggregate stats
├── 20260425_133214_load-test.log              ← k6 console output (small)
├── 20260425_133214_stress-test_summary.json
├── 20260425_133214_stress-test.log
├── 20260425_141231_spike-test_summary.json
├── 20260425_141231_spike-test.log
├── 20260425_142729_soak-test_summary.json     ← only if you ran soak
├── 20260425_142729_soak-test.log
└── reports/
    ├── MASTER_REPORT_FINAL_SUITE.md           ← Headline + verdict per scenario
    ├── report_<TIMESTAMP>_<scenario>.md       ← Detailed per-scenario report
    ├── metrics_<TIMESTAMP>_<scenario>.csv     ← Server-side metrics from Prometheus
    └── status_<TIMESTAMP>_<scenario>.csv      ← HTTP status code breakdown
```

Note that the **per-iteration JSON streams** (one of which is 1.6 GB) are *not* committed to git — they're listed in `.gitignore`. If you want them, they're produced locally by k6 in the same folder as the summaries.

### What each report contains

Every per-scenario report includes:

1. **Test configuration** — scenario, VUs, duration, total requests
2. **Headline results** — k6 client-side P50/P90/P95, error rate, throughput
3. **Per-service throughput** — Prometheus rate by service (mid-test snapshot)
4. **Per-service latency** — P50/P95/P99 from Prometheus histograms (server-side)
5. **Memory footprint** — Swift RSS vs Java JVM heap and total
6. **Concurrency model** — JVM threads (live, daemon, peak)
7. **GC overhead** — Java only (Swift has zero runtime GC)
8. **DB connection pool** — HikariCP active/idle/max
9. **Status code breakdown** — count by service + status + outcome
10. **Error analysis** — auto-generated; if 0 errors, says so explicitly
11. **Key findings** — winners per metric, computed from the data
12. **Apple-to-apple parity configuration** — the table that makes the comparison fair
13. **Limitations & caveats** — what this run does *not* claim
14. **Reproducibility** — exact commands

The master report aggregates §1, §2 (latency by scenario), §3 (throughput), §4 (verdict per scenario), §5 (parity), §6 (links).

## 6. Resetting

When you want a clean slate (e.g. before re-running the full suite for the paper):

```bash
cd infrastructure
docker compose down
docker compose -f docker-compose.monitoring.yml down
docker volume ls -q | grep "infrastructure_" | xargs docker volume rm
cd ..
```

This wipes Postgres, Redis, Prometheus TSDB, Loki logs, Grafana DB, Alertmanager state. The Docker networks and images survive.

To wipe and re-run in one command:

```bash
./scripts/reset-and-benchmark.sh load        # or stress, spike, soak, all
```

## 7. Regenerating Reports Without Re-Running

If you tweak `generate_report.py` or `generate_consolidated.py` and want to refresh the markdown without re-running k6:

```bash
./scripts/regen-final-report.sh
```

This will:
1. Delete all stale `MASTER_REPORT_*.md` files in `benchmarking/results/final/reports/`
2. Re-generate every per-scenario report (skipping aborted runs with zero iterations)
3. Build a fresh `MASTER_REPORT_FINAL_SUITE.md` from whatever summaries it finds

Note that this script reads from `benchmarking/results/final/` only. Old runs in `benchmarking/results/` (without the `final/` subfolder) are left alone.

## 8. Common Issues

### "POST /users returns 500"

You're hitting the schema-conflict bug — the database used to be shared between Swift and Java, so the two ORMs added clashing column names. Fix:

```bash
docker compose down
docker volume rm infrastructure_postgres-data
docker compose up -d
```

The current `init-db.sql` creates **6 separate databases** (`swift_user_db`, `swift_product_db`, `swift_order_db`, `java_user_db`, `java_product_db`, `java_order_db`) so each ORM owns its own schema cleanly.

### "k6 reports `__ITER is not defined`"

You're running an older copy of `benchmarking/k6/helpers/utils.js`. The current version uses `typeof __VU !== "undefined"` guards so it's safe inside `setup()` and `teardown()`.

### "Grafana shows `No data` for histogram panels"

Three things to check:

1. **Did you actually run a benchmark?** Histograms only populate after requests
2. **Time window** — Grafana defaults to `Last 30 minutes`. If you're looking at the panel an hour after the run, switch to `Custom range` and pick the test window
3. **Histogram bucket parity** — Swift's `MetricsCollector` ships the same 72 bucket boundaries Java's Micrometer emits. If you've forked the code, make sure you didn't accidentally revert to the 11-bucket version, or the two stacks will look unfairly different at low-latency percentiles

### "Build is slow"

The very first Swift build inside the Docker context downloads the entire Swift toolchain and compiles Vapor + dependencies. Allow 5–10 minutes for the first run; subsequent rebuilds use the layer cache and finish in under 30 seconds.

The Java build is faster (Maven downloads dependencies once, then compiles in seconds).

### "Stress test threshold failed for `java_request_duration`"

That's not a bug — it's a research finding. At 1000 VUs, Java's 200-thread Tomcat pool starves and P95 climbs above the 2-second threshold. Swift, with 10 NIO event loops multiplexing all 1000 connections, holds P95 around 1 second. This is the headline result of the stress scenario; see `FINDINGS.md` §3.2.

## 9. What's Next

- **Read the findings** — [`FINDINGS.md`](./FINDINGS.md) walks through every result with context
- **Cite the data** — every CSV in `benchmarking/results/final/reports/` is suitable for paper figures
- **Reproduce on different hardware** — the parity guarantees should hold; absolute numbers will differ

If something doesn't reproduce, file an issue with: hardware, Docker version, k6 version, and the exact command you ran.
