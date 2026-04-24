"""Test configuration and fixtures."""

import os

# Ensure required env vars exist so Settings() doesn't blow up during imports.
# Tests mock all external APIs, so these dummy values are never used for real calls.
os.environ.setdefault("PARTYMAP_API_KEY", "test-api-key")
os.environ.setdefault("EXA_API_KEY", "test-exa-key")
os.environ.setdefault("OPENROUTER_API_KEY", "test-openrouter-key")

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from unittest.mock import AsyncMock, MagicMock, patch

# ---------------------------------------------------------------------------
# CRITICAL: Monkey-patch SQLAlchemy ARRAY → JSON for SQLite so tests can run
# without a real PostgreSQL instance. This must happen BEFORE importing any
# models that declare ARRAY columns.
# ---------------------------------------------------------------------------
from sqlalchemy import ARRAY, JSON
from sqlalchemy.ext.compiler import compiles


@compiles(ARRAY, "sqlite")
def compile_array_sqlite(type_, compiler, **kw):
    """Render ARRAY as JSON on SQLite (which natively supports JSON)."""
    return compiler.process(JSON())


# Patch bind/result processors so Python lists are JSON-serialised when
# written to SQLite and parsed back on read.
_original_array_bind_processor = ARRAY.bind_processor
_original_array_result_processor = ARRAY.result_processor


def _array_bind_processor(self, dialect):
    if dialect.name == "sqlite":
        return JSON().bind_processor(dialect)
    return _original_array_bind_processor(self, dialect)


def _array_result_processor(self, dialect, coltype):
    if dialect.name == "sqlite":
        return JSON().result_processor(dialect, coltype)
    return _original_array_result_processor(self, dialect, coltype)


ARRAY.bind_processor = _array_bind_processor
ARRAY.result_processor = _array_result_processor
# ---------------------------------------------------------------------------

from src.core.database import Base

# Use in-memory SQLite for tests
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture(loop_scope="function")
async def engine():
    """Create test database engine (function-scoped for isolation)."""
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
    from httpx import ASGITransport, AsyncClient
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as ac:
        yield ac


@pytest.fixture
def mock_celery_tasks():
    """Mock all Celery task functions."""
    from contextlib import ExitStack

    fake_celery_app = MagicMock()
    fake_celery_app.control.revoke = MagicMock()

    patches = [
        patch("src.tasks.celery_app.discovery_pipeline"),
        patch("src.tasks.celery_app.research_pipeline"),
        patch("src.tasks.celery_app.run_sync_task"),
        patch("src.tasks.celery_app.sync_pipeline"),
        patch("src.tasks.goabase_tasks.goabase_sync_task"),
        patch("src.tasks.refresh_pipeline.refresh_unconfirmed_dates_task"),
        patch("src.tasks.refresh_pipeline.apply_approved_refresh_task"),
        patch("src.api.jobs.discovery_pipeline"),
        patch("src.api.jobs.research_pipeline"),
        patch("src.api.jobs.run_sync_task"),
        patch("src.api.jobs.goabase_sync_task"),
        patch("src.api.festivals.research_pipeline"),
        patch("src.api.festivals.deduplication_check"),
        patch("src.tasks.pipeline.discovery_pipeline"),
        patch("src.tasks.pipeline.research_pipeline"),
        patch("src.tasks.pipeline.run_sync_task"),
        patch("src.tasks.pipeline.sync_pipeline"),
        patch("src.tasks.goabase_tasks.goabase_sync_task"),
        patch("src.tasks.goabase_tasks.goabase_sync_stop_task"),
        patch("src.api.goabase.goabase_sync_task"),
        patch("src.api.goabase.goabase_sync_stop_task"),
        patch("src.api.refresh.apply_approved_refresh_task"),
        patch("src.api.settings.discovery_pipeline"),
        patch("src.tasks.celery_app.celery_app", fake_celery_app),
    ]

    with ExitStack() as stack:
        mocks = [stack.enter_context(p) for p in patches]
        (
            mock_d, mock_r, mock_sync, mock_s, mock_g, mock_refresh, mock_apply,
            mock_jobs_d, mock_jobs_r, mock_jobs_sync, mock_jobs_g,
            mock_festivals_r, mock_festivals_d,
            mock_pipe_d, mock_pipe_r, mock_pipe_sync, mock_pipe_sp, mock_gtask,
            mock_goabase_stop_task, mock_goabase_router_g, mock_goabase_router_stop,
            mock_refresh_apply, mock_settings_d, _fake_app,
        ) = mocks

        for mock in [mock_d, mock_r, mock_sync, mock_s, mock_g, mock_refresh, mock_apply,
                     mock_jobs_d, mock_jobs_r, mock_jobs_sync, mock_jobs_g,
                     mock_festivals_r, mock_festivals_d,
                     mock_pipe_d, mock_pipe_r, mock_pipe_sync, mock_pipe_sp, mock_gtask,
                     mock_goabase_stop_task, mock_goabase_router_g, mock_goabase_router_stop,
                     mock_refresh_apply, mock_settings_d]:
            mock.delay = MagicMock(return_value=MagicMock(id=f"task-{id(mock)}"))

        yield {
            "discovery": mock_d,
            "research": mock_r,
            "run_sync": mock_sync,
            "sync": mock_s,
            "goabase": mock_g,
            "refresh": mock_refresh,
            "apply_refresh": mock_apply,
        }


@pytest.fixture
def mock_partymap_client():
    """Mock PartyMapClient for deduplication and sync tests."""
    # Patch where PartyMapClient is actually imported in endpoint modules
    # (src.api.festivals doesn't import it directly, but pipeline tasks do)
    with patch("src.partymap.client.PartyMapClient") as MockClient:
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
    with patch("src.agents.streaming.get_broadcaster") as mock_get, \
         patch("src.api.agents.get_broadcaster") as mock_get_agents:
        broadcaster = AsyncMock()
        broadcaster.subscribe = AsyncMock(return_value=[])
        broadcaster.broadcast = AsyncMock()
        mock_get.return_value = broadcaster
        mock_get_agents.return_value = broadcaster
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


@pytest.fixture
def mock_redis_tracker():
    """Mock Redis for JobTracker tests (sync and async clients)."""
    store = {}  # In-memory Redis store

    class FakeAsyncRedis:
        async def get(self, key):
            return store.get(key)

        async def set(self, key, value, nx=False, ex=None):
            if nx and key in store:
                return None
            store[key] = value
            return True

        async def delete(self, key):
            store.pop(key, None)

    class FakeSyncRedis:
        def get(self, key):
            return store.get(key)

        def set(self, key, value, nx=False, ex=None):
            if nx and key in store:
                return None
            store[key] = value
            return True

        def delete(self, key):
            store.pop(key, None)

    with patch("src.core.job_tracker.get_async_redis_client") as mock_async, \
         patch("src.core.job_tracker.get_redis_client") as mock_sync:
        mock_async.return_value = FakeAsyncRedis()
        mock_sync.return_value = FakeSyncRedis()
        yield store


@pytest.fixture
def mock_job_activity():
    """Mock JobActivityLogger to avoid database writes in unit tests."""
    with patch("src.core.job_tracker.JobActivityLogger") as MockLogger:
        MockLogger.log_job_started = AsyncMock()
        MockLogger.log_job_completed = AsyncMock()
        MockLogger.log_job_failed = AsyncMock()
        MockLogger.log_job_stopped = AsyncMock()
        MockLogger.log_job_progress = AsyncMock()
        MockLogger.log_festival_started = AsyncMock()
        MockLogger.log_festival_completed = AsyncMock()
        MockLogger.log_activity = AsyncMock()
        yield MockLogger


@pytest.fixture
def mock_celery_result():
    """Mock Celery AsyncResult for JobTracker.inspect_and_sync_status tests."""

    class FakeAsyncResult:
        """Simple fake AsyncResult that doesn't rely on MagicMock."""
        def __init__(self, task_id, ready=False, successful=False, state="PENDING", result=None):
            self.task_id = task_id
            self._ready = ready
            self._successful = successful
            self.state = state
            self.result = result

        def ready(self):
            return self._ready

        def successful(self):
            return self._successful

    results = {}

    def make_result(task_id, ready=False, successful=False, state="PENDING", result=None):
        m = FakeAsyncResult(task_id, ready=ready, successful=successful, state=state, result=result)
        results[task_id] = m
        return m

    def get_result(task_id):
        if task_id in results:
            return results[task_id]
        return make_result(task_id)

    # Create a fake Celery app that returns our mocked AsyncResults
    # Use a plain class instead of MagicMock to avoid attribute-creation weirdness
    class FakeCeleryApp:
        def __init__(self):
            self.control = MagicMock()
            self.control.revoke = MagicMock()
            self.AsyncResult = MagicMock(side_effect=get_result)

    fake_app = FakeCeleryApp()

    # Patch both the global variable and the accessor so the fake app is always used
    with patch("src.core.job_tracker._celery_app", fake_app), \
         patch("src.core.job_tracker._get_celery_app", return_value=fake_app):
        yield {
            "make": make_result,
            "get": get_result,
            "results": results,
            "revoke": fake_app.control.revoke,
        }


@pytest.fixture(autouse=True)
def mock_all_redis():
    """Mock all Redis (sync + async) globally so tests never hit real Redis."""
    store = {}

    class FakeAsyncRedis:
        async def get(self, key):
            return store.get(key)

        async def set(self, key, value, nx=False, ex=None):
            if nx and key in store:
                return None
            store[key] = value
            return True

        async def delete(self, key):
            return store.pop(key, None)

        async def publish(self, channel, message):
            return 0

    class FakeSyncRedis:
        def get(self, key):
            return store.get(key)

        def set(self, key, value, nx=False, ex=None):
            if nx and key in store:
                return None
            store[key] = value
            return True

        def delete(self, key):
            return store.pop(key, None)

        def publish(self, channel, message):
            return 0

    # Patch async Redis everywhere
    with patch("src.core.database.get_async_redis_client") as m_db, \
         patch("src.partymap.client.get_async_redis_client") as m_pm, \
         patch("src.core.job_tracker.get_async_redis_client") as m_jt_async, \
         patch("src.core.job_tracker.get_redis_client") as m_jt_sync, \
         patch("src.agents.streaming.broadcaster.get_broadcaster") as m_broadcaster:

        fake_async = FakeAsyncRedis()
        fake_sync = FakeSyncRedis()

        m_db.return_value = fake_async
        m_pm.return_value = fake_async
        m_jt_async.return_value = fake_async
        m_jt_sync.return_value = fake_sync

        # Mock broadcaster to avoid real Redis pub/sub
        broadcaster = AsyncMock()
        broadcaster.subscribe = AsyncMock()
        broadcaster.unsubscribe = AsyncMock()
        broadcaster.broadcast = AsyncMock()
        m_broadcaster.return_value = broadcaster

        yield store


@pytest_asyncio.fixture(loop_scope="function", autouse=True)
async def patch_async_session_local(engine):
    """Reconfigure AsyncSessionLocal to use the test engine so code that
    bypasses FastAPI dependency injection still hits the test database."""
    from src.core.database import AsyncSessionLocal
    AsyncSessionLocal.configure(bind=engine)
    yield
    # Reset back to original engine (optional, but keeps module clean)
    from src.core.database import engine as original_engine
    AsyncSessionLocal.configure(bind=original_engine)


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
