# Swift Vapor vs Java Spring Boot — Microservices Performance Benchmark

> **Research project** — empirical comparison of Swift (Vapor 4) and Java (Spring Boot 3) under identical microservices workloads.
>
> Iko Afianando (NIM 2602261970) — BINUS University 2025/2026 — Enrichment Program

---

## TL;DR

Six identical microservices (User, Product, Order × Swift + Java), running side-by-side in Docker against the same PostgreSQL and Redis. Hit them with k6 across four scenarios (load, stress, spike, soak), then collect server-side metrics from Prometheus and analyse client-side latency from k6.

Configuration is **apple-to-apple by construction**: bcrypt cost = 10 in both, async thread-pool offloading on both, 20 DB connections per service in both, **identical 72-bucket histograms in both**.

### Headline result (4 scenarios, 691,352 total requests)

| Scenario | VUs (max) | Verdict |
|---|---|---|
| Load — 100 VUs, 10 min | 100 | 🟢 **Swift wins** P50 (1.5×), P95 (1.2×), Max — both 0% error |
| Stress — 1000 VUs, 13 min | 1000 | 🟢 **Swift wins decisively** — P95 **27.83× faster** (1.02 s vs 28.33 s); Java threshold failed |
| Spike — 200 VUs burst, 5.5 min | 200 | 🔴 Java wins P50 (1.7×), P95 (1.6×) — both 0% error |
| Soak — 30 VUs × 40 min | 30 | 🟢 **Swift wins** P50 (7.94×), P95 (4.01×) — both 0% error |

**Memory footprint (across all services):** Swift 46.4 MB RSS vs Java 258.5 MB total JVM — **Swift 5.6× lighter**.

**Concurrency model:** Swift uses ~10 SwiftNIO event loops; Java grows to 28–46 OS threads.

See [`FINDINGS.md`](./FINDINGS.md) for the full analysis and [`benchmarking/results/final/reports/MASTER_REPORT_FINAL_SUITE.md`](./benchmarking/results/final/reports/MASTER_REPORT_FINAL_SUITE.md) for raw numbers per scenario.

---

## Stack

| Layer | Swift side | Java side |
|---|---|---|
| Language | Swift 6.0 (Linux) | Java 21 |
| Framework | Vapor 4.99 | Spring Boot 3.2 |
| ORM | Fluent + FluentPostgresDriver | JPA / Hibernate |
| HTTP server | SwiftNIO event loops | Tomcat thread pool |
| DB | PostgreSQL 15 (separate DB per service per language) | same |
| Cache | Redis 7 | same |
| Metrics | Custom `MetricsCollector` actor → `/metrics` (Prometheus text format, 72 histogram buckets) | Spring Boot Actuator + Micrometer |
| Logs | Promtail → Loki | same |
| Container | Docker Compose (multi-service, two external networks) | same |

## Project Layout

```
swift-vs-java-microservices/
├── README.md                    ← you are here
├── TUTORIAL.md                  ← step-by-step guide to run everything
├── FINDINGS.md                  ← full research findings (English)
├── LICENSE                      ← MIT
├── .gitignore
│
├── services/
│   ├── swift/                   ← Vapor 4 services (Swift Package Manager)
│   │   ├── user-service/
│   │   ├── product-service/
│   │   └── order-service/
│   └── java/                    ← Spring Boot 3 services (Maven)
│       ├── user-service/
│       ├── product-service/
│       └── order-service/
│
├── infrastructure/
│   ├── docker-compose.yml              ← 6 services + Postgres + Redis
│   ├── docker-compose.monitoring.yml   ← Prometheus + Grafana + Loki + cAdvisor + Alertmanager
│   ├── init-db.sql                     ← Creates 6 isolated databases (swift_*_db, java_*_db)
│   └── .env.example
│
├── monitoring/
│   ├── prometheus/                     ← Scrape config + alert rules
│   ├── grafana/                        ← Provisioned dashboards (Swift vs Java comparison)
│   ├── loki/                           ← Log aggregation config
│   ├── promtail/                       ← Log shipper config
│   └── alertmanager/
│
├── benchmarking/
│   ├── k6/
│   │   ├── scenarios/                  ← load, stress, spike, soak (.js)
│   │   ├── helpers/
│   │   └── run-all.sh
│   ├── analysis/
│   │   ├── generate_report.py          ← Per-scenario report generator
│   │   ├── generate_consolidated.py    ← Master comparison report
│   │   └── compare.py                  ← Quick comparison + chart
│   └── results/
│       └── final/                      ← The actual research data
│           ├── *_summary.json          ← k6 aggregate stats per scenario
│           ├── *.log                   ← k6 console output
│           └── reports/
│               ├── MASTER_REPORT_FINAL_SUITE.md
│               ├── report_*.md         ← Per-scenario markdown reports
│               ├── metrics_*.csv       ← Prometheus-derived metrics
│               └── status_*.csv        ← HTTP status code breakdown
│
└── scripts/
    ├── setup.sh                        ← One-shot env + network setup
    ├── run-final-suite.sh              ← Run the FINAL benchmark suite
    ├── regen-final-report.sh           ← Regenerate reports without re-running
    └── reset-and-benchmark.sh          ← Wipe + re-run
```

## Quick Start

```bash
# 1. Clone and enter the project
git clone <this-repo>
cd swift-vs-java-microservices

# 2. Bootstrap (creates Docker networks, copies .env)
./scripts/setup.sh

# 3. Start the monitoring stack and the services
cd infrastructure
docker compose -f docker-compose.monitoring.yml up -d
docker compose up -d
cd ..

# 4. Wait for everything to be healthy (~25 s), then run the FINAL benchmark suite
./scripts/run-final-suite.sh                            # load + stress + spike (~30 min)
SOAK_DURATION=30m ./scripts/run-final-suite.sh soak     # optional 40-min endurance test

# 5. Open the master report
open benchmarking/results/final/reports/MASTER_REPORT_FINAL_SUITE.md
```

For a full walkthrough — including troubleshooting and how to interpret the dashboards — see [`TUTORIAL.md`](./TUTORIAL.md).

## Why "apple-to-apple" matters here

Microservice benchmarks online are full of disparities that quietly bias the result: one stack uses bcrypt cost 12, the other 10; one offloads to a thread pool, the other blocks the request thread; one has a 20-connection pool, the other has 10; one declares 11 histogram buckets, the other declares 73. Each is enough to flip a percentile.

This project explicitly equalises:

- **Database isolation** — separate `swift_*_db` and `java_*_db` so the two ORMs never argue about the schema
- **bcrypt cost = 10** in both stacks (`new BCryptPasswordEncoder(10)` and `app.passwords.use(.bcrypt(cost: 10))`)
- **bcrypt threading** — both stacks offload to a worker pool (Tomcat threads on Java, NIOThreadPool via `req.password.async.hash` on Swift)
- **DB connection pool size = 20** per service (HikariCP `maximum-pool-size: 20`, Vapor `maxConnectionsPerEventLoop: 2 × 10 event loops`)
- **Histogram buckets identical** — Swift's custom `MetricsCollector` ships the exact 72 bucket boundaries Spring Boot Micrometer emits, so `histogram_quantile()` interpolation is bit-for-bit comparable

The full parity table lives in section §5 of `MASTER_REPORT_FINAL_SUITE.md`.

## Reproducibility

All runs in `benchmarking/results/final/` were produced by `./scripts/run-final-suite.sh` against the code in this repo, on the same Apple-Silicon Mac, with Docker Desktop and a clean PostgreSQL/Redis state.

To reproduce from scratch:

```bash
./scripts/reset-and-benchmark.sh            # wipes volumes + re-runs the load scenario
./scripts/run-final-suite.sh                # then load + stress + spike
SOAK_DURATION=30m ./scripts/run-final-suite.sh soak    # optional
./scripts/regen-final-report.sh             # regenerate the markdown reports
```

## Author

**Iko Afianando** — BINUS University 2025/2026, Enrichment Program (Research Track).  
NIM 2602261970.

## License

MIT — see [LICENSE](./LICENSE).
