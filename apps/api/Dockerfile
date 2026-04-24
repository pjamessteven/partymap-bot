# Multi-stage build for Python FastAPI backend
# Stage 1: Builder - installs build deps and compiles Python packages
# Stage 2: Runtime - minimal image with only runtime deps

# =============================================================================
# STAGE 1: Builder
# =============================================================================
FROM python:3.12-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies into venv
COPY pyproject.toml .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -e "."

# Install Playwright browsers into venv
RUN playwright install chromium

# =============================================================================
# STAGE 2: Tester (runs unit tests, build fails if tests fail)
# =============================================================================
FROM builder AS tester

WORKDIR /app

ENV PATH="/opt/venv/bin:$PATH"

# Install dev dependencies for testing
RUN pip install --no-cache-dir -e ".[dev]"

# Copy application code and tests
COPY src/ ./src/
COPY tests/ ./tests/
COPY migrations/ ./migrations/
COPY alembic.ini .
COPY migrate.sh .

# Run unit tests with coverage (SQLite in-memory, no external DB needed)
# Build fails if tests fail
RUN pytest tests/unit/ -v --tb=short --cov=src --cov-report=term-missing

# =============================================================================
# STAGE 3: Runtime
# =============================================================================
FROM python:3.12-slim AS runtime

WORKDIR /app

# Install runtime system dependencies (no gcc/build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libpq5 \
    # Playwright runtime dependencies
    libglib2.0-0 \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user early (needed for browser cache ownership)
RUN useradd -m -u 1000 appuser

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy Playwright browsers from builder and fix ownership
COPY --from=builder --chown=appuser:appuser /root/.cache/ms-playwright /home/appuser/.cache/ms-playwright

# Copy application code
COPY --chown=appuser:appuser src/ ./src/
COPY --chown=appuser:appuser scripts/ ./scripts/
COPY --chown=appuser:appuser tests/ ./tests/
COPY --chown=appuser:appuser migrations/ ./migrations/
COPY --chown=appuser:appuser alembic.ini .
COPY --chown=appuser:appuser migrate.sh .

# Copy and set up entrypoint script
COPY --chown=appuser:appuser entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

USER appuser

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
