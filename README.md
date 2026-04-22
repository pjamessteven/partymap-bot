# PartyMap Festival Bot - Monorepo

This is a monorepo containing the PartyMap Festival Bot application with a Next.js frontend and Python FastAPI backend.

## Structure

```
partymap-bot/
├── apps/
│   ├── api/           # Python FastAPI backend
│   └── web/           # Next.js frontend
├── docker-compose.yml      # Production Docker orchestration
├── docker-compose.dev.yml  # Development overrides (hot reload)
└── package.json       # Root workspace config
```

## Quick Start with Docker

### Prerequisites

- Docker and Docker Compose

### 1. Create environment file

```bash
cp .env.example .env
# Edit .env and add your API keys:
# OPENROUTER_API_KEY=your_key_here
# EXA_API_KEY=your_key_here
```

### 2. Start all services (Development)

```bash
# Start with hot reload for development
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# Or start and view logs directly
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up
```

### 3. Verify services are running

```bash
# Check container status
docker-compose -f docker-compose.yml -f docker-compose.dev.yml ps

# View API logs
docker-compose -f docker-compose.yml -f docker-compose.dev.yml logs -f api

# View web logs
docker-compose -f docker-compose.yml -f docker-compose.dev.yml logs -f web
```

### 4. Access the services

| Service | URL | Description |
|---------|-----|-------------|
| Web UI | http://localhost:3000 | Next.js frontend dashboard |
| API Docs | http://localhost:8000/docs | FastAPI Swagger UI |
| API Redoc | http://localhost:8000/redoc | FastAPI ReDoc |
| Database | localhost:5438 | PostgreSQL (direct access) |
| Redis | localhost:6379 | Redis (direct access) |

### 5. Stop services

```bash
# Stop all services
docker-compose -f docker-compose.yml -f docker-compose.dev.yml down

# Stop and remove volumes (clears database data)
docker-compose -f docker-compose.yml -f docker-compose.dev.yml down -v
```

## Common Docker Commands

### Running Migrations

Migrations run automatically when containers start. To run manually:

```bash
# Run pending migrations
docker-compose -f docker-compose.yml -f docker-compose.dev.yml exec api alembic upgrade head

# Check current migration version
docker-compose -f docker-compose.yml -f docker-compose.dev.yml exec api alembic current

# Rollback one migration
docker-compose -f docker-compose.yml -f docker-compose.dev.yml exec api alembic downgrade -1

# Create new migration (with autogenerate)
docker-compose -f docker-compose.yml -f docker-compose.dev.yml exec api alembic revision --autogenerate -m "description"
```

### Rebuilding Containers

```bash
# Rebuild all containers
docker-compose -f docker-compose.yml -f docker-compose.dev.yml build

# Rebuild specific service
docker-compose -f docker-compose.yml -f docker-compose.dev.yml build api

# Rebuild and restart
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
```

### Executing Commands in Containers

```bash
# Open Python shell in API container
docker-compose -f docker-compose.yml -f docker-compose.dev.yml exec api python

# Open database shell
docker-compose -f docker-compose.yml -f docker-compose.dev.yml exec db psql -U partymap -d partymap_bot

# Install new Python dependency
docker-compose -f docker-compose.yml -f docker-compose.dev.yml exec api pip install <package>

# Run API tests
docker-compose -f docker-compose.yml -f docker-compose.dev.yml exec api pytest
```

### Restarting Services

```bash
# Restart all services
docker-compose -f docker-compose.yml -f docker-compose.dev.yml restart

# Restart specific service
docker-compose -f docker-compose.yml -f docker-compose.dev.yml restart api
```

## Services

| Service   | Port | Description                |
| --------- | ---- | -------------------------- |
| web       | 3000 | Next.js frontend dashboard |
| api       | 8000 | FastAPI backend            |
| worker    | -    | Celery task worker         |
| scheduler | -    | Celery Beat scheduler      |
| db        | 5438 | PostgreSQL database        |
| redis     | 6379 | Redis cache/queue          |

## Development

### Frontend (Next.js)

```bash
cd apps/web
npm install
npm run dev
```

### Backend (Python)

```bash
cd apps/api
pip install -e "."
uvicorn src.main:app --reload
```

## Environment Variables

Create a `.env` file in the root directory:

```bash
OPENROUTER_API_KEY=your_key_here
EXA_API_KEY=your_key_here
PARTYMAP_API_KEY=your_key_here
```

## API Documentation

When running locally, API documentation is available at:

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
