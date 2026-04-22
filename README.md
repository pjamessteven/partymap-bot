# PartyMap Festival Bot - Monorepo

This is a monorepo containing the PartyMap Festival Bot application with a Next.js frontend and Python FastAPI backend.

## Structure

```
partymap-bot/
├── apps/
│   ├── api/           # Python FastAPI backend
│   └── web/           # Next.js frontend
├── docker-compose.yml # Docker orchestration
└── package.json       # Root workspace config
```

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Node.js 20+ (for local development)
- Python 3.12+ (for local development)

### Running with Docker

```bash
# Start all services
docker-compose up -d

# DEV

docker-compose -f docker-compose.yml -f docker-compose.dev.yml build --no-cache web
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up

# Initialize the database
docker-compose exec api python scripts/init_db.py

# View logs
docker-compose logs -f

# Access the services:
# - Web UI: http://localhost:3000
# - API Docs: http://localhost:8000/docs
```

### Services

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
```

## API Documentation

When running locally, API documentation is available at:

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
