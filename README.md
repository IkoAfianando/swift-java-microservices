# Swift Vapor and Spring Boot under identical microservice workloads

Replication package for the paper *An Apples-to-Apples Empirical Comparison of Swift Vapor
and Spring Boot Configurations for Containerized CRUD Microservices* (IITSOE 2026).

| | |
|---|---|
| Release | `v2.0-iitsoe-revision` |
| Commit | whatever the release tag resolves to |
| Permanent link | `https://github.com/IkoAfianando/swift-java-microservices` |

---

## 1. What this measures

Three microservices, user, product and order, implemented twice: once with
Swift 6 on Vapor 4, once with Java 21 on Spring Boot 3. Both implementations
expose the same endpoints, back onto the same PostgreSQL 15 and Redis 7
versions with one database per service per stack, run under the same container
resource limits, and are driven by the same k6 script.

Four configurations are compared, not two. Leaving Spring Boot at its defaults
and calling the result a language comparison would make the finding an artifact
of one arbitrary setting, so the Java side is bracketed across its
configuration space:

| Key | Configuration |
|---|---|
| `vapor` | Vapor, 2 event loops, 64 blocking threads, DB pool 10 per loop |
| `boot-t200` | Spring Boot, Tomcat platform threads, max 200, the framework default |
| `boot-t64` | Spring Boot, Tomcat platform threads, max 64, matched to the Vapor blocking pool |
| `boot-vt` | Spring Boot, virtual threads, `spring.threads.virtual.enabled` |

Four load scenarios are run against each configuration: `load`, `stress`,
`spike` and `soak`.

Measured, per run:

- Client-side latency percentiles from k6, per endpoint and in aggregate.
- Server-side latency percentiles from the stacks' own histograms, snapshotted
  at the start and the end of the measured window, so a percentile is computed
  over a stated window and not over process lifetime.
- Throughput over time, and the point at which it stops rising.
- Error rate.
- Container CPU quota utilisation and resident set size, sampled throughout.
- JVM heap used and committed, garbage collection pause count and time, busy
  Tomcat threads, HikariCP pending connections and acquire time.
- Resident set size of the load generator itself, so the cost of k6 on the
  shared host is disclosed rather than assumed away.
- A control-plane responsiveness probe against a trivial health endpoint on
  both stacks, polled at a fixed interval.

The unit of analysis is the run, not the request. Each configuration and
scenario pair is repeated five times. Runs never overlap, so the system under
test owns its CPU quota for the whole measured window. Repetitions are
interleaved rather than blocked, so an interrupted suite leaves a balanced
design rather than complete data for whichever configuration ran first, and
configuration order is rotated each repetition so that host drift over a long
session does not land on the same configuration twice.

Not measured: multi-host deployment, network latency beyond loopback,
disk-bound database workloads, and cold-start or warm-up time.

---

## 2. Reproducing every number

### Prerequisites

Docker with Compose v2, k6 0.50 or newer, Python 3.10 or newer with `numpy`,
`scipy` and `matplotlib`, and a host with at least 8 cores and 16 GB of RAM.
No Swift or Java toolchain is needed on the host; both stacks build inside
containers.

### One command

```bash
./scripts/reproduce.sh
```

That runs the four steps below in order and writes everything under
`benchmarking/rev3/results/`. It takes roughly `about 5.5 hours of wall clock for 80 runs` on the
reference hardware in section 3. It is resumable: completed runs are skipped,
so re-running after an interruption continues rather than restarts.

### The same thing in four steps

```bash
./scripts/setup.sh                                 # docker networks, .env from .env.example
python3 benchmarking/rev3/capture_environment.py   # -> results/environment.json
python3 benchmarking/rev3/run_suite.py --reps 5    # -> results/<config>_<scenario>_r<n>_*
python3 benchmarking/rev3/analyze.py               # -> results/analysis/*.csv, SUMMARY.md
python3 benchmarking/rev3/make_figures.py          # -> results/figures/*.png
```

Useful subsets:

```bash
python3 benchmarking/rev3/run_suite.py --reps 1 --scenarios load
python3 benchmarking/rev3/run_suite.py --configs vapor,boot-t200
python3 benchmarking/rev3/run_suite.py --start-rep 6 --reps 5   # add repetitions
```

### Verifying without re-running

The published results are committed. To regenerate every table and figure from
the committed data, without running any benchmark:

```bash
python3 benchmarking/rev3/analyze.py
python3 benchmarking/rev3/make_figures.py
```

The output should match the committed files in `benchmarking/rev3/results/analysis/`
and `benchmarking/rev3/results/figures/` byte for byte, except for the figure
PNGs, whose bytes depend on the matplotlib version.

---

## 3. Where each table and figure comes from

Every number in the paper is produced by a script in this repository from data
committed in this repository. Nothing is typed by hand into a table or a figure.

Table numbers below use placeholders because the manuscript is being renumbered.

### Tables

| Paper | Contents | Produced by | Output file | Column or field |
|---|---|---|---|---|
| `Table I` | Configuration parity across the four configurations | `benchmarking/rev3/run_suite.py` (`CONFIGS`) and `infrastructure/docker-compose.parity.yml` | `benchmarking/rev3/results/environment.json` | `containers.*.cpu_limit_cores`, `memory_limit_bytes`, per-config `env` |
| `Table II` | Execution environment: host, runtime versions, container limits | `benchmarking/rev3/capture_environment.py` | `benchmarking/rev3/results/environment.json` | `host`, `docker`, `runtimes`, `containers` |
| `described in the text, Method` | k6 load scenarios: shape, duration, target | `benchmarking/rev3/scenarios/bench.js` (`STAGES`) | `benchmarking/rev3/results/<run_id>_meta.json` | `scenario`, `stages` |
| `Table III` | Latency by configuration and scenario: n, median, IQR, bootstrap 95% CI | `benchmarking/rev3/analyze.py` | `benchmarking/rev3/results/analysis/aggregate.csv` | `scenario`, `config`, `config_label`, `metric`, `n`, `median`, `iqr`, `q1`, `q3`, `ci95_low`, `ci95_high` |
| `Table III, last column` | Significance: Vapor against each Spring Boot configuration | `benchmarking/rev3/analyze.py` | `benchmarking/rev3/results/analysis/significance.csv` | `config_a`, `config_b`, `median_a`, `median_b`, `U`, `p_value`, `rank_biserial`, `vargha_delaney_a12`, `significant_at_0.05`, `direction` |
| `Table IV` | Memory, with the distinct quantities kept apart and each one defined in the file | `benchmarking/rev3/analyze.py` | `benchmarking/rev3/results/analysis/memory.csv` | `quantity`, `definition`, `n`, `median_mb`, `iqr_mb`, `ci95_low_mb`, `ci95_high_mb` |
| `Table III, throughput and error columns` | Throughput and the saturation point | `benchmarking/rev3/analyze.py` | `benchmarking/rev3/results/analysis/throughput_saturation.csv` | `peak_server_rps_median`, `client_rps_median`, `error_rate_median`, `saturated`, `note` |
| `Table V` | Diagnostics behind the saturation explanation: CPU, GC, queue depth, busy threads, DB wait | `benchmarking/rev3/analyze.py` | `benchmarking/rev3/results/analysis/diagnostics.csv` | `scenario`, `config`, `metric`, `n`, `median`, `iqr`, `note` |
| `described in the text, Results` | Client-measured against server-measured percentiles | `benchmarking/rev3/analyze.py` | `benchmarking/rev3/results/analysis/client_vs_server.csv` | `client_p95_ms_median`, `server_p95_ms_median`, `difference_ms`, `ratio_client_over_server` |
| `repository only` | Per-endpoint percentiles, all scenarios and configurations | `benchmarking/rev3/analyze.py` | `benchmarking/rev3/results/analysis/endpoint_level.csv` | `endpoint`, `n`, `p95_ms_median`, `p95_ms_iqr`, `median_ms_median`, `requests_median` |
| `repository only` | Every run, every extracted metric, one row each | `benchmarking/rev3/analyze.py` | `benchmarking/rev3/results/analysis/runs_long.csv` | the full record behind every aggregate above |
| not in the paper | Throughput over time, per run, for the saturation figure | `benchmarking/rev3/analyze.py` | `benchmarking/rev3/results/analysis/throughput_timeseries.csv` | `run_id`, `config`, `scenario`, `repetition`, `seconds_into_window`, `server_rps` |

### Figures

| Paper | Contents | Produced by | Output file |
|---|---|---|---|
| `not in this revision` | Experimental procedure | not generated, drawn by hand | `docs/figures/procedure.png` |
| `not in this revision` | System architecture and measurement points | not generated, drawn by hand | `docs/figures/architecture.png` |
| `Fig. 1` | Tail latency with confidence intervals, and sustained throughput with error rate | `benchmarking/rev3/make_figures.py` | `benchmarking/rev3/results/figures/fig_latency_throughput.png` |
| `repository only` | Memory, quantities kept apart | `benchmarking/rev3/make_figures.py` | `benchmarking/rev3/results/figures/fig_memory.png` |
| `repository only` | Saturation diagnostics per scenario | `benchmarking/rev3/make_figures.py` | `benchmarking/rev3/results/figures/fig_diagnostics.png` |

`benchmarking/rev3/results/analysis/SUMMARY.md` is a readable digest of the
same analysis and is the fastest way to check a quoted number without opening
a CSV.

The two hand-drawn figures contain no measured values. Every figure that plots
data reads it from `results/analysis/*.csv`, so a figure cannot drift away from
the table it illustrates.

---

## 4. The environment the published numbers came from

`benchmarking/rev3/results/environment.json` is the authoritative record and is
generated, not written by hand. It is captured once per stack while that stack
is running, and it holds:

- Host: model identifier, CPU brand string, logical, performance and efficiency
  core counts, physical memory, operating system name, version, build and
  architecture.
- Docker: engine and Compose versions, CPU and memory granted to the Docker
  virtual machine.
- Runtimes: Swift and Vapor versions read from the build manifests and the
  builder image, JDK and Spring Boot versions, PostgreSQL and Redis versions,
  k6 version.
- Per container: image digest, CPU limit in cores, memory limit in bytes, and
  the environment variables that distinguish the configuration.

Summary of that record for the published run, to be filled from the file:

| | |
|---|---|
| Host | `Mac16,1`, `Apple M4`, `10 logical (4 performance, 6 efficiency)` cores, `16 GB` |
| Operating system | `macOS 15.7.9` (`24G830`), `arm64` |
| Docker | `29.8.0`, `10` CPUs and `8 GB` GB granted |
| Per-service limits | `1.5 cores per service container` cores and `1024 MB per service container` MB per container, set in `infrastructure/docker-compose.parity.yml` |
| Swift | `swift:6.0-jammy`, Vapor `4.99.3` |
| Java | `eclipse-temurin:21-jre-jammy`, Spring Boot `3.2.4` |
| PostgreSQL, Redis | `(PostgreSQL) 15.17`, `Redis server v=7.4.8` |
| k6 | `k6 v1.3.0 (commit/devel, go1.25.1, darwin/arm64)` |
| Suite executed | `2026-09-22 23:37 to 2026-09-23 05:04` |

All six services and the load generator run on one host. Absolute latency
figures therefore include no network beyond loopback and should not be read as
deployment numbers. The comparison between configurations is the result; the
absolute values are not.

Swift dependency versions are pinned by the committed `Package.resolved` in
each service. Java dependency versions are pinned by each `pom.xml`. Container
base images are pinned by digest in the compose files.

---

## 5. What is in this repository, and what is not

### Included

| Path | Contents |
|---|---|
| `services/swift/` | Three Vapor services: source, Dockerfile, `Package.swift`, `Package.resolved` |
| `services/java/` | Three Spring Boot services: source, Dockerfile, `pom.xml` |
| `infrastructure/` | Compose files including `docker-compose.parity.yml`, which pins per-container CPU, memory, event-loop and thread-pool settings; `init-db.sql`; `.env.example` |
| `monitoring/` | Prometheus scrape config and alert rules, provisioned Grafana dashboards, Loki and Promtail configuration |
| `benchmarking/rev3/` | The revision-3 harness: driver, sampler, environment capture, analysis, figures, k6 script |
| `benchmarking/rev3/results/` | Raw output of every published run, and the derived analysis and figures |
| `benchmarking/k6/`, `benchmarking/analysis/` | The original single-run harness, kept so the earlier results remain regenerable |
| `benchmarking/results/final/` | The April 2026 single-run campaign. Superseded. See below. |
| `scripts/` | Setup and run wrappers |

### Not included, and why

**Per-iteration k6 streams from the April 2026 campaign.** Four files totalling
1.08 GB. They are the raw input k6 reduced into the summaries that are
committed, and they contain nothing the summaries do not. GitHub rejects a
single file over 100 MB and three of these run between 270 MB and 388 MB, so a
repository containing them cannot be cloned from the link this paper quotes.
The `*_summary.json` and `*.log` files they were reduced from are committed in
full.

The revision-3 harness does not produce streams of this kind. It exports a k6
summary and samples metrics on a fixed interval, so all of its raw output is
committed with nothing withheld.

**Pilot and aborted runs from April 2026.** Twenty-nine files in
`benchmarking/results/` outside `final/`, including three runs of 536 bytes
that failed at startup. No table in any version of the paper refers to them.

**Build output.** `services/swift/*/.build/` and `services/java/*/target/`.
Regenerated by `docker compose build`. The SwiftPM checkouts under `.build/`
carry their own git metadata and cannot be committed into this repository
without breaking a clone.

**`infrastructure/.env`.** Holds local database and Grafana credentials.
`infrastructure/.env.example` carries the same keys with placeholder values and
is committed. `./scripts/setup.sh` creates the real file from it.

**Supervision material.** The research proposal, the four-month schedule and
the daily logbook template are programme administration, not experimental
artifacts, and are not part of this package.

### Superseded data, retained

`benchmarking/results/final/` holds the April 2026 campaign: one run per
scenario, both stacks driven inside the same virtual-user iteration, no
repetitions and no confidence intervals. The numbers in the accepted version of
the paper came from it. Reviewers objected to exactly that design, so the
revised paper does not use it.

It is retained rather than deleted so that the accepted version and the revised
version can both be checked against what they were computed from. Nothing in
the revised paper cites it. `benchmarking/results/final/README.md` repeats this
statement next to the data.

---

## 6. Repository layout

```
services/
  swift/{user,product,order}-service/     Vapor 4
  java/{user,product,order}-service/      Spring Boot 3
infrastructure/
  docker-compose.yml                      six services, PostgreSQL, Redis
  docker-compose.parity.yml               resource limits and pinned pool sizes
  docker-compose.monitoring.yml           Prometheus, Grafana, Loki, cAdvisor
  init-db.sql                             six isolated databases
monitoring/                               scrape config, alert rules, dashboards
benchmarking/
  rev3/                                   revision-3 harness and results
    run_suite.py sampler.py analyze.py capture_environment.py make_figures.py
    scenarios/bench.js
    results/                              raw runs, analysis/, figures/
  k6/ analysis/                           original single-run harness
  results/final/                          April 2026 campaign, superseded
scripts/                                  setup and run wrappers
FINDINGS.md                               narrative discussion
LICENSE                                   MIT
```

---

## 7. Citation

```
```bibtex
@inproceedings{afianando2026vaporboot,
  author    = {Afianando, Iko and Hardjanto, Viga Laksa and Pambudi, Pandu Dwi Luhur},
  title     = {An Apples-to-Apples Empirical Comparison of Swift Vapor and Spring Boot
               Configurations for Containerized {CRUD} Microservices},
  booktitle = {2026 Integrating Information Technology for Strategic and Operational
               Excellence (IITSOE)},
  year      = {2026},
  publisher = {IEEE}
}
```
```

Archived as release `v2.0-iitsoe-revision`. The manuscript quotes the commit identifier that this tag resolves to.
