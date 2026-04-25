#!/usr/bin/env bash
# Reset Prometheus + Loki data, restart services (flushes in-memory metrics),
# warm up lazy Java metrics, then run benchmark.
#
# Usage: ./scripts/reset-and-benchmark.sh [load|stress|spike|soak|all]
#
# Preserved: Postgres + Redis data, Grafana dashboards/config.
# Reset:     Prometheus TSDB, Loki logs, Swift/Java in-memory metric counters.

set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCENARIO="${1:-load}"

echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}  Reset + Benchmark: ${SCENARIO}${NC}"
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

cd "$ROOT/infrastructure"

echo -e "\n${YELLOW}[1/6] Stopping services (resets in-memory metrics)...${NC}"
docker compose stop \
  swift-user-service swift-product-service swift-order-service \
  java-user-service java-product-service java-order-service

docker compose -f docker-compose.monitoring.yml stop prometheus loki

echo -e "\n${YELLOW}[2/6] Wiping Prometheus TSDB and Loki log volumes...${NC}"
docker volume rm infrastructure_prometheus-data infrastructure_loki-data 2>/dev/null || true

echo -e "\n${YELLOW}[3/6] Starting Prometheus + Loki with fresh volumes...${NC}"
docker compose -f docker-compose.monitoring.yml up -d prometheus loki

echo -e "\n${YELLOW}[4/6] Starting all 6 microservices...${NC}"
docker compose up -d \
  swift-user-service swift-product-service swift-order-service \
  java-user-service java-product-service java-order-service

echo -e "\n${YELLOW}[5/6] Waiting for services to be healthy + warming up Java lazy metrics...${NC}"
sleep 15
for port in 8081 8082 8083 9081 9082 9083; do
  path="users"; [ $port -eq 8082 ] || [ $port -eq 9082 ] && path="products"
  [ $port -eq 8083 ] || [ $port -eq 9083 ] && path="orders"
  for _ in 1 2 3 4 5; do
    curl -s "http://localhost:$port/$path" > /dev/null || true
  done
done
echo -e "${GREEN}✓ Warmup complete${NC}"

echo -e "\n${YELLOW}[6/6] Running benchmark: ${SCENARIO}${NC}"
echo -e "${YELLOW}  → Live view: http://localhost:3000${NC}\n"
exec "$ROOT/benchmarking/k6/run-all.sh" "$SCENARIO"
