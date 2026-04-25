#!/usr/bin/env bash
set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo -e "${YELLOW}Starting microservices...${NC}"
cd "$ROOT/infrastructure"

# Start infrastructure first, then services
docker compose --env-file .env up -d postgres redis
echo -e "${YELLOW}Waiting for database...${NC}"
until docker compose exec postgres pg_isready -U research &>/dev/null; do sleep 1; done
echo -e "${GREEN}✓${NC} PostgreSQL ready"

docker compose --env-file .env up -d \
  swift-user-service swift-product-service swift-order-service \
  java-user-service java-product-service java-order-service

echo -e "\n${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  All services started!${NC}"
echo -e ""
echo -e "  Swift services:   :8081 (user) | :8082 (product) | :8083 (order)"
echo -e "  Java services:    :9081 (user) | :9082 (product) | :9083 (order)"
echo -e ""
echo -e "  Health checks:"
echo -e "    curl http://localhost:8081/health  # Swift user"
echo -e "    curl http://localhost:9081/health  # Java user"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
