#!/bin/sh
set -e

# Skip migrations for worker/scheduler containers
if [ "$SKIP_MIGRATIONS" = "true" ]; then
    echo "=========================================="
    echo "Skipping migrations (SKIP_MIGRATIONS=true)"
    echo "=========================================="
else
    echo "=========================================="
    echo "Running Database Migrations..."
    echo "=========================================="

    # Wait for database to be ready
    echo "Waiting for database..."
    python3 << 'EOF'
import asyncio
import os
import sys

sys.path.insert(0, '/app/src')

from sqlalchemy import text
from src.core.database import engine

async def wait_for_db():
    max_retries = 30
    for i in range(max_retries):
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            print("Database is ready!")
            return True
        except Exception as e:
            print(f"Waiting for database... ({i+1}/{max_retries})")
            await asyncio.sleep(1)
    print("ERROR: Database not available after 30 retries")
    return False

result = asyncio.run(wait_for_db())
if not result:
    sys.exit(1)
EOF

    if [ $? -ne 0 ]; then
        echo "ERROR: Failed to connect to database"
        exit 1
    fi

    # Run Alembic migrations
    echo ""
    echo "Running Alembic migrations..."
    cd /app

    if alembic upgrade head; then
        echo "Migrations completed successfully!"
    else
        echo "ERROR: Migrations failed"
        exit 1
    fi
fi

echo ""
echo "=========================================="
echo "Starting Application"
echo "=========================================="
exec "$@"
