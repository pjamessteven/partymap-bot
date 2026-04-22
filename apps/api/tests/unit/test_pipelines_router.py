"""Tests for pipeline control endpoints."""

import pytest


class TestPipelineStatus:
    """Tests for pipeline status endpoints."""

    @pytest.mark.asyncio
    async def test_all_pipelines(self, async_client):
        """Returns status for all pipelines."""
        response = await async_client.get("/api/pipelines/status")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "pipelines" in data

    @pytest.mark.asyncio
    async def test_specific_pipeline(self, async_client):
        """Returns status for specific pipeline."""
        response = await async_client.get("/api/pipelines/discovery/status")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "pipeline" in data


class TestStartStop:
    """Tests for pipeline start/stop."""

    @pytest.mark.asyncio
    async def test_start_discovery(self, async_client, mock_celery_tasks):
        """Starts discovery pipeline."""
        response = await async_client.post("/api/pipelines/discovery/start")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data

    @pytest.mark.asyncio
    async def test_stop_pipeline(self, async_client):
        """Stops a pipeline."""
        response = await async_client.post("/api/pipelines/discovery/stop")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_stop_all(self, async_client):
        """Stops all pipelines."""
        response = await async_client.post("/api/pipelines/stop-all")
        assert response.status_code == 200
        data = response.json()
        assert "stopped_pipelines" in data
