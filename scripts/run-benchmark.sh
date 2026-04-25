#!/usr/bin/env bash
set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

SCENARIO="${1:-load}"  # load | stress | spike | soak | all

echo -e "${YELLOW}Running benchmark: ${SCENARIO}${NC}"
echo -e "${YELLOW}Grafana live view: http://localhost:3000${NC}\n"

exec "$ROOT/benchmarking/k6/run-all.sh" "$SCENARIO"
