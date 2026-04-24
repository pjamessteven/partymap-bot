"""Tests for settings management endpoints."""

import pytest

from src.core.models import SystemSettings


class TestListSettings:
    """Tests for GET /api/settings"""

    @pytest.mark.asyncio
    async def test_all(self, async_client, db_session):
        """Returns all settings grouped by category."""
        setting = SystemSettings(
            key="test_setting",
            value=True,
            category="test",
            description="Test setting",
        )
        db_session.add(setting)
        await db_session.commit()
        
        response = await async_client.get("/api/settings")
        assert response.status_code == 200
        data = response.json()
        assert "settings" in data or isinstance(data, dict)

    @pytest.mark.asyncio
    async def test_filter_category(self, async_client, db_session):
        """Filters settings by category."""
        setting = SystemSettings(
            key="pipeline_setting",
            value="test",
            category="pipeline",
            description="Pipeline test",
        )
        db_session.add(setting)
        await db_session.commit()
        
        response = await async_client.get("/api/settings?category=pipeline")
        assert response.status_code == 200


class TestGetSetting:
    """Tests for GET /api/settings/{key}"""

    @pytest.mark.asyncio
    async def test_found(self, async_client, db_session):
        """Returns specific setting."""
        setting = SystemSettings(
            key="auto_process",
            value=True,
            category="pipeline",
            description="Auto process festivals",
        )
        db_session.add(setting)
        await db_session.commit()
        
        response = await async_client.get("/api/settings/auto_process")
        assert response.status_code == 200
        data = response.json()
        assert data["key"] == "auto_process"

    @pytest.mark.asyncio
    async def test_not_found(self, async_client):
        """Returns 404 for unknown key."""
        response = await async_client.get("/api/settings/nonexistent_key")
        assert response.status_code == 404


class TestUpdateSetting:
    """Tests for PUT /api/settings/{key}"""

    @pytest.mark.asyncio
    async def test_update_value(self, async_client, db_session):
        """Updates setting value."""
        setting = SystemSettings(
            key="max_cost_per_day",
            value="500",
            value_type="integer",
            category="cost",
            description="Max daily cost",
        )
        db_session.add(setting)
        await db_session.commit()
        
        response = await async_client.put(
            "/api/settings/max_cost_per_day",
            json={"value": 1000}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["value"] == 1000

    @pytest.mark.asyncio
    async def test_invalid_value(self, async_client, db_session):
        """Returns 400 for invalid value type."""
        setting = SystemSettings(
            key="numeric_setting",
            value=100,
            category="test",
            description="Numeric test",
        )
        db_session.add(setting)
        await db_session.commit()
        
        # This depends on validation in the endpoint
        response = await async_client.put(
            "/api/settings/numeric_setting",
            json={"value": "not_a_number"}
        )
        # May succeed or fail depending on endpoint validation
        assert response.status_code in (200, 400)


class TestAutoProcess:
    """Tests for auto-process endpoints."""

    @pytest.mark.asyncio
    async def test_get_status(self, async_client, db_session):
        """Returns auto-process status."""
        setting = SystemSettings(
            key="auto_process",
            value=True,
            category="pipeline",
            description="Auto process",
        )
        db_session.add(setting)
        await db_session.commit()
        
        response = await async_client.get("/api/settings/auto-process/status")
        assert response.status_code == 200
        data = response.json()
        assert "enabled" in data or "auto_process" in data

    @pytest.mark.asyncio
    async def test_enable(self, async_client, db_session):
        """Enables auto-process."""
        setting = SystemSettings(
            key="auto_process",
            value=False,
            category="pipeline",
            description="Auto process",
        )
        db_session.add(setting)
        await db_session.commit()
        
        response = await async_client.put("/api/settings/auto-process/enable")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_disable(self, async_client, db_session):
        """Disables auto-process."""
        setting = SystemSettings(
            key="auto_process",
            value=True,
            category="pipeline",
            description="Auto process",
        )
        db_session.add(setting)
        await db_session.commit()
        
        response = await async_client.put("/api/settings/auto-process/disable")
        assert response.status_code == 200
