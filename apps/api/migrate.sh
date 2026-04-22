#!/bin/bash
# Database migration helper script
# Usage: ./migrate.sh [command]
#
# Commands:
#   upgrade    - Run all pending migrations (default)
#   downgrade  - Rollback one migration
#   revision   - Create a new migration (with autogenerate)
#   history    - Show migration history
#   current    - Show current migration version
#   stamp      - Stamp the database with current version

cd "$(dirname "$0")"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

cmd="${1:-upgrade}"

case "$cmd" in
    upgrade)
        echo -e "${GREEN}Running migrations...${NC}"
        alembic upgrade head
        ;;
    downgrade)
        echo -e "${YELLOW}Rolling back one migration...${NC}"
        alembic downgrade -1
        ;;
    revision)
        echo -e "${GREEN}Creating new migration...${NC}"
        read -p "Enter migration message: " message
        if [ -z "$message" ]; then
            echo -e "${RED}Error: Migration message is required${NC}"
            exit 1
        fi
        alembic revision --autogenerate -m "$message"
        echo -e "${GREEN}Migration created. Review the file in migrations/versions/ before applying.${NC}"
        ;;
    history)
        echo -e "${GREEN}Migration history:${NC}"
        alembic history --verbose
        ;;
    current)
        echo -e "${GREEN}Current migration version:${NC}"
        alembic current
        ;;
    stamp)
        echo -e "${YELLOW}Stamping database with current version...${NC}"
        alembic stamp head
        ;;
    create|init)
        echo -e "${GREEN}Creating initial migration...${NC}"
        alembic revision --autogenerate -m "Initial migration"
        ;;
    *)
        echo "Usage: $0 [command]"
        echo ""
        echo "Commands:"
        echo "  upgrade     Run all pending migrations (default)"
        echo "  rollback    Rollback one migration"
        echo "  revision    Create a new migration with autogenerate"
        echo "  history     Show migration history"
        echo "  current     Show current migration version"
        echo "  stamp       Stamp database with current version"
        echo ""
        exit 1
        ;;
esac
