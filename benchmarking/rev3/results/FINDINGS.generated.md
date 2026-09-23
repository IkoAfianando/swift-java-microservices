# Findings

Every number on this page is produced by `benchmarking/rev3/analyze.py` from the raw
run output in `benchmarking/rev3/results/`. Nothing here is typed by hand. Rebuild it
with `./scripts/reproduce.sh --analyse-only`.

Runs analysed: **80**. Repetitions per configuration and scenario: **5**.

## How to read this

The unit of analysis is the run, not the request. Latency distributions are skewed, so
the centre is a median and the interval is a bootstrap 95 percent interval of the
median over 10,000 resamples. Configurations are compared with a two sided
Mann-Whitney U test, with the Vargha and Delaney A12 effect size beside it. With five
observations per side the smallest attainable p value is 0.008, so a non significant
result means the design could not resolve the difference, not that none exists.

Results describe the tested configurations and workloads on the hardware recorded in
`benchmarking/rev3/results/environment.json`. They are not claims about Swift Vapor or
Spring Boot in general.

## Tail latency, client measured, milliseconds

| Scenario | Vapor | Spring Boot, Tomcat 200 | Spring Boot, Tomcat 64 | Spring Boot, virtual threads |
|---|---|---|---|---|
| Load | 1199.2 [1096.0, 1288.4] | 2587.8 [2496.5, 2689.1] | 2588.5 [2584.4, 2605.9] | 836.3 [767.8, 1066.1] |
| Stress | 23206.3 [21607.9, 24198.0] | 33312.8 [33078.8, 34432.2] | 28295.2 [27802.5, 31296.4] | 21990.3 [19681.5, 22411.1] |
| Spike | 14.7 [13.5, 15.9] | 15.3 [14.4, 18.0] | 14.8 [14.4, 16.4] | 13.8 [11.4, 14.7] |
| Sustained | 98.4 [89.8, 124.6] | 122.6 [110.1, 177.6] | 115.5 [104.4, 133.0] | 264.7 [253.9, 455.5] |

Median P95 with its 95 percent interval. Full per run values are in
`results/analysis/runs_long.csv`.

## Throughput, requests per second

| Scenario | Vapor | Spring Boot, Tomcat 200 | Spring Boot, Tomcat 64 | Spring Boot, virtual threads |
|---|---|---|---|---|
| Load | 46.2 [46.1, 47.5] | 37.7 [37.1, 38.2] | 37.8 [37.5, 38.5] | 47.1 [46.3, 47.9] |
| Stress | 35.9 [35.7, 36.3] | 24.7 [24.5, 25.0] | 25.1 [24.1, 25.2] | 47.3 [45.5, 48.7] |
| Spike | 431.3 [430.4, 432.0] | 432.7 [429.0, 433.0] | 431.4 [430.9, 433.0] | 433.8 [432.5, 436.3] |
| Sustained | 25.7 [25.6, 25.8] | 25.6 [25.5, 25.7] | 25.6 [25.6, 25.7] | 25.1 [24.5, 25.2] |

## Memory, megabytes

Resident set size is summed over the three service containers of a stack and is the
only quantity compared across stacks, because a resident set size and a virtual machine
heap are not the same thing. Heap figures exist only on the JVM and are listed
separately in `results/analysis/memory.csv`.

| Scenario | Vapor | Spring Boot, Tomcat 200 | Spring Boot, Tomcat 64 | Spring Boot, virtual threads |
|---|---|---|---|---|
| Load | 40 [38, 50] | 1033 [1012, 1082] | 1026 [998, 1048] | 1014 [979, 1058] |
| Stress | 52 [51, 52] | 1042 [1004, 1074] | 1018 [973, 1082] | 1080 [1044, 1157] |
| Spike | 46 [45, 46] | 1054 [999, 1061] | 1034 [998, 1123] | 1044 [1033, 1062] |
| Sustained | 36 [36, 36] | 1030 [979, 1037] | 1017 [949, 1037] | 1012 [953, 1028] |

## Significance, Vapor against each Spring Boot configuration

| Scenario | Comparison | median Vapor | median other | p | A12 | separated at 0.05 |
|---|---|---|---|---|---|---|
| Load | Vapor vs Spring Boot, Tomcat 200 | 1199.2254 | 2587.7677 | 0.00794 | 0.000 | yes |
| Load | Vapor vs Spring Boot, Tomcat 64 | 1199.2254 | 2588.5329 | 0.00794 | 0.000 | yes |
| Load | Vapor vs Spring Boot, virtual threads | 1199.2254 | 836.2696 | 0.00794 | 1.000 | yes |
| Stress | Vapor vs Spring Boot, Tomcat 200 | 23206.3438 | 33312.7670 | 0.00794 | 0.000 | yes |
| Stress | Vapor vs Spring Boot, Tomcat 64 | 23206.3438 | 28295.2465 | 0.00794 | 0.000 | yes |
| Stress | Vapor vs Spring Boot, virtual threads | 23206.3438 | 21990.2962 | 0.05556 | 0.880 | no |
| Spike | Vapor vs Spring Boot, Tomcat 200 | 14.7289 | 15.3090 | 0.30952 | 0.280 | no |
| Spike | Vapor vs Spring Boot, Tomcat 64 | 14.7289 | 14.8350 | 0.42063 | 0.320 | no |
| Spike | Vapor vs Spring Boot, virtual threads | 14.7289 | 13.8004 | 0.42063 | 0.680 | no |
| Sustained | Vapor vs Spring Boot, Tomcat 200 | 98.3917 | 122.5902 | 0.05556 | 0.120 | no |
| Sustained | Vapor vs Spring Boot, Tomcat 64 | 98.3917 | 115.4700 | 0.15079 | 0.200 | no |
| Sustained | Vapor vs Spring Boot, virtual threads | 98.3917 | 264.6838 | 0.00794 | 0.000 | yes |

## What changed from the first release

The first release reported single runs. Two defects were found while preparing this one
and both are reported rather than quietly fixed.

1. **The list endpoints did not return the same result set.** The Vapor services
   returned a bounded, ordered page while the Spring services returned the whole table,
   which grew as the workload inserted rows. Part of the difference the first release
   attributed to concurrency architecture was a serialisation cost the benchmark itself
   created.
2. **The measurement window counted traffic the client never issued.** Warm-up requests
   and the health probe reached the service histograms without reaching the client
   metrics, and both are much faster than a real request, so the server side percentiles
   were pulled down. Warm-up now runs in a separate process before the window opens, and
   probe and scrape traffic is removed from the server side figures.

Every number on this page comes from runs made after both fixes. The numbers in the
first release are superseded and should not be cited.

