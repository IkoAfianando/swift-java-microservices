# Manuscript figures

Two kinds of figure appear in the paper and both are generated, not drawn by
hand into a document.

| Figure | Source | Rebuild with |
|---|---|---|
| Fig. 1, system under test | `fig1_system.puml` | `java -jar plantuml.jar -tpng fig1_system.puml` |
| Fig. 2, research design | `fig2_design.puml` | `java -jar plantuml.jar -tpng fig2_design.puml` |
| Fig. 3, latency and throughput | `../../benchmarking/rev3/make_figures.py` | `python3 make_figures.py` |
| Fig. 4, diagnostics | `../../benchmarking/rev3/make_figures.py` | `python3 make_figures.py` |

Figures 3 and 4 read `benchmarking/rev3/results/analysis/*.csv`, so they cannot
drift away from the tables they illustrate. Figures 1 and 2 describe the
measured configuration and are kept in step with
`infrastructure/docker-compose.parity.yml` and `benchmarking/rev3/run_suite.py`.

The diagrams that appeared in the first version of this paper are not reused.
They described a setup in which both stacks ran at the same time, no container
carried a processor or memory quota, and the dashboard sat on the measurement
path. None of that is true of this revision.
