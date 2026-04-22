"""Tests for Goabase sync endpoints."""

import pytest


class TestGoabaseSync:
    """Tests for Goabase sync operations."""

    @pytest.mark.asyncio
    async def test_start(self, async_client, mock_celery_tasks):
        """Starts Goabase sync."""
        response = await async_client.post("/api/goabase/sync/start")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "task_id" in data

    @pytest.mark.asyncio
    async def test_stop(self, async_client):
        """Stops Goabase sync."""
        response = await async_client.post("/api/goabase/sync/stop")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_status(self, async_client):
        """Returns Goabase sync status."""
        response = await async_client.get("/api/goabase/sync/status")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data


class TestGoabaseSettings:
    """Tests for Goabase settings."""

    @pytest.mark.asyncio
    async def test_get(self, async_client):
        """Returns Goabase settings."""
        response = await async_client.get("/api/goabase/settings")
        assert response.status_code == 200
        data = response.json()
        assert "goabase_sync_enabled" in data or "settings" in data

    @pytest.mark.asyncio
    async def test_update(self, async_client):
        """Updates Goabase settings."""
        response = await async_client.put(
            "/api/goabase/settings",
            json={
                "goabase_sync_enabled": True,
                "goabase_sync_frequency": "weekly",
                "goabase_sync_day": "monday",
                "goabase_sync_hour": 3,
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "settings" in data or "status" in data
