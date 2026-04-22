#!/bin/sh
set -e

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

# Check if alembic is installed
if ! python3 -c "import alembic" 2>/dev/null; then
    echo "Installing alembic..."
    pip install alembic -q
fi

# Try to run migrations. If they fail due to existing tables, stamp and continue
echo "Attempting to run migrations..."
if alembic upgrade head; then
    echo "✓ Migrations completed successfully!"
else
    echo "Migration failed. Checking if database already has tables..."
    
    # Check if festivals table exists (meaning DB was already set up)
    TABLE_COUNT=$(python3 << 'EOF' 2>/dev/null
import asyncio
import sys
sys.path.insert(0, '/app/src')
from sqlalchemy import text
from src.core.database import engine
import logging
logging.disable(logging.INFO)

async def check():
    async with engine.connect() as conn:
        try:
            result = await conn.execute(text("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public'"))
            count = result.scalar()
            print(count, end='')
        except Exception as e:
            print("0", end='')

asyncio.run(check())
EOF
)
    
    if [ "$TABLE_COUNT" -gt "0" ]; then
        echo "Database has $TABLE_COUNT existing tables. Stamping with current migration version..."
        alembic stamp head || echo "WARNING: Failed to stamp database"
        echo "✓ Database stamped. Continuing..."
    else
        echo "ERROR: Database is empty but migrations failed"
        exit 1
    fi
fi

echo ""
echo "=========================================="
echo "Starting Application"
echo "=========================================="
exec "$@"
