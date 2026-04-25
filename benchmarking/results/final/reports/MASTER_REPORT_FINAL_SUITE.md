# MASTER REPORT — Swift Vapor vs Java Spring Boot

**Researcher:** Iko Afianando (NIM 2602261970)  
**Institution:** BINUS University 2025/2026 — Enrichment Program  
**Suite ID:** `FINAL_SUITE`  
**Scenarios run:** 4  
**Generated:** 2026-04-25 15:20:00

---

## 1. Suite Summary

| Scenario | VUs (max) | Iterations | Total Reqs | Duration | HTTP Failed |
|---|---|---|---|---|---|
| **load-test** | 100 | 8,171 | 65,388 | 10.0 min | 0.00% |
| **stress-test** | 1000 | 16,656 | 100,576 | 13.0 min | 4.11% |
| **spike-test** | 200 | 104,607 | 418,428 | 5.5 min | 0.00% |
| **soak-test** | 30 | 29,704 | 106,960 | 40.0 min | 0.00% |

## 2. Latency Comparison Across Scenarios (k6 client-side)

### 2.1 Median (P50)

| Scenario | Swift P50 | Java P50 | Winner | Margin |
|---|---|---|---|---|
| load-test | 3.89 ms | 5.83 ms | 🟢 Swift | 1.50× faster |
| stress-test | 36.21 ms | 232.32 ms | 🟢 Swift | 6.42× faster |
| spike-test | 1.83 ms | 1.07 ms | 🔴 Java | 1.71× faster |
| soak-test | 3.82 ms | 30.33 ms | 🟢 Swift | 7.94× faster |

### 2.2 P95

| Scenario | Swift P95 | Java P95 | Winner | Margin |
|---|---|---|---|---|
| load-test | 60.03 ms | 74.01 ms | 🟢 Swift | 1.23× faster |
| stress-test | 1017.97 ms | 28330.17 ms | 🟢 Swift | 27.83× faster |
| spike-test | 7.41 ms | 4.68 ms | 🔴 Java | 1.58× faster |
| soak-test | 57.58 ms | 231.16 ms | 🟢 Swift | 4.01× faster |

### 2.3 Max latency (worst-case observed)

| Scenario | Swift Max | Java Max | Winner |
|---|---|---|---|
| load-test | 232.43 ms | 348.73 ms | 🟢 Swift |
| stress-test | 6267.37 ms | 51567.80 ms | 🟢 Swift |
| spike-test | 77.49 ms | 161.85 ms | 🟢 Swift |
| soak-test | 614.09 ms | 1623.61 ms | 🟢 Swift |

## 3. Throughput & Error Rate

| Scenario | Swift RPS | Java RPS | Swift Err % | Java Err % |
|---|---|---|---|---|
| load-test | 54.36 | 54.36 | 0.00% | 0.00% |
| stress-test | 64.58 | 64.30 | 0.00% | 0.30% |
| spike-test | 316.80 | 316.80 | 0.00% | 0.00% |
| soak-test | 22.27 | 22.27 | 0.00% | 0.00% |

## 4. Verdict per Scenario

### load-test

| Metric | Winner | Detail |
|---|---|---|
| P50 | **Swift** | 3.89ms vs 5.83ms |
| P95 | **Swift** | 60.03ms vs 74.01ms |
| Max | **Swift** | 232.43ms vs 348.73ms |
| Errors | **Tied** | 0.00% vs 0.00% |

*See: [report_20260425_133214_load-test.md](./report_20260425_133214_load-test.md)*

### stress-test

| Metric | Winner | Detail |
|---|---|---|
| P50 | **Swift** | 36.21ms vs 232.32ms |
| P95 | **Swift** | 1017.97ms vs 28330.17ms |
| Max | **Swift** | 6267.37ms vs 51567.80ms |
| Errors | **Swift** | 0.00% vs 0.30% |

*See: [report_20260425_133214_stress-test.md](./report_20260425_133214_stress-test.md)*

### spike-test

| Metric | Winner | Detail |
|---|---|---|
| P50 | **Java** | 1.07ms vs 1.83ms |
| P95 | **Java** | 4.68ms vs 7.41ms |
| Max | **Swift** | 77.49ms vs 161.85ms |
| Errors | **Tied** | 0.00% vs 0.00% |

*See: [report_20260425_141231_spike-test.md](./report_20260425_141231_spike-test.md)*

### soak-test

| Metric | Winner | Detail |
|---|---|---|
| P50 | **Swift** | 3.82ms vs 30.33ms |
| P95 | **Swift** | 57.58ms vs 231.16ms |
| Max | **Swift** | 614.09ms vs 1623.61ms |
| Errors | **Tied** | 0.00% vs 0.00% |

*See: [report_20260425_142729_soak-test.md](./report_20260425_142729_soak-test.md)*

## 5. Apple-to-Apple Parity Configuration

All scenarios in this suite use the SAME parity setup:

| Aspect | Swift Vapor | Java Spring Boot |
|---|---|---|
| Database | Separate `swift_*_db` per service | Separate `java_*_db` per service |
| bcrypt cost factor | `app.passwords.use(.bcrypt(cost: 10))` | `new BCryptPasswordEncoder(10)` |
| bcrypt threading | `req.password.async.hash(_:)` → NIOThreadPool | Tomcat worker threads |
| DB connection pool | `maxConnectionsPerEventLoop: 2` × 10 = 20 | HikariCP `maximum-pool-size: 20` |
| HTTP server | SwiftNIO (10 event loops) | Tomcat (200 thread max) |
| Histogram buckets | **72 buckets matching Micrometer defaults** | Spring Boot Micrometer defaults |
| Cache | Vapor Redis client (manual TTL 30s) | Spring `@Cacheable` (Redis TTL 30s) |

> Histogram buckets are **bit-for-bit identical** between stacks, ensuring `histogram_quantile()` interpolation produces objective and comparable percentiles.

## 6. Per-Scenario Reports

- [load-test](./report_20260425_133214_load-test.md)
- [stress-test](./report_20260425_133214_stress-test.md)
- [spike-test](./report_20260425_141231_spike-test.md)
- [soak-test](./report_20260425_142729_soak-test.md)
