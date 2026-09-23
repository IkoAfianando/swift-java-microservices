#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# Initial Setup Script
# Swift vs Java Microservices Research – Iko Afianando
# ============================================================

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  Research Environment Setup${NC}"
echo -e "${GREEN}  Building High-Performance Microservices with Swift${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# ──────────────────────────────────────────────────────────
# Check prerequisites
# ──────────────────────────────────────────────────────────

check_tool() {
  if command -v "$1" &>/dev/null; then
    echo -e "  ${GREEN}✓${NC} $1 found: $(command -v "$1")"
  else
    echo -e "  ${RED}✗${NC} $1 not found – please install it"
    MISSING+=("$1")
  fi
}

# docker compose v2 is a plugin, needs its own check
check_compose() {
  if docker compose version &>/dev/null 2>&1; then
    echo -e "  ${GREEN}✓${NC} docker compose (v2 plugin) found"
    COMPOSE_CMD="docker compose"
  elif command -v docker-compose &>/dev/null; then
    echo -e "  ${GREEN}✓${NC} docker-compose (v1) found: $(command -v docker-compose)"
    COMPOSE_CMD="docker-compose"
  else
    echo -e "  ${RED}✗${NC} docker compose not found"
    echo -e "      → Enable it in Docker Desktop: Settings → General → ✓ Use Docker Compose V2"
    echo -e "        OR: brew install docker-compose"
    MISSING+=("docker-compose")
  fi
}

MISSING=()
COMPOSE_CMD=""
echo -e "\n${YELLOW}Checking prerequisites...${NC}"
check_tool docker
check_compose
check_tool k6
check_tool python3
check_tool curl

if [ ${#MISSING[@]} -gt 0 ]; then
  echo -e "\n${RED}Missing tools: ${MISSING[*]}${NC}"
  echo "Install guide:"
  echo "  docker compose: Docker Desktop → Settings → General → Use Docker Compose V2"
  echo "  k6:             brew install k6"
  echo "  python3:        brew install python"
  exit 1
fi

# Export compose command for other scripts to use
export COMPOSE_CMD

# ──────────────────────────────────────────────────────────
# Environment file
# ──────────────────────────────────────────────────────────
if [ ! -f "$ROOT/infrastructure/.env" ]; then
  cp "$ROOT/infrastructure/.env.example" "$ROOT/infrastructure/.env"
  echo -e "${GREEN}✓${NC} Created infrastructure/.env from template"
fi

# ──────────────────────────────────────────────────────────
# Create Docker networks (idempotent)
# ──────────────────────────────────────────────────────────
echo -e "\n${YELLOW}Setting up Docker networks...${NC}"
docker network inspect microservices-net &>/dev/null || docker network create microservices-net
docker network inspect monitoring-net &>/dev/null    || docker network create monitoring-net
echo -e "${GREEN}✓${NC} Networks ready"

# ──────────────────────────────────────────────────────────
# Python analysis dependencies
# ──────────────────────────────────────────────────────────
echo -e "\n${YELLOW}Installing Python analysis dependencies...${NC}"
python3 -m pip install --quiet matplotlib numpy 2>/dev/null || echo "  (Optional: pip install matplotlib numpy for charts)"

# ──────────────────────────────────────────────────────────
# Make scripts executable
# ──────────────────────────────────────────────────────────
chmod +x "$ROOT/scripts/"*.sh
chmod +x "$ROOT/benchmarking/k6/run-all.sh"

echo -e "\n${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  Setup complete!${NC}"
echo -e ""
echo -e "  Next steps:"
echo -e "  1. ${YELLOW}./scripts/start-services.sh${NC}    – Start all microservices"
echo -e "  2. ${YELLOW}./scripts/start-monitoring.sh${NC}  – Start Prometheus + Grafana"
echo -e "  3. ${YELLOW}./scripts/run-benchmark.sh${NC}     – Run k6 benchmarks"
echo -e "  4. ${YELLOW}open http://localhost:3000${NC}      – View Grafana dashboards"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
