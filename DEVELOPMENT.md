# Development Mode with Hot Reload

This setup enables hot reloading for all services during development.

## Quick Start

```bash
# Start all services with hot reload
./dev.sh

# Or manually:
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d
```

## What's Included

### API Service
- **Hot reload**: Uvicorn watches `/app/src` and restarts on changes
- **Debug mode**: Enabled for detailed error messages

### Worker & Scheduler
- **Hot reload**: Uses `watchfiles` to restart Celery on Python changes
- **Auto-restart**: Workers restart automatically when code changes

### Web (Next.js)
- **Hot reload**: Next.js dev server with Fast Refresh
- **Source maps**: Full debugging support

## How It Works

The `docker-compose.dev.yml` file overrides the production settings:

1. **Volume mounts**: Local source code is mounted into containers
2. **Development commands**: Services run in dev mode with watchers
3. **Debug environment**: Additional logging and debugging enabled

## File Structure

```
docker-compose.yml          # Production-like base configuration
docker-compose.dev.yml      # Development overrides (hot reload)
dev.sh                      # Convenience script to start dev mode
```

## Logs

View logs for specific services:

```bash
# API logs
docker-compose logs -f api

# Worker logs
docker-compose logs -f worker

# Web logs
docker-compose logs -f web

# All logs
docker-compose logs -f
```

## Rebuilding

If you add new dependencies to `pyproject.toml` or `package.json`:

```bash
# Rebuild specific service
docker-compose build api
docker-compose up -d api

# Or rebuild all
docker-compose build
docker-compose up -d
```

## Environment Variables

The dev mode sets these additional variables:

| Variable | Value | Effect |
|----------|-------|--------|
| `DEBUG` | `true` | Enables debug logging |
| `LOG_LEVEL` | `debug` | Verbose logging |
| `NODE_ENV` | `development` | Next.js dev mode |

## Troubleshooting

### Changes not reflecting

If code changes aren't picked up:

```bash
# Restart specific service
docker-compose restart worker

# Or full restart
docker-compose down
./dev.sh
```

### Worker not reloading

Celery workers use `watchfiles` for hot reload. If it's not working:

```bash
# Check if watchfiles is installed
docker-compose exec worker pip list | grep watchfiles

# Manual restart
docker-compose restart worker
```

### Port conflicts

If ports are already in use:

```bash
# Stop any running containers
docker-compose down

# Check what's using the ports
lsof -i :8000  # API
lsof -i :3000  # Web
lsof -i :5438  # DB
lsof -i :6379  # Redis
```

## Production Mode

To run in production mode (no hot reload):

```bash
docker-compose down
docker-compose up -d
```

This uses the base `docker-compose.yml` only, with optimized production settings.
