"""Test configuration and fixtures."""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from unittest.mock import AsyncMock, MagicMock, patch

from src.core.database import Base

# Use in-memory SQLite for tests
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture(scope="session")
async def engine():
    """Create test database engine."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(engine) -> AsyncSession:
    """Create test database session."""
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session
        # Rollback after each test
        await session.rollback()


@pytest.fixture
def test_app(db_session):
    """Create FastAPI test app with overridden DB dependency."""
    from src.main import create_app
    from src.core.database import get_db

    app = create_app()

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    return app


@pytest.fixture
async def async_client(test_app):
    """Create AsyncClient for testing endpoints."""
    from httpx import AsyncClient
    async with AsyncClient(app=test_app, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def mock_celery_tasks():
    """Mock all Celery task functions."""
    with patch("src.tasks.celery_app.discovery_pipeline") as mock_d, \
         patch("src.tasks.celery_app.research_pipeline") as mock_r, \
         patch("src.tasks.celery_app.sync_pipeline") as mock_s, \
         patch("src.tasks.goabase_tasks.goabase_sync_task") as mock_g, \
         patch("src.tasks.refresh_pipeline.refresh_unconfirmed_dates_task") as mock_refresh, \
         patch("src.tasks.refresh_pipeline.apply_approved_refresh_task") as mock_apply:
        
        for mock in [mock_d, mock_r, mock_s, mock_g, mock_refresh, mock_apply]:
            mock.delay = MagicMock(return_value=MagicMock(id=f"task-{id(mock)}"))
        
        yield {
            "discovery": mock_d,
            "research": mock_r,
            "sync": mock_s,
            "goabase": mock_g,
            "refresh": mock_refresh,
            "apply_refresh": mock_apply,
        }


@pytest.fixture
def mock_partymap_client():
    """Mock PartyMapClient for deduplication and sync tests."""
    with patch("src.dashboard.router.PartyMapClient") as MockClient:
        instance = AsyncMock()
        instance.find_existing_event = AsyncMock(return_value=None)
        instance.get_event = AsyncMock(return_value={"id": 12345, "name": "Test"})
        instance.search_events = AsyncMock(return_value=[])
        instance.sync_festival = AsyncMock(return_value={"event_id": 12345, "action": "created"})
        instance.close = AsyncMock()
        MockClient.return_value = instance
        MockClient.__aenter__ = AsyncMock(return_value=instance)
        MockClient.__aexit__ = AsyncMock(return_value=False)
        yield instance


@pytest.fixture
def mock_broadcaster():
    """Mock StreamBroadcaster for streaming tests."""
    with patch("src.agents.streaming.get_broadcaster") as mock_get:
        broadcaster = AsyncMock()
        broadcaster.subscribe = AsyncMock(return_value=[])
        broadcaster.broadcast = AsyncMock()
        mock_get.return_value = broadcaster
        yield broadcaster


@pytest.fixture
def mock_redis():
    """Mock Redis for WebSocket/job tests."""
    with patch("src.api.jobs.redis_client") as mock_redis:
        mock_redis.publish = AsyncMock()
        mock_redis.pubsub = MagicMock()
        mock_redis.pubsub.subscribe = AsyncMock()
        mock_redis.pubsub.unsubscribe = AsyncMock()
        mock_redis.pubsub.listen = AsyncMock(return_value=[])
        yield mock_redis


@pytest.fixture(autouse=True)
def reset_circuit_breakers():
    """Reset all circuit breakers before each test."""
    from src.services.circuit_breaker import get_all_circuit_breakers
    for breaker in get_all_circuit_breakers().values():
        breaker.reset()
    yield


@pytest.fixture
def mock_settings():
    """Create mock settings."""
    settings = MagicMock()
    settings.partymap_api_key = "test-api-key"
    settings.partymap_base_url = "https://api.partymap.com"
    settings.sync_rate_limit_per_minute = 60
    settings.exa_api_key = "test-exa-key"
    settings.openrouter_api_key = "test-llm-key"
    settings.openrouter_base_url = "https://openrouter.ai/api/v1"
    settings.openrouter_model = "deepseek/deepseek-chat"
    settings.redis_url = "redis://localhost:6379/0"
    return settings
