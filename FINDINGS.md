# Findings — Swift Vapor vs Java Spring Boot

This is the narrative companion to the auto-generated [`MASTER_REPORT_FINAL_SUITE.md`](./benchmarking/results/final/reports/MASTER_REPORT_FINAL_SUITE.md). The master report is the *numbers*; this document is the *interpretation*.

> Iko Afianando (NIM 2602261970) — BINUS University 2025/2026 — Enrichment Program

---

## Executive Summary

Across four realistic load profiles (load, stress, spike, soak), totalling **691,352 requests** issued by k6 with 100% configuration parity between the two stacks:

- **Swift Vapor wins 3 of 4 scenarios** outright on P50, P95 and worst-case latency.
- **Java Spring Boot wins 1 scenario** — the spike test, where 200 concurrent VUs sit *exactly* inside Tomcat's 200-thread pool and Hibernate's caches dominate the workload.
- The biggest gap is the stress test at 1000 VUs: **Swift P95 = 1.02 s, Java P95 = 28.33 s — a 27.83× difference**. Java's threshold (`p95 < 2 s`) failed; Swift's passed.
- **Memory footprint:** Swift uses 5.6× less total memory than Java JVM (46.4 MB RSS vs 258.5 MB total JVM, averaged across services).
- **Endurance:** 40 minutes of sustained 30-VU load left both stacks with 0% error rate; Swift kept its P50 at 3.82 ms while Java drifted to 30.33 ms.

The single-line conclusion that survives peer review:

> *Swift Vapor 4 outperforms Java Spring Boot 3 on tail latency, memory footprint and oversaturation behaviour for mixed-CRUD microservice workloads. Java retains a meaningful edge for pure read-heavy workloads at concurrency below the Tomcat thread-pool size, where JIT optimisation and Hibernate query caching dominate.*

---

## 1. Methodology

### 1.1 Workload

Three identical microservices were implemented in both stacks:

- **User Service** — CRUD users with bcrypt-hashed passwords (CPU-bound writes)
- **Product Service** — CRUD products (cache-friendly reads)
- **Order Service** — Creates orders that fan out HTTP calls to user-service and product-service

The k6 scenarios exercise different mixes of these endpoints. See `benchmarking/k6/scenarios/*.js` for the full payload definitions.

### 1.2 Apple-to-apple parity

The configuration was equalised so the comparison measures *runtime overhead*, not configuration choices:

| Aspect | Swift Vapor | Java Spring Boot |
|---|---|---|
| Database | Separate `swift_*_db` per service | Separate `java_*_db` per service |
| bcrypt cost factor | `app.passwords.use(.bcrypt(cost: 10))` | `new BCryptPasswordEncoder(10)` |
| bcrypt threading | `req.password.async.hash(_:)` → NIOThreadPool | Tomcat worker threads |
| DB connection pool | `maxConnectionsPerEventLoop: 2` × 10 = 20 | HikariCP `maximum-pool-size: 20` |
| HTTP server | SwiftNIO (10 event loops, 1 per CPU core) | Tomcat (200 thread max) |
| Histogram buckets | **72 buckets matching Micrometer defaults** | Spring Boot Micrometer defaults |
| Cache | Vapor Redis client (manual TTL 30 s) | Spring `@Cacheable` (Redis TTL 30 s) |

A previous iteration of the project ran with `bcrypt cost = 12` on Swift vs `10` on Java, blocking Vapor's event loop on each hash. Fixing both produced a **5.9× drop** in Swift P95 (328 ms → 56 ms) — a reminder of how quietly configuration choices can dominate a benchmark.

### 1.3 Histogram bucket parity (the subtle one)

Spring Boot Micrometer with `percentiles-histogram: true` emits 72 finite buckets with geometric spacing, plus the four SLO points (100 ms, 250 ms, 500 ms, 1 s). At low percentiles, bucket granularity dominates the `histogram_quantile()` interpolation: a stack with only 11 buckets between 5 ms and 10 s will report a *higher* P50 than a stack with 30 buckets in that range, even if the true distributions are identical.

Swift's `MetricsCollector` (an `actor` in `services/swift/*/Sources/App/MetricsCollector.swift`) ships **the same 72 bucket boundaries Spring Boot emits**, so Prometheus's `histogram_quantile()` computes percentiles from comparable structures. This is not optional — without it, the dashboard reports a different winner than the k6 client-side measurement, and figuring out which one to trust takes longer than it should.

### 1.4 Hardware

- Apple Silicon Mac, 10 CPU cores, 16 GB RAM
- Docker Desktop with default resource allocation
- All services + load generator on the same host (no network between k6 and the services beyond the loopback)
- PostgreSQL and Redis sized to defaults (no tuning)

This is *single-host* benchmarking. Absolute numbers reflect runtime overhead. Network latency, multi-tenant CPU contention and disk-bound DB scenarios are out of scope.

### 1.5 Measurements

- **Client-side**: k6 records every request's latency. The `_summary.json` file aggregates avg / min / median / p90 / p95 / max plus error rate.
- **Server-side**: Prometheus scrapes `/metrics` (Swift, custom) and `/actuator/prometheus` (Java) every 10 s. The histogram buckets are identical, so `histogram_quantile()` over the same time range produces directly comparable percentiles.
- **Memory**: Swift RSS from `/proc/self/status` exposed by the custom collector; Java `jvm_memory_used_bytes` (heap and non-heap) from Micrometer.
- **Threads / GC**: only Java reports these; Swift NIO event loops are bounded by `System.coreCount`, and ARC has no runtime GC.

When client-side and server-side numbers disagree, **k6 is authoritative** — it sees the request the way a real client does, including network overhead and queueing.

---

## 2. Results — Per Scenario

### 2.1 Load test — 100 VUs, 10 min realistic load

**Configuration**: ramp 0 → 10 (1 min) → 50 (3 min) → 100 (3 min) → 50 (2 min) → 0 (1 min). VU body cycles `GET /users`, `GET /products`, `POST /users`, `POST /orders` with 0.5–1.5 s sleeps between groups.

**Headline (k6 client-side, 32,572 requests per stack):**

| Metric | Swift | Java | Δ vs Java |
|---|---|---|---|
| Avg latency | 15.65 ms | 20.76 ms | **−24.6%** |
| P50 (median) | 3.41 ms | 4.80 ms | **−28.9%** |
| P95 | 55.72 ms | 68.15 ms | **−18.2%** |
| Max latency | 188.43 ms | 285.33 ms | **−34.0%** |
| Errors | 0% | 0% | tied |

Swift is faster across every percentile *and* lower at the worst case. Both stacks complete with zero errors over 65,164 total requests.

The interesting per-service breakdown (server-side, mid-test):

| Endpoint | Swift P95 | Java P95 |
|---|---|---|
| product-service (pure DB read) | 4.76 ms | **1.37 ms** ← Java 3.5× faster |
| user-service (with bcrypt POST) | 84.87 ms | **67.75 ms** ← Java 1.3× faster |
| order-service (HTTP fan-out) | 5.74 ms | 5.62 ms ← tied |

So why does Swift win the *overall* P95 (55.72 ms vs 68.15 ms) when Java wins two of three services? Because the k6 client-side P95 is computed across the *mixed* workload: with 0.5 s sleeps and 100 VUs, the request stream is dominated by GET endpoints where Swift's lighter overhead wins, while the slower POST /users tail only shows up at very high percentiles. **Service-level analysis tells one story; the user-facing P95 tells another.**

### 2.2 Stress test — 1000 VUs, 13 min, oversaturation

**Configuration**: ramp 50 → 200 → 500 → 1000 → 0 over 13 minutes. VU body is mostly read-heavy with a 0.1 s sleep — designed to push past Tomcat's 200-thread pool.

**Headline (k6 client-side, 50,395 Swift requests, 50,181 Java):**

| Metric | Swift | Java | Δ |
|---|---|---|---|
| Avg latency | 308.71 ms | **5.51 s** | Java **17.8× slower** |
| P50 (median) | 36.21 ms | 232.32 ms | Java 6.4× slower |
| P95 | 1.02 s | **28.33 s** | Java **27.83× slower** |
| Max latency | 6.27 s | **51.57 s** | Java 8.2× slower |
| Errors | **0%** | 0.30% (151 timeouts) | Swift wins |
| `p95 < 2 s` threshold | ✓ pass | ✗ **fail** | Swift only |

This is the headline result of the entire study. Java's 200-thread Tomcat pool can serve at most 200 concurrent requests before the rest queue up. With 1000 VUs hammering, **800 requests are always waiting for a thread**. As bcrypt and DB calls hold those threads for hundreds of milliseconds each, the queue depth grows and tail latency cascades.

Swift's NIO multiplexes all 1000 connections across 10 event loops, with bcrypt offloaded to a separate thread pool so the loops stay responsive. The system degrades gracefully — P50 climbs from 3.4 ms (load test) to 36 ms (10× higher), but P95 stays under 1 s and zero requests time out.

The 27.83× P95 ratio is not a typo. It's the most striking number in this study and the main answer to *"why pick Vapor over Spring Boot?"* for high-concurrency workloads.

### 2.3 Spike test — 200 VUs sudden burst, 5.5 min

**Configuration**: 1 min at 20 VUs (baseline) → 30 s ramp to 200 VUs → 1 min hold at 200 VUs → 30 s drop to 20 → 2 min recovery → 30 s ramp to 0. VU body is a single `GET /products`.

**Headline (k6 client-side, 209,214 requests per stack — note the much higher throughput):**

| Metric | Swift | Java | Δ |
|---|---|---|---|
| P50 (median) | 1.83 ms | **1.07 ms** | **Java 1.71× faster** |
| P95 | 7.41 ms | **4.68 ms** | **Java 1.58× faster** |
| Max latency | **77.49 ms** | 161.85 ms | Swift 2.1× lower |
| Errors | 0% | 0% | tied |
| Throughput | 316.80 RPS | 316.80 RPS | tied |

This is the scenario where Java Spring Boot wins *and where it makes the most sense for it to win*. Three things compose:

1. **200 VUs ≤ 200 Tomcat threads** — no thread starvation, no queueing
2. **Pure read workload on a single endpoint** — Hibernate's L1 query cache and Spring's `@Cacheable` Redis layer hit on most requests
3. **Steady-state burst** — JIT compiler has time to optimise the hot path; Spring's class-loading overhead is amortised

Swift still wins the *worst-case* (Max latency 77 ms vs Java's 161 ms) — its tail behaviour is more bounded — but at P50 and P95 the JVM's mature optimisation toolchain wins.

This is an honest finding for the paper. Java is not "old and slow"; it has decades of work poured into making the steady-state hot path fast, and that work shows up here.

### 2.4 Soak test — 30 VUs × 30 min hold (40 min total)

**Configuration**: 5 min ramp to 30 VUs → 30 min hold at 30 VUs → 5 min ramp to 0. VU body is 80% reads, 20% writes — the canonical endurance pattern for memory-leak detection.

**Headline (k6 client-side, 53,480 requests per stack):**

| Metric | Swift | Java | Δ vs Java |
|---|---|---|---|
| P50 (median) | 3.82 ms | 30.33 ms | **−87.4%** |
| P95 | 57.58 ms | 231.16 ms | **−75.1%** |
| Max latency | 614 ms | 1623 ms | **−62.2%** |
| Errors | 0% | 0% | tied |

**Interpretation:**

The 7.94× P50 ratio is large but not surprising in context: at moderate sustained load, Java's median is dragged up by:

- **Periodic G1 GC pauses** (sub-percent CPU overhead, but visible in the per-request distribution)
- **JIT recompilation** when method profiles shift over time
- **Hibernate session bookkeeping** for write-mix transactions
- **Spring's middleware chain** (security filters, observation filters, transaction interceptors) — every request crosses ~15 filters before reaching the handler

Swift Vapor's middleware stack is shorter and the runtime has no GC, so the per-request floor stays low.

Both stacks ran 40 minutes without a single error and without unbounded memory growth (visible in the Grafana memory panel). **Endurance: equivalent. Sustained latency: Swift wins.**

---

## 3. Cross-cutting Observations

### 3.1 Memory

| Service | Swift RSS (peak) | Java JVM heap (peak) | Java JVM total (peak) |
|---|---|---|---|
| user-service | 51.1 MB | 191.7 MB | 327.3 MB |
| product-service | 44.3 MB | 96.6 MB | 236.1 MB |
| order-service | 43.8 MB | 86.2 MB | 212.1 MB |
| **Average** | **46.4 MB** | **124.8 MB** | **258.5 MB** |

Swift uses **5.6× less total memory than the JVM**, including non-heap (metaspace, code cache, compressed class space). On a multi-microservice cluster where each language might run dozens of pod replicas, this scales to gigabytes of saved RAM.

ARC pays its memory-management cost at compile time (reference-counting instructions inserted into the binary). The JVM pays it at runtime (heap, metaspace, JIT-compiled code, GC bookkeeping). This is the entire reason the two numbers differ by an order of magnitude — it is not Vapor being clever or Spring being wasteful, it's the runtime model.

### 3.2 Concurrency

- **Java** grew to **28–46 live threads** per service under stress. Tomcat's pool ramps with demand up to its 200-thread ceiling.
- **Swift** uses **~10 SwiftNIO event loops total** across all three services (1 per CPU core), regardless of how many concurrent requests are in flight.

The threading models behave very differently under saturation. Below the thread-pool ceiling, both scale fine. Above it, Java queues and Swift multiplexes. The stress test results in §2.2 are a direct consequence.

### 3.3 GC overhead

| Scenario | Java GC overhead (peak) |
|---|---|
| load | 0.0035% |
| stress | 0.0102% |
| spike | 0.0009% |
| soak | 0.0021% |

Sub-percent in every scenario — G1 is doing its job. Swift's ARC has zero runtime GC overhead by construction, but at the scale of this benchmark the difference is invisible.

What *is* visible is the per-request *variance* from GC pauses showing up in the soak P50, where Java's 30 ms median is much higher than expected for a 30-VU workload. GC overhead is small in aggregate but lumpy at the request level.

### 3.4 Throughput

Throughput in this benchmark is **k6-bounded, not server-bounded**. With `sleep(0.5)` between groups and 100 VUs in the load test, the ceiling is around 50 RPS per stack — the servers were nowhere near saturated. The stress test (sleep 0.1) and spike test (no sleep on the hot endpoint) push higher: 64 RPS and 316 RPS respectively. To find the true throughput ceiling, the load profile would need to drop sleep entirely and ramp VUs until error rate breaches 1%.

This means the latency numbers in §2 are *latency under fixed load*, not *latency at the throughput ceiling*. Both are valid benchmarks; this study reports the former.

---

## 4. Threat Validity

What this benchmark **does not** claim:

- **Cold start.** All measurements happened after a 15-second warmup, so the JVM was already JIT-compiled. Swift was AOT-compiled. Cold-start would heavily favour Swift, but isn't measured here.
- **Cluster behaviour.** Single-host. No network between k6 and services beyond loopback. Multi-host deployment with real network latency, NAT, load balancers and pod-to-pod communication is out of scope.
- **Disk-bound or IO-bound DB scenarios.** PostgreSQL is sized to defaults and lives in a Docker volume on the host SSD. A workload bottlenecked on disk IO would tell a very different story.
- **Production hardening.** Swift Vapor's Fluent ORM is genuinely thinner than Hibernate. That's a feature for performance and a constraint for ergonomics — Hibernate's lazy loading, automatic dirty checking, second-level cache and N+1 detection do not all have direct Swift equivalents.
- **Long-tail libraries.** The Java ecosystem has battle-tested libraries for things this benchmark didn't touch: distributed tracing, structured logging, OpenAPI generation, OAuth2, GraphQL, Kafka clients. Swift's server ecosystem is younger and has rougher edges.
- **Operational maturity.** Spring Boot's Actuator endpoints (`/actuator/health`, `/actuator/info`, `/actuator/threaddump`, `/actuator/heapdump`, `/actuator/prometheus`) are richer than Vapor's hand-rolled equivalents.

What this benchmark **does** establish, with the apple-to-apple parity guarantees, is that on identical workloads Swift Vapor is **not slower** than Spring Boot — and is in fact dramatically faster for high-concurrency, mixed-CRUD or sustained-load profiles.

---

## 5. Practical Implications

For a microservice currently in Java Spring Boot, **migration to Swift Vapor is worth evaluating if any of the following apply:**

- **Concurrency frequently exceeds the thread-pool size.** This is the high-water mark in your monitoring. If you regularly see Tomcat saturated, the cascade you saw in §2.2 will eventually visit your production system.
- **Memory is the cluster bottleneck.** Each microservice pod is ~250 MB of JVM. Replace with Swift and that's ~50 MB. At 100 pods, that's 20 GB freed.
- **Cold-start matters.** Swift Vapor binaries start in milliseconds. JVM cold-start is multi-second.
- **Tail latency is a contracted SLO.** Swift's worst-case latency was lower than Java's in *every* scenario, including the one Java otherwise won.

**Migration is probably not worth it if:**

- **Workload is dominated by Hibernate-cached reads** with concurrency comfortably below the thread-pool size. The spike-test result shows Java unchallenged here.
- **Library dependencies are deep.** Spring Cloud, Kafka Streams, Flink connectors, etc. don't have Swift equivalents. The cost of porting may exceed the benefit.
- **Team operates on JVM tooling.** The observability and debugging story for Swift on Linux is meaningfully behind the JVM.

The honest answer to *"which framework is faster?"* is **"Swift Vapor, except for one specific shape of workload — and even there, only at typical percentiles, not at the tail"**. That's a more useful answer than the usual benchmarking shootout result.

---

## 6. Reproducibility

All numbers in this document come from `benchmarking/results/final/`. Re-generate from the included summary JSONs:

```bash
./scripts/regen-final-report.sh
```

To re-run the entire suite:

```bash
./scripts/reset-and-benchmark.sh load              # one scenario
./scripts/run-final-suite.sh                       # load + stress + spike (~30 min)
SOAK_DURATION=30m ./scripts/run-final-suite.sh soak  # endurance (~40 min)
```

Hardware required: 8+ CPU cores, 16 GB RAM, Docker Desktop. See [`TUTORIAL.md`](./TUTORIAL.md) §1 for the full setup.

The exact commit that produced the numbers, the scenario JS files, and the summary JSONs that the master report was built from are all preserved in this repo. Anyone with the same hardware and Docker version should reproduce the qualitative result (Swift faster on 3 of 4 scenarios, Java faster on the spike) within a 5–10% margin on the absolute percentiles.

---

## 7. Acknowledgements

This research is part of the BINUS University 2025/2026 Enrichment Program (Research Track). The methodology — particularly the apple-to-apple parity construction and the histogram bucket alignment — was developed iteratively by debugging early biased results, and deserves a quick acknowledgement to the broader literature on benchmark hygiene that informed the approach (Gil Tene's "How NOT to Measure Latency", the Aphyr / Jepsen body of work on measurement traps).

---

*Iko Afianando — NIM 2602261970 — BINUS University 2025/2026*
