"""Unit tests for data mappers."""

from datetime import datetime
from decimal import Decimal

import pytest

from src.core.schemas import EventDate, MediaItem, ResearchedFestival, TicketInfo
from src.partymap.mappers import FestivalMapper, GoabaseMapper


class TestFestivalMapper:
    """Test FestivalMapper."""

    def test_to_create_event_request(self):
        """Test mapping to create event request."""
        festival = ResearchedFestival(
            name="Test Festival",
            description="A test festival",
            full_description="Full description here",
            website_url="https://example.com",
            logo_url="https://example.com/logo.jpg",
            tags=["psytrance", "outdoor"],
            event_dates=[
                EventDate(
                    start=datetime(2026, 7, 15, 14, 0, 0),
                    end=datetime(2026, 7, 17, 23, 0, 0),
                    location_description="Berlin, Germany",
                    lineup=["Artist A", "Artist B"],
                    expected_size=5000,
                    tickets=[
                        TicketInfo(
                            url="https://tickets.example.com",
                            description="GA Ticket",
                            price_min=Decimal("50.00"),
                            price_max=Decimal("100.00"),
                            price_currency_code="EUR",
                        )
                    ],
                )
            ],
            media_items=[MediaItem(url="https://example.com/photo1.jpg", caption="Main stage")],
        )

        result = FestivalMapper.to_create_event_request(festival)

        assert result["name"] == "Test Festival"
        assert result["description"] == "A test festival"
        assert result["date_time"]["start"] == "2026-07-15T14:00:00"
        assert result["date_time"]["end"] == "2026-07-17T23:00:00"
        assert result["location"]["description"] == "Berlin, Germany"
        assert result["tags"] == ["psytrance", "outdoor"]
        assert result["logo"]["url"] == "https://example.com/logo.jpg"
        assert result["next_event_date_size"] == 5000
        assert len(result["next_event_date_artists"]) == 2
        assert result["next_event_date_artists"][0]["name"] == "Artist A"

    def test_to_create_event_request_no_dates(self):
        """Test mapping fails without event dates."""
        festival = ResearchedFestival(
            name="Test Festival",
            event_dates=[],
        )

        with pytest.raises(ValueError, match="event dates"):
            FestivalMapper.to_create_event_request(festival)

    def test_to_add_event_date_request(self):
        """Test mapping event date request."""
        event_date = EventDate(
            start=datetime(2026, 7, 15, 14, 0, 0),
            end=datetime(2026, 7, 17, 23, 0, 0),
            location_description="Berlin, Germany",
            lineup=["Artist A"],
            expected_size=5000,
        )

        result = FestivalMapper.to_add_event_date_request(event_date)

        assert result["start"] == "2026-07-15T14:00:00"
        assert result["end"] == "2026-07-17T23:00:00"
        assert result["description"] == "Berlin, Germany"
        assert result["size"] == 5000

    def test_to_update_event_request(self):
        """Test mapping update request."""
        festival = ResearchedFestival(
            name="Updated Name",
            description="Updated description",
            event_dates=[
                EventDate(
                    start=datetime(2026, 7, 15, 14, 0, 0),
                    location_description="Berlin",
                )
            ],
        )

        result = FestivalMapper.to_update_event_request(festival, "Test update")

        assert result["message"] == "Test update"
        assert result["name"] == "Updated Name"
        assert result["description"] == "Updated description"
        assert "date_time" in result

    def test_map_tickets(self):
        """Test ticket mapping."""
        tickets = [
            TicketInfo(
                url="https://tickets.example.com/ga",
                description="General Admission",
                price_min=Decimal("50.00"),
                price_max=Decimal("75.00"),
                price_currency_code="EUR",
            ),
            TicketInfo(
                description="VIP",
                price_min=Decimal("150.00"),
                price_currency_code="EUR",
            ),
        ]

        result = FestivalMapper._map_tickets(tickets)

        assert len(result) == 2
        assert result[0]["description"] == "General Admission"
        assert result[0]["price_min"] == 50.0
        assert result[0]["price_currency_code"] == "EUR"
        assert result[1]["price_max"] is None


class TestGoabaseMapper:
    """Test GoabaseMapper."""

    def test_map_event_list_item(self):
        """Test mapping event list item."""
        item = {
            "id": 12345,
            "name": "Psy Festival",
            "urlPartyJson": "https://goabase.net/api/party/12345/json",
        }

        result = GoabaseMapper.map_event_list_item(item)

        assert result["source"] == "goabase"
        assert result["source_id"] == "12345"
        assert result["source_url"] == "https://goabase.net/api/party/12345/json"

    def test_map_event_details(self):
        """Test mapping full event details."""
        json_data = {"party": {"dateModified": "2024-01-15T10:00:00"}}

        jsonld_data = {
            "name": "Amazing Psytrance Festival",
            "description": "Best festival ever",
            "startDate": "2026-07-15T14:00:00",
            "endDate": "2026-07-17T23:00:00",
            "location": {
                "name": "Mystic Woods",
                "address": {
                    "addressLocality": "Berlin",
                    "addressCountry": "Germany",
                },
            },
            "url": "https://example.com/festival",
            "performers": "Artist One, Artist Two, Artist Three",
            "image": {"url": "https://example.com/logo.jpg"},
            "nameType": "Open Air",
        }

        result = GoabaseMapper.map_event_details(json_data, jsonld_data)

        assert result.name == "Amazing Psytrance Festival"
        assert len(result.event_dates) == 1
        assert result.event_dates[0].location_description == "Mystic Woods, Berlin, Germany"
        assert len(result.event_dates[0].lineup) == 3
        assert "goabase" in result.tags
        assert "psytrance" in result.tags
        assert "open air" in result.tags

    def test_parse_description_with_lineup(self):
        """Test parsing description with lineup."""
        description = "Festival description"
        lineup = "Artist A, Artist B"

        result = GoabaseMapper._parse_description(description, lineup)

        assert description in result
        assert lineup in result

    def test_parse_description_empty(self):
        """Test parsing empty description."""
        result = GoabaseMapper._parse_description(None, "Lineup only")

        assert result == "Lineup only"

    def test_parse_description_coming_soon(self):
        """Test parsing 'coming' placeholder."""
        result = GoabaseMapper._parse_description("coming", "Real Lineup")

        assert result == "Real Lineup"

    def test_build_location_description_full(self):
        """Test building location with all fields."""
        location = {
            "name": "Venue Name",
            "address": {
                "streetAddress": "123 Main St",
                "addressLocality": "Berlin",
                "addressCountry": "Germany",
            },
        }

        result = GoabaseMapper._build_location_description(location)

        assert "Venue Name" in result
        assert "Berlin" in result
        assert "Germany" in result

    def test_build_location_description_partial(self):
        """Test building location with partial data."""
        location = {"name": "Venue Name"}

        result = GoabaseMapper._build_location_description(location)

        assert result == "Venue Name"

    def test_extract_hashtags(self):
        """Test hashtag extraction."""
        text = "Festival #psytrance #goa #outdoor fun"

        result = GoabaseMapper._extract_hashtags(text)

        assert "psytrance" in result
        assert "goa" in result
        assert "outdoor" in result

    def test_get_image_url_from_dict(self):
        """Test getting image URL from dict."""
        image = {"url": "https://example.com/image.jpg"}

        result = GoabaseMapper._get_image_url(image)

        assert result == "https://example.com/image.jpg"

    def test_get_image_url_from_list(self):
        """Test getting image URL from list."""
        image = [
            {"url": "https://example.com/image1.jpg"},
            {"url": "https://example.com/image2.jpg"},
        ]

        result = GoabaseMapper._get_image_url(image)

        assert result == "https://example.com/image1.jpg"

    def test_get_image_url_empty(self):
        """Test getting image URL when empty."""
        result = GoabaseMapper._get_image_url(None)

        assert result is None

    def test_parse_lineup(self):
        """Test parsing lineup string."""
        performers = "Artist A, Artist B; Artist C\nArtist D"

        result = GoabaseMapper._parse_lineup(performers)

        assert len(result) == 4
        assert "Artist A" in result
        assert "Artist D" in result

    def test_parse_lineup_tba(self):
        """Test parsing TBA lineup."""
        result = GoabaseMapper._parse_lineup("TBA")

        assert result == []

    def test_create_summary(self):
        """Test creating summary."""
        description = "A" * 500

        result = GoabaseMapper._create_summary(description, max_length=100)

        assert len(result) == 103  # 100 + "..."
        assert result.endswith("...")

    def test_create_summary_short(self):
        """Test creating summary from short description."""
        description = "Short description"

        result = GoabaseMapper._create_summary(description, max_length=100)

        assert result == description
