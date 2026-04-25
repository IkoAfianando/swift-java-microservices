#!/usr/bin/env bash
#
# Run the final benchmark suite. Output goes to benchmarking/results/final/.
#
# Usage:
#   ./scripts/run-final-suite.sh           # load + stress + spike
#   ./scripts/run-final-suite.sh load      # one scenario
#   ./scripts/run-final-suite.sh +soak     # all + a 20m soak

set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export RESULTS_DIR="$ROOT/benchmarking/results/final"
mkdir -p "$RESULTS_DIR/reports"

MODE="${1:-all}"

echo -e "${CYAN}Final Benchmark Suite${NC}"
echo -e "${CYAN}Output: $RESULTS_DIR${NC}"

echo -e "\n${YELLOW}[1/3] Checking services...${NC}"
for url in "http://localhost:8081/health" "http://localhost:9081/actuator/health" \
           "http://localhost:8082/health" "http://localhost:9082/actuator/health" \
           "http://localhost:8083/health" "http://localhost:9083/actuator/health"; do
  if ! curl -sf "$url" >/dev/null 2>&1; then
    echo -e "  ❌ $url not responding. Run 'docker compose up -d' first."
    exit 1
  fi
  echo -e "  ✓ $url"
done

echo -e "\n${YELLOW}[2/3] Verifying Swift histogram parity...${NC}"
for port in 8081 8082; do
  curl -s "http://localhost:$port/users" > /dev/null || true
  curl -s "http://localhost:$port/products" > /dev/null || true
done
sleep 1
SWIFT_BUCKETS=$(curl -s http://localhost:8081/metrics | grep -c 'http_request_duration_seconds_bucket{' || echo 0)
echo -e "  Swift /metrics emits ${SWIFT_BUCKETS} bucket lines"

# Run scenarios
case "$MODE" in
  +soak|all+soak)
    SCENARIOS="all"
    RUN_SOAK=1
    ;;
  *)
    SCENARIOS="$MODE"
    RUN_SOAK=0
    ;;
esac

echo -e "\n${GREEN}[3/3] Running k6 scenarios: $SCENARIOS${NC}"
"$ROOT/benchmarking/k6/run-all.sh" "$SCENARIOS"

if [ "$RUN_SOAK" = "1" ]; then
  echo -e "\n${GREEN}Running 20-min soak${NC}"
  SOAK_DURATION=20m "$ROOT/benchmarking/k6/run-all.sh" soak
fi

echo -e "\n${GREEN}Generating reports...${NC}"
python3 "$ROOT/benchmarking/analysis/generate_consolidated.py"

echo -e "\n${GREEN}Done.${NC}"
echo -e "  Results: $RESULTS_DIR/"
echo -e "  Reports: $RESULTS_DIR/reports/"
echo -e "  Open:    open $RESULTS_DIR/reports/MASTER_REPORT_*.md"
