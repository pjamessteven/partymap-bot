#!/bin/bash
# Generate TypeScript types from FastAPI OpenAPI spec

set -e

echo "🚀 Generating TypeScript types from FastAPI OpenAPI spec..."

# Change to API directory
cd "$(dirname "$0")/../apps/api"

# Check if Python environment is available
if [ ! -d ".venv" ]; then
    echo "❌ Virtual environment not found. Please run: python -m venv .venv"
    exit 1
fi

# Activate virtual environment
source .venv/bin/activate

# Start FastAPI in background to get OpenAPI spec
echo "📡 Starting FastAPI server temporarily..."
uvicorn src.main:app --host 127.0.0.1 --port 9999 --log-level error &
SERVER_PID=$!

# Wait for server to be ready
sleep 3

# Download OpenAPI spec
echo "📥 Downloading OpenAPI spec..."
curl -s http://127.0.0.1:9999/openapi.json > /tmp/openapi.json

# Kill server
echo "🛑 Stopping FastAPI server..."
kill $SERVER_PID 2>/dev/null || true

# Check if openapi-typescript is installed
cd ../web
if ! command -v npx &> /dev/null; then
    echo "❌ npx not found. Please install Node.js"
    exit 1
fi

# Generate TypeScript types
echo "📝 Generating TypeScript types..."
npx openapi-typescript /tmp/openapi.json --output types/api.ts

echo "✅ TypeScript types generated at apps/web/types/api.ts"
echo ""
echo "⚠️  IMPORTANT: Review the generated types and update types/index.ts if needed"
