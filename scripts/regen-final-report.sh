#!/usr/bin/env bash
# Regenerate the master report from summaries in benchmarking/results/final/.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export RESULTS_DIR="$ROOT/benchmarking/results/final"

if [ ! -d "$RESULTS_DIR" ]; then
  echo "$RESULTS_DIR does not exist. Run a benchmark first."
  exit 1
fi

rm -f "$RESULTS_DIR/reports/MASTER_REPORT_"*.md

cd "$ROOT"
python3 "$ROOT/benchmarking/analysis/generate_consolidated.py" --all

echo ""
echo "Open: $RESULTS_DIR/reports/MASTER_REPORT_FINAL_SUITE.md"
