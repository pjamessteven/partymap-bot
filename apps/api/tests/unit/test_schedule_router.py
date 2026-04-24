"""Tests for schedule management endpoints (unified under settings)."""

import pytest

from src.core.models import PipelineSchedule


class TestGetSchedules:
    """Tests for GET /api/settings/schedules"""

    @pytest.mark.asyncio
    async def test_list_all(self, async_client, db_session):
        """Returns all schedule configurations."""
        schedule = PipelineSchedule(
            task_type="discovery",
            enabled=True,
            hour=2,
            minute=0,
        )
        db_session.add(schedule)
        await db_session.commit()

        response = await async_client.get("/api/settings/schedules")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1


class TestGetSchedule:
    """Tests for GET /api/settings/schedules/{task_type}"""

    @pytest.mark.asyncio
    async def test_found(self, async_client, db_session):
        """Returns specific schedule."""
        schedule = PipelineSchedule(
            task_type="discovery",
            enabled=True,
            hour=2,
            minute=0,
        )
        db_session.add(schedule)
        await db_session.commit()

        response = await async_client.get("/api/settings/schedules/discovery")
        assert response.status_code == 200
        data = response.json()
        assert data["task_type"] == "discovery"
        assert data["hour"] == 2

    @pytest.mark.asyncio
    async def test_not_found(self, async_client):
        """Returns 404 for unknown task type."""
        response = await async_client.get("/api/settings/schedules/unknown_task")
        assert response.status_code == 404


class TestUpdateSchedule:
    """Tests for PUT /api/settings/schedules/{task_type}"""

    @pytest.mark.asyncio
    async def test_update_time(self, async_client, db_session):
        """Updates schedule hour and minute."""
        schedule = PipelineSchedule(
            task_type="discovery",
            enabled=True,
            hour=2,
            minute=0,
        )
        db_session.add(schedule)
        await db_session.commit()

        response = await async_client.put(
            "/api/settings/schedules/discovery",
            json={"hour": 4, "minute": 30}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["hour"] == 4
        assert data["minute"] == 30

    @pytest.mark.asyncio
    async def test_invalid_time(self, async_client, db_session):
        """Returns 400 for invalid time values."""
        schedule = PipelineSchedule(
            task_type="discovery",
            enabled=True,
            hour=2,
            minute=0,
        )
        db_session.add(schedule)
        await db_session.commit()

        response = await async_client.put(
            "/api/settings/schedules/discovery",
            json={"hour": 25, "minute": 0}
        )
        assert response.status_code == 400


class TestEnableDisable:
    """Tests for enable/disable endpoints."""

    @pytest.mark.asyncio
    async def test_enable(self, async_client, db_session):
        """Enables schedule."""
        schedule = PipelineSchedule(
            task_type="discovery",
            enabled=False,
            hour=2,
            minute=0,
        )
        db_session.add(schedule)
        await db_session.commit()

        response = await async_client.post("/api/settings/schedules/discovery/enable")
        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is True

    @pytest.mark.asyncio
    async def test_disable(self, async_client, db_session):
        """Disables schedule."""
        schedule = PipelineSchedule(
            task_type="discovery",
            enabled=True,
            hour=2,
            minute=0,
        )
        db_session.add(schedule)
        await db_session.commit()

        response = await async_client.post("/api/settings/schedules/discovery/disable")
        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is False


class TestApply:
    """Tests for POST /api/settings/schedules/apply"""

    @pytest.mark.asyncio
    async def test_force_reload(self, async_client):
        """Forces scheduler to reload from DB."""
        response = await async_client.post("/api/settings/schedules/apply")
        assert response.status_code == 200


class TestRunNow:
    """Tests for POST /api/settings/schedules/run-now/{task_type}"""

    @pytest.mark.asyncio
    async def test_trigger(self, async_client, db_session, mock_celery_tasks):
        """Manually triggers scheduled task."""
        from src.core.models import PipelineSchedule
        schedule = PipelineSchedule(task_type="discovery", enabled=True, hour=2, minute=0)
        db_session.add(schedule)
        await db_session.commit()

        response = await async_client.post("/api/settings/schedules/run-now/discovery")
        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data or "message" in data
