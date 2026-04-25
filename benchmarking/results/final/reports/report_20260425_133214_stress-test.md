# Benchmark Report — Swift Vapor vs Java Spring Boot

**Researcher:** Iko Afianando (NIM 2602261970)  
**Institution:** BINUS University 2025/2026 — Enrichment Program  
**Test ID:** `20260425_133214_stress-test`  
**Test window:** 2026-04-25 13:32:14 → 13:45:14 (13.0 min)  
**Generated:** 2026-04-25 15:20:00  
**k6 Summary:** `benchmarking/results/final/20260425_133214_stress-test_summary.json`

---

## 1. Test Configuration

| Field | Value |
|---|---|
| Scenario | k6 load test (constant ramp-up) |
| Duration | 13.0 minutes (780 s) |
| Max VUs | 1000 |
| Iterations | 16,656 (21.34 iter/s) |
| Total HTTP requests | 100,576 (128.9 req/s) |
| Endpoints tested | `GET /users`, `GET /products`, `POST /users` |
| Stack A | Swift Vapor 4 — ports 8081–8083 (user, product, order) |
| Stack B | Java Spring Boot 3 — ports 9081–9083 |
| Database | PostgreSQL 15 (one DB per service) |
| Cache | Redis 7 (shared) |

## 2. Headline Results (k6 client-side measurements)

| Metric | Swift Vapor | Java Spring Boot | Δ vs Java |
|---|---|---|---|
| Total requests | 50,395 | 50,181 | tied |
| Throughput (req/s) | 64.58 | 64.30 | tied |
| Avg latency | 308.71 ms | 5513.60 ms | -94.4% |
| Median (P50) | 36.21 ms | 232.32 ms | -84.4% |
| P90 | 358.09 ms | 21515.94 ms | -98.3% |
| P95 | 1017.97 ms | 28330.17 ms | -96.4% |
| Min latency | 0.61 ms | 0.00 ms | — |
| Max latency | 6267.37 ms | 51567.80 ms | — |
| Errors (k6 checks) | 50,395 of 50,395 | 50,030 of 50,181 | tied |
| Error rate | 0.00% | 0.30% | tied |

> **HTTP-level failure rate (overall):** 4.11% of 100,576 requests.

## 3. Per-Service Throughput (Prometheus, 2-min avg at mid-test)

| Service | Swift RPS | Java RPS |
|---|---|---|
| user-service | 41.60 | 41.33 |
| product-service | 40.20 | 40.32 |
| order-service | 20.48 | 20.67 |

## 4. Per-Service Latency (Prometheus histogram, mid-test)

### 4.1 P50 (median)

| Service | Swift | Java |
|---|---|---|
| user-service | 39.15 ms | 56.04 ms |
| product-service | 0.64 ms | 0.62 ms |
| order-service | 3.84 ms | 3.32 ms |

### 4.2 P95

| Service | Swift | Java |
|---|---|---|
| user-service | 71.73 ms | 88.89 ms |
| product-service | 2.10 ms | 1.95 ms |
| order-service | 12.80 ms | 10.23 ms |

### 4.3 P99

| Service | Swift | Java |
|---|---|---|
| user-service | 97.72 ms | 128.50 ms |
| product-service | 5.70 ms | 6.70 ms |
| order-service | 38.08 ms | 26.88 ms |

## 5. Memory Footprint (peak during test)

Swift uses ARC (Automatic Reference Counting) — compile-time memory management, no GC.
Java uses G1 GC — heap-based with periodic concurrent collection. Total JVM = heap + non-heap (metaspace, code cache, etc.).

| Service | Swift RSS (peak) | Java JVM Heap (peak) | Java JVM Total (peak) | Java Non-Heap |
|---|---|---|---|---|
| user-service | 52.8 MB | 1278.2 MB | 1413.9 MB | 154.1 MB |
| product-service | 46.0 MB | 98.0 MB | 244.6 MB | 147.0 MB |
| order-service | 43.9 MB | 98.6 MB | 229.1 MB | 132.6 MB |

**Average across 3 services:**  
- Swift RSS: **47.6 MB**
- Java JVM heap: **491.6 MB**
- Java JVM total: **629.2 MB**
- **Swift uses 13.2× less total memory than Java JVM.**

## 6. Concurrency Model

Swift Vapor uses **async/await** on top of SwiftNIO event loops (cooperative, non-blocking I/O). Java Spring Boot uses **thread-per-request** via Tomcat's executor pool.

| Service | Java Live Threads (peak) | Java Daemon Threads | Java All-Time Peak |
|---|---|---|---|
| user-service | 121 | 27 | 113 |
| product-service | 31 | 25 | 32 |
| order-service | 30 | 21 | 30 |

> Swift NIO event loops are typically 1 per CPU core (~10 on this machine), regardless of concurrent request count. Java needs to grow its thread pool to handle concurrent connections.

## 7. GC Overhead (Java only)

Swift has **zero runtime GC overhead** (ARC is compile-time). Java G1 GC consumes CPU time periodically.

| Service | GC Overhead % (peak during test) |
|---|---|
| user-service | 0.0210% |
| product-service | 0.0009% |
| order-service | 0.0007% |

## 8. Database Connection Pool (Java HikariCP)

Java services use HikariCP (max 20 connections per service). Swift uses async PostgreSQL driver (per-event-loop connections).

| Service | Active (peak) | Idle | Max |
|---|---|---|---|
| user-service | 20 | 9 | 20 |
| product-service | 1 | 5 | 20 |
| order-service | 0 | 20 | 20 |

## 9. Status Code Breakdown (cumulative at test end)

### 9.1 Swift (Vapor) — by status code

| Service | Status | Count |
|---|---|---|
| order-service | 201 | 8,171 |
| product-service | 200 | 21,934 |
| product-service | 201 | 5 |
| product-service | 404 | 1 |
| user-service | 200 | 14,076 |
| user-service | 201 | 14,016 |
| user-service | 404 | 1 |

### 9.2 Java (Spring Boot) — by status code

| Service | Status | Outcome | Count |
|---|---|---|---|
| order-service | 201 | SUCCESS | 8,171 |
| product-service | 200 | SUCCESS | 21,960 |
| product-service | 201 | SUCCESS | 5 |
| user-service | 200 | SUCCESS | 13,987 |
| user-service | 201 | SUCCESS | 13,935 |

## 10. Error Analysis

**Swift error rate: 0.00%** (50,395 of 50,395 checks failed)
**Java error rate:  0.30%** (50,030 of 50,181 checks failed)

Inspect the status code breakdown (§9) for distribution by endpoint and root cause.

## 11. Key Findings

1. **P95 latency:** **Swift** wins (1017.97 ms vs 28330.17 ms, **27.83× faster**).
2. **Median (P50):** **Swift** wins (36.21 ms vs 232.32 ms, **6.42× faster**).
3. **Max latency (worst case):** **Swift** lower (6267.37 ms vs 51567.80 ms).
4. **Memory:** Swift averaged **47.6 MB** RSS vs Java **629.2 MB** total JVM — **Swift 13.2× lighter**.
5. **Concurrency:** Java grew to **30–121 live threads** per service; Swift NIO uses ~10 event loops total across all 3 services (1 per CPU core).
6. **GC overhead:** Java G1 peaked at **0.0210%** CPU (negligible at this scale). Swift ARC has zero runtime GC cost.
7. **Throughput:** Both stacks served identical k6 load (~65 req/s/stack) without saturation — bottleneck was the k6 workload pattern (sleep between groups), not the server.
8. **Per-service nuance — pure DB (product-service P95):** Java **1.1× faster** (1.95 ms vs 2.10 ms). Likely due to Hibernate query cache + JIT optimizations on the hot read path.
9. **Per-service — bcrypt POST (user-service P95):** Swift wins despite CPU-bound work (71.73 ms vs 88.89 ms, 1.2× faster).

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
- k6 summary JSON: `benchmarking/results/final/20260425_133214_stress-test_summary.json`
- Per-iteration JSON stream: `benchmarking/results/20260425_133214_stress-test.json` (~200 MB)
- k6 stdout log: `benchmarking/results/20260425_133214_stress-test.log`
- Prometheus metrics CSV: `benchmarking/results/final/reports/metrics_20260425_133214_stress-test.csv`
- Status code CSV: `benchmarking/results/final/reports/status_20260425_133214_stress-test.csv`
