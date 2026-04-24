"""Tests for PartyMapSyncValidator and validation logic."""

import pytest
from datetime import datetime, timedelta

from src.core.validators import PartyMapSyncValidator, validate_festival_for_sync
from src.core.schemas import FestivalData, EventDateData, MediaItem, TicketInfo


class TestPartyMapSyncValidator:
    """Tests for pre-flight sync validation."""

    def test_valid_festival(self):
        """Complete valid data passes validation."""
        data = FestivalData(
            name="Test Festival",
            description="A great festival description",
            full_description="A full description that is definitely long enough",
            event_dates=[
                EventDateData(
                    start=datetime(2026, 7, 15, 14, 0, 0),
                    end=datetime(2026, 7, 17, 23, 0, 0),
                    location_description="Berlin, Germany",
                    location_country="Germany",
                    location_lat=52.5,
                    location_lng=13.4,
                    lineup=["Artist A", "Artist B"],
                    tickets=[
                        TicketInfo(
                            url="https://tickets.example.com/ga",
                            price_min=50,
                            price_max=100,
                            price_currency_code="USD",
                        )
                    ],
                )
            ],
            logo_url="https://example.com/logo.jpg",
            website_url="https://example.com",
            youtube_url="https://youtube.com/watch?v=123",
            tags=["music", "festival", "outdoor"],
            media_items=[MediaItem(url="https://example.com/photo.jpg", caption="Photo")],
        )
        validator = PartyMapSyncValidator()
        result = validator.validate(data)

        assert result.is_valid is True
        assert result.status == "ready"
        assert result.completeness_score >= 0.8
        assert len(result.errors) == 0

    def test_missing_name(self):
        """Too-short name returns validation error."""
        data = FestivalData(
            name="A",  # Passes Pydantic min_length=1, fails validator MIN_NAME_LENGTH=2
            description="A great festival description",
            full_description="A full description that is definitely long enough",
            event_dates=[
                EventDateData(
                    start=datetime(2026, 7, 15, 14, 0, 0),
                    location_description="Berlin, Germany",
                )
            ],
        )
        validator = PartyMapSyncValidator()
        result = validator.validate(data)

        assert result.is_valid is False
        assert result.status == "invalid"
        assert any(e["field"] == "name" for e in result.errors)

    def test_short_description(self):
        """Description < 10 chars fails."""
        data = FestivalData(
            name="Test Festival",
            description="Short",
            full_description="A full description that is definitely long enough",
            event_dates=[
                EventDateData(
                    start=datetime(2026, 7, 15, 14, 0, 0),
                    location_description="Berlin, Germany",
                )
            ],
        )
        validator = PartyMapSyncValidator()
        result = validator.validate(data)
        
        assert result.is_valid is False
        assert any(e["field"] == "description" for e in result.errors)

    def test_end_before_start(self):
        """End date before start date returns error."""
        data = FestivalData(
            name="Test Festival",
            description="A great festival description",
            full_description="A full description that is definitely long enough",
            event_dates=[
                EventDateData(
                    start=datetime(2026, 7, 17, 23, 0, 0),
                    end=datetime(2026, 7, 15, 14, 0, 0),  # Before start
                    location_description="Berlin, Germany",
                )
            ],
        )
        validator = PartyMapSyncValidator()
        result = validator.validate(data)
        
        assert any(e["field"].endswith(".end") for e in result.errors)

    def test_missing_logo(self):
        """Missing logo_url returns error for PartyMap sync."""
        data = FestivalData(
            name="Test Festival",
            description="A great festival description",
            full_description="A full description that is definitely long enough",
            event_dates=[
                EventDateData(
                    start=datetime(2026, 7, 15, 14, 0, 0),
                    location_description="Berlin, Germany",
                )
            ],
            # No logo_url
        )
        validator = PartyMapSyncValidator()
        result = validator.validate(data)
        
        assert result.is_valid is False
        assert any(e["field"] == "logo_url" for e in result.errors)

    def test_past_date_warning(self):
        """Past dates generate warnings but don't fail."""
        data = FestivalData(
            name="Test Festival",
            description="A great festival description",
            full_description="A full description that is definitely long enough",
            event_dates=[
                EventDateData(
                    start=datetime(2020, 7, 15, 14, 0, 0),  # Past
                    end=datetime(2020, 7, 17, 23, 0, 0),
                    location_description="Berlin, Germany",
                )
            ],
            logo_url="https://example.com/logo.jpg",
        )
        validator = PartyMapSyncValidator()
        result = validator.validate(data)
        
        assert any("past" in w["message"].lower() for w in result.warnings)

    def test_invalid_url(self):
        """Invalid URLs are rejected by _is_valid_url helper."""
        validator = PartyMapSyncValidator()

        # Direct test of URL validation logic (Pydantic blocks invalid URLs at construction,
        # so we test the validator's internal check directly)
        assert validator._is_valid_url("not-a-valid-url") is False
        assert validator._is_valid_url("ftp://example.com") is False  # Wrong scheme
        assert validator._is_valid_url("http://") is False  # Missing netloc
        assert validator._is_valid_url("https://example.com") is True
        assert validator._is_valid_url("http://localhost:8000") is True

    def test_completeness_score(self):
        """Completeness score calculated between 0 and 1."""
        # Minimal data
        data = FestivalData(
            name="Test",
            description="Description",
            full_description="Full description that is long enough",
            event_dates=[
                EventDateData(
                    start=datetime(2026, 7, 15, 14, 0, 0),
                    location_description="Berlin",
                )
            ],
        )
        validator = PartyMapSyncValidator()
        result = validator.validate(data)
        
        assert 0.0 <= result.completeness_score <= 1.0
        # Minimal data should have low score
        assert result.completeness_score < 0.8

    def test_convenience_function(self):
        """validate_festival_for_sync convenience function works."""
        data = FestivalData(
            name="Test",
            description="A great festival description",
            full_description="A full description that is definitely long enough",
            event_dates=[
                EventDateData(
                    start=datetime(2026, 7, 15, 14, 0, 0),
                    location_description="Berlin, Germany",
                )
            ],
            logo_url="https://example.com/logo.jpg",
        )
        result = validate_festival_for_sync(data)
        
        assert result.status in ("ready", "needs_review")
