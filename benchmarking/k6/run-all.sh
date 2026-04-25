#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# Run all k6 benchmark scenarios and save results
# ============================================================

RESULTS_DIR="${RESULTS_DIR:-$(dirname "$0")/../results}"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
mkdir -p "$RESULTS_DIR"

# Colors
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'

# Check k6 is installed
if ! command -v k6 &>/dev/null; then
  echo -e "${RED}k6 is not installed. Install: brew install k6${NC}"
  exit 1
fi

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Swift vs Java Benchmark Suite${NC}"
echo -e "${GREEN}  Research: Iko Afianando (2602261970)${NC}"
echo -e "${GREEN}  $(date)${NC}"
echo -e "${GREEN}========================================${NC}"

# Wait for services to be ready
echo -e "${YELLOW}Checking service health...${NC}"
for url in "http://localhost:8081/health" "http://localhost:9081/actuator/health"; do
  until curl -sf "$url" >/dev/null 2>&1; do
    echo "  Waiting for $url..."
    sleep 3
  done
  echo -e "  ${GREEN}✓ $url is ready${NC}"
done

run_scenario() {
  local name="$1"
  local script="$2"
  local output_file="${RESULTS_DIR}/${TIMESTAMP}_${name}.json"
  local summary_file="${RESULTS_DIR}/${TIMESTAMP}_${name}_summary.html"

  echo -e "\n${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
  echo -e "${YELLOW}Running: ${name}${NC}"
  echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

  k6 run \
    --out json="$output_file" \
    --summary-export="${RESULTS_DIR}/${TIMESTAMP}_${name}_summary.json" \
    "$script" \
    2>&1 | tee "${RESULTS_DIR}/${TIMESTAMP}_${name}.log"

  echo -e "${GREEN}✓ ${name} complete → ${output_file}${NC}"
}

# ──────────────────────────────────────────────────────────
# Run scenarios
# ──────────────────────────────────────────────────────────

case "${1:-all}" in
  load)
    run_scenario "load-test" "$(dirname "$0")/scenarios/load-test.js"
    ;;
  stress)
    run_scenario "stress-test" "$(dirname "$0")/scenarios/stress-test.js"
    ;;
  spike)
    run_scenario "spike-test" "$(dirname "$0")/scenarios/spike-test.js"
    ;;
  soak)
    echo -e "${YELLOW}Soak test will run for ${SOAK_DURATION:-2h}. Set SOAK_DURATION=30m to override.${NC}"
    run_scenario "soak-test" "$(dirname "$0")/scenarios/soak-test.js"
    ;;
  all|*)
    run_scenario "load-test"   "$(dirname "$0")/scenarios/load-test.js"
    run_scenario "stress-test" "$(dirname "$0")/scenarios/stress-test.js"
    run_scenario "spike-test"  "$(dirname "$0")/scenarios/spike-test.js"
    ;;
esac

echo -e "\n${GREEN}========================================${NC}"
echo -e "${GREEN}  All benchmarks complete!${NC}"
echo -e "${GREEN}  Results: ${RESULTS_DIR}/${NC}"
echo -e "${GREEN}  Grafana: http://localhost:3000${NC}"
echo -e "${GREEN}========================================${NC}"

# Auto-run analysis if Python is available
if command -v python3 &>/dev/null; then
  echo -e "\n${YELLOW}Running analysis...${NC}"
  python3 "$(dirname "$0")/../analysis/compare.py" \
    --results-dir "$RESULTS_DIR" \
    --timestamp "$TIMESTAMP" \
    || echo -e "${YELLOW}Analysis skipped (check requirements)${NC}"
fi
