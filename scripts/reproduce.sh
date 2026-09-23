#!/usr/bin/env bash
# ============================================================
# Reproduce every table and figure reported in the revised paper.
#
# One command, from a clean checkout to the CSV files the manuscript is
# generated from. Expect the full suite to take several hours: runs are
# deliberately sequential, because running two stacks at once on one host is
# the measurement error this revision exists to correct.
#
# Usage:
#   ./scripts/reproduce.sh                # full suite, 5 repetitions
#   ./scripts/reproduce.sh --reps 2       # shorter, for checking the pipeline
#   ./scripts/reproduce.sh --analyse-only # re-derive tables from published data
# ============================================================
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REV3="$ROOT/benchmarking/rev3"
REPS=5
ANALYSE_ONLY=0

while [ $# -gt 0 ]; do
  case "$1" in
    --reps) REPS="$2"; shift 2 ;;
    --analyse-only) ANALYSE_ONLY=1; shift ;;
    -h|--help) sed -n '2,14p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

need() { command -v "$1" >/dev/null 2>&1 || { echo "missing required tool: $1" >&2; exit 1; }; }
need docker
need python3
[ "$ANALYSE_ONLY" -eq 1 ] || need k6

python3 - <<'PY'
import importlib, sys
missing = [m for m in ("numpy", "scipy", "matplotlib") if not importlib.util.find_spec(m)]
if missing:
    sys.exit("missing python packages: " + ", ".join(missing) + "  (pip install numpy scipy matplotlib)")
PY

if [ "$ANALYSE_ONLY" -eq 0 ]; then
  echo "==> creating the shared docker networks if they do not exist"
  docker network inspect microservices-net >/dev/null 2>&1 || docker network create microservices-net
  docker network inspect monitoring-net   >/dev/null 2>&1 || docker network create monitoring-net

  echo "==> building the service images"
  docker compose \
    -f "$ROOT/infrastructure/docker-compose.yml" \
    -f "$ROOT/infrastructure/docker-compose.parity.yml" build

  echo "==> recording the execution environment"
  python3 "$REV3/capture_environment.py" "$REV3/results/environment.json" || true

  echo "==> running the benchmark suite, $REPS repetitions, one configuration at a time"
  echo "    (safe to interrupt: completed runs are skipped when you start it again)"
  python3 "$REV3/run_suite.py" --reps "$REPS" --outdir "$REV3/results"
fi

echo "==> aggregating, testing and writing the tables"
python3 "$REV3/analyze.py"

echo "==> drawing the figures"
python3 "$REV3/make_figures.py"

cat <<EOF

Done.

  tables   $REV3/results/analysis/
  figures  $REV3/results/figures/
  digest   $REV3/results/analysis/SUMMARY.md

Mapping from each paper table to the file that produces it is in README.md.
EOF
