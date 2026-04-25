#!/usr/bin/env bash
set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo -e "${YELLOW}Starting monitoring stack...${NC}"
cd "$ROOT/infrastructure"

docker compose -f docker-compose.monitoring.yml --env-file .env up -d

echo -e "\n${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  Monitoring stack is up!${NC}"
echo -e ""
echo -e "  Grafana:      ${YELLOW}http://localhost:3000${NC}  (admin/admin)"
echo -e "  Prometheus:   ${YELLOW}http://localhost:9090${NC}"
echo -e "  Loki:         ${YELLOW}http://localhost:3100${NC}"
echo -e "  cAdvisor:     ${YELLOW}http://localhost:8080${NC}"
echo -e "  Node Exporter:${YELLOW}http://localhost:9100${NC}"
echo -e ""
echo -e "  Dashboard: Swift vs Java Research Benchmark"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
