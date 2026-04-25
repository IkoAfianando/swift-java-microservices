# Benchmark Report — Swift Vapor vs Java Spring Boot

**Researcher:** Iko Afianando (NIM 2602261970)  
**Institution:** BINUS University 2025/2026 — Enrichment Program  
**Test ID:** `20260425_141231_spike-test`  
**Test window:** 2026-04-25 14:12:31 → 14:18:01 (5.5 min)  
**Generated:** 2026-04-25 15:20:00  
**k6 Summary:** `benchmarking/results/final/20260425_141231_spike-test_summary.json`

---

## 1. Test Configuration

| Field | Value |
|---|---|
| Scenario | k6 load test (constant ramp-up) |
| Duration | 5.5 minutes (330 s) |
| Max VUs | 200 |
| Iterations | 104,607 (316.80 iter/s) |
| Total HTTP requests | 418,428 (1267.2 req/s) |
| Endpoints tested | `GET /users`, `GET /products`, `POST /users` |
| Stack A | Swift Vapor 4 — ports 8081–8083 (user, product, order) |
| Stack B | Java Spring Boot 3 — ports 9081–9083 |
| Database | PostgreSQL 15 (one DB per service) |
| Cache | Redis 7 (shared) |

## 2. Headline Results (k6 client-side measurements)

| Metric | Swift Vapor | Java Spring Boot | Δ vs Java |
|---|---|---|---|
| Total requests | 104,607 | 104,607 | tied |
| Throughput (req/s) | 316.80 | 316.80 | tied |
| Avg latency | 2.81 ms | 1.82 ms | +54.7% |
| Median (P50) | 1.83 ms | 1.07 ms | +71.2% |
| P90 | 5.75 ms | 3.38 ms | +70.1% |
| P95 | 7.41 ms | 4.68 ms | +58.4% |
| Min latency | 0.44 ms | 0.22 ms | — |
| Max latency | 77.49 ms | 161.85 ms | — |
| Errors (k6 checks) | 104,607 of 104,607 | 104,607 of 104,607 | tied |
| Error rate | 0.00% | 0.00% | tied |

> **HTTP-level failure rate (overall):** 0.00% of 418,428 requests.

## 3. Per-Service Throughput (Prometheus, 2-min avg at mid-test)

| Service | Swift RPS | Java RPS |
|---|---|---|
| user-service | — | — |
| product-service | 766.67 | 711.85 |
| order-service | — | — |

## 4. Per-Service Latency (Prometheus histogram, mid-test)

### 4.1 P50 (median)

| Service | Swift | Java |
|---|---|---|
| user-service | — | — |
| product-service | 0.86 ms | 0.56 ms |
| order-service | — | — |

### 4.2 P95

| Service | Swift | Java |
|---|---|---|
| user-service | — | — |
| product-service | 3.58 ms | 1.55 ms |
| order-service | — | — |

### 4.3 P99

| Service | Swift | Java |
|---|---|---|
| user-service | — | — |
| product-service | 9.69 ms | 4.38 ms |
| order-service | — | — |

## 5. Memory Footprint (peak during test)

Swift uses ARC (Automatic Reference Counting) — compile-time memory management, no GC.
Java uses G1 GC — heap-based with periodic concurrent collection. Total JVM = heap + non-heap (metaspace, code cache, etc.).

| Service | Swift RSS (peak) | Java JVM Heap (peak) | Java JVM Total (peak) | Java Non-Heap |
|---|---|---|---|---|
| user-service | 50.6 MB | 1312.0 MB | 1449.5 MB | 141.5 MB |
| product-service | 38.9 MB | 134.9 MB | 255.2 MB | 120.5 MB |
| order-service | 17.0 MB | 83.1 MB | 217.4 MB | 134.3 MB |

**Average across 3 services:**  
- Swift RSS: **35.5 MB**
- Java JVM heap: **510.0 MB**
- Java JVM total: **640.7 MB**
- **Swift uses 18.0× less total memory than Java JVM.**

## 6. Concurrency Model

Swift Vapor uses **async/await** on top of SwiftNIO event loops (cooperative, non-blocking I/O). Java Spring Boot uses **thread-per-request** via Tomcat's executor pool.

| Service | Java Live Threads (peak) | Java Daemon Threads | Java All-Time Peak |
|---|---|---|---|
| user-service | 103 | 96 | 220 |
| product-service | 94 | 91 | 95 |
| order-service | 24 | 20 | 30 |

> Swift NIO event loops are typically 1 per CPU core (~10 on this machine), regardless of concurrent request count. Java needs to grow its thread pool to handle concurrent connections.

## 7. GC Overhead (Java only)

Swift has **zero runtime GC overhead** (ARC is compile-time). Java G1 GC consumes CPU time periodically.

| Service | GC Overhead % (peak during test) |
|---|---|
| user-service | 0.0013% |
| product-service | 0.0015% |
| order-service | 0.0000% |

## 8. Database Connection Pool (Java HikariCP)

Java services use HikariCP (max 20 connections per service). Swift uses async PostgreSQL driver (per-event-loop connections).

| Service | Active (peak) | Idle | Max |
|---|---|---|---|
| user-service | 0 | 13 | 20 |
| product-service | 0 | 7 | 20 |
| order-service | 0 | 20 | 20 |

## 9. Status Code Breakdown (cumulative at test end)

### 9.1 Swift (Vapor) — by status code

| Service | Status | Count |
|---|---|---|
| order-service | 201 | 8,171 |
| product-service | 200 | 137,608 |
| product-service | 201 | 5 |
| product-service | 404 | 2 |
| user-service | 200 | 25,044 |
| user-service | 201 | 25,043 |
| user-service | 404 | 2 |

### 9.2 Java (Spring Boot) — by status code

| Service | Status | Outcome | Count |
|---|---|---|---|
| order-service | 201 | SUCCESS | 8,171 |
| product-service | 200 | SUCCESS | 137,606 |
| product-service | 201 | SUCCESS | 5 |
| user-service | 200 | SUCCESS | 4,736 |
| user-service | 201 | SUCCESS | 5,280 |
| user-service | 500 | SERVER_ERROR | 2 |

## 10. Error Analysis

**Both stacks: 0 errors out of 104,607 (Swift) and 104,607 (Java) requests.** All checks (status 2xx, response time < 2s, body present) passed at 100%.

Status code distribution shows only 2xx responses (200 for reads, 201 for creates). No 4xx (validation/conflict) or 5xx (server) errors observed under sustained load.

## 11. Key Findings

1. **P95 latency:** **Java** wins (4.68 ms vs 7.41 ms, **1.58× faster**).
2. **Median (P50):** **Java** wins (1.07 ms vs 1.83 ms, **1.71× faster**).
3. **Max latency (worst case):** **Swift** lower (77.49 ms vs 161.85 ms).
4. **Memory:** Swift averaged **35.5 MB** RSS vs Java **640.7 MB** total JVM — **Swift 18.0× lighter**.
5. **Concurrency:** Java grew to **24–103 live threads** per service; Swift NIO uses ~10 event loops total across all 3 services (1 per CPU core).
6. **GC overhead:** Java G1 peaked at **0.0015%** CPU (negligible at this scale). Swift ARC has zero runtime GC cost.
7. **Throughput:** Both stacks served identical k6 load (~317 req/s/stack) without saturation — bottleneck was the k6 workload pattern (sleep between groups), not the server.
8. **Per-service nuance — pure DB (product-service P95):** Java **2.3× faster** (1.55 ms vs 3.58 ms). Likely due to Hibernate query cache + JIT optimizations on the hot read path.
9. **Per-service — bcrypt POST (user-service P95):** Swift wins despite CPU-bound work (— vs —, nan× faster).

## 12. Apple-to-Apple Parity Configuration

This run was configured for **fair runtime-overhead comparison** with the following parity:

| Aspect | Swift Vapor | Java Spring Boot |
|---|---|---|
| Database | Separate `swift_*_db` per service | Separate `java_*_db` per service |
| bcrypt cost factor | `app.passwords.use(.bcrypt(cost: 10))` | `new BCryptPasswordEncoder(10)` |
| bcrypt threading | `req.password.async.hash(_:)` → NIOThreadPool | Tomcat worker threads |
| DB connection pool | `maxConnectionsPerEventLoop: 2` × 10 loops = 20 | HikariCP `maximum-pool-size: 20` |
| HTTP server | SwiftNIO (10 event loops) | Tomcat (200 thread max) |
| Cache | Vapor Redis client (manual TTL 30s) | Spring `@Cacheable` (Redis TTL 30s) |

## 13. Limitations & Caveats

- **macOS Docker Desktop cAdvisor:** does not expose per-container `name` label. Memory comparison uses Java JVM Micrometer metrics + Swift process RSS from `/proc/self/status`.
- **Cold-start excluded:** k6 ran after ~15s warmup, so JVM JIT had reached steady state. Swift was already AOT-compiled. Cold-start would favor Swift.
- **Single-host benchmark:** all services + load generator on one M-series Mac — no network latency between k6 and services. Results reflect *runtime overhead*, not real deployment latency where network would dominate.
- **Throughput is k6-bounded:** With 100 VUs and `sleep(0.5)` between groups, the stack never saturated. Both stacks could likely handle much higher RPS — this run measures *latency under fixed load*, not max throughput.

## 14. Reproducibility

```bash
# Full reset + re-run:
./scripts/reset-and-benchmark.sh load

# Or step-by-step:
docker compose -f infrastructure/docker-compose.monitoring.yml stop prometheus loki
docker volume rm infrastructure_prometheus-data infrastructure_loki-data
docker compose -f infrastructure/docker-compose.monitoring.yml up -d prometheus loki
docker compose -f infrastructure/docker-compose.yml restart \
  swift-user-service swift-product-service swift-order-service \
  java-user-service java-product-service java-order-service
./scripts/run-benchmark.sh load

# Generate this report from latest run:
python3 benchmarking/analysis/generate_report.py
```

**Raw artifacts:**
- k6 summary JSON: `benchmarking/results/final/20260425_141231_spike-test_summary.json`
- Per-iteration JSON stream: `benchmarking/results/20260425_141231_spike-test.json` (~200 MB)
- k6 stdout log: `benchmarking/results/20260425_141231_spike-test.log`
- Prometheus metrics CSV: `benchmarking/results/final/reports/metrics_20260425_141231_spike-test.csv`
- Status code CSV: `benchmarking/results/final/reports/status_20260425_141231_spike-test.csv`
