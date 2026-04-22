#!/bin/bash
# Development mode helper script
# Enables hot reloading for all services

cd "$(dirname "$0")"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Starting PartyMap Bot in development mode...${NC}"
echo -e "${YELLOW}Hot reloading enabled for all services${NC}"
echo ""

# Export compose file for dev mode
export COMPOSE_FILE=docker-compose.yml:docker-compose.dev.yml

# Check if services are already running
if docker-compose ps | grep -q "api\|worker\|web"; then
    echo -e "${YELLOW}Services already running. Restarting with hot reload...${NC}"
    docker-compose down
fi

# Build images (force rebuild for dev mode)
echo "Building images..."
docker-compose build --no-cache web

# Start services
echo ""
echo -e "${GREEN}Starting services...${NC}"
docker-compose up -d

# Show logs
echo ""
echo -e "${GREEN}Services started! Showing logs (Ctrl+C to exit):${NC}"
echo ""
docker-compose logs -f api worker scheduler web
