"""Tests for Pydantic schema validators."""

import pytest
from datetime import datetime

from src.core.schemas import (
    AgentDecisionLog,
    DiscoveredFestival,
    DuplicateCheckResult,
    EventDateData,
    FestivalActionRequest,
    FestivalActionResponse,
    FestivalData,
    FestivalState,
    FestivalUpdateRequest,
    FestivalUpdateResponse,
    DeduplicationResultResponse,
    PartyMapAddEventDateRequest,
    PartyMapCreateEventRequest,
    PartyMapUpdateEventDateRequest,
    PartyMapUpdateEventRequest,
    ResearchFailure,
    ResearchResult,
    ResearchedFestival,
    RRuleData,
    SchemaValidationResult,
    SystemSettingUpdate,
    TicketInfo,
    ValidationResult,
)


class TestFestivalDataValidateForSync:
    """Tests for FestivalData.validate_for_sync() method."""

    def _make_valid(self):
        return FestivalData(
            name="Test Festival",
            description="A great festival description",
            full_description="A full description that is definitely long enough",
            event_dates=[
                EventDateData(
                    start=datetime(2026, 7, 15, 14, 0, 0),
                    end=datetime(2026, 7, 17, 23, 0, 0),
                    location_description="Berlin, Germany",
                )
            ],
            logo_url="https://example.com/logo.jpg",
            tags=["music", "outdoor"],
            media_items=[
                {"url": "https://example.com/photo.jpg", "caption": "Photo"}
            ],
            website_url="https://example.com",
        )

    def test_ready_all_fields_valid(self):
        """All required fields present → status='ready'."""
        data = self._make_valid()
        result = data.validate_for_sync()

        assert result.status == "ready"
        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_invalid_missing_logo(self):
        """Missing logo_url → status='invalid'."""
        data = self._make_valid()
        data = data.model_copy(update={"logo_url": None})
        result = data.validate_for_sync()

        assert result.status == "invalid"
        assert result.is_valid is False
        assert any(e["field"] == "logo_url" for e in result.errors)

    def test_invalid_missing_name(self):
        """Missing name → status='invalid'."""
        data = self._make_valid()
        data = data.model_copy(update={"name": ""})
        result = data.validate_for_sync()

        assert result.status == "invalid"
        assert any(e["field"] == "name" for e in result.errors)

    def test_invalid_short_description(self):
        """Description < 10 chars → status='invalid'."""
        data = self._make_valid()
        data = data.model_copy(update={"description": "Short"})
        result = data.validate_for_sync()

        assert result.status == "invalid"
        assert any(e["field"] == "description" for e in result.errors)

    def test_invalid_short_full_description(self):
        """Full description < 20 chars → status='invalid'."""
        data = self._make_valid()
        data = data.model_copy(update={"full_description": "Too short"})
        result = data.validate_for_sync()

        assert result.status == "invalid"
        assert any(e["field"] == "full_description" for e in result.errors)

    def test_invalid_no_event_dates(self):
        """No event dates → status='invalid'."""
        data = self._make_valid()
        data = data.model_copy(update={"event_dates": []})
        result = data.validate_for_sync()

        assert result.status == "invalid"
        assert any(e["field"] == "event_dates" for e in result.errors)

    def test_invalid_end_before_start(self):
        """End date before start date → error."""
        data = FestivalData(
            name="Test",
            description="A great festival description",
            full_description="A full description that is definitely long enough",
            event_dates=[
                EventDateData(
                    start=datetime(2026, 7, 17, 23, 0, 0),
                    end=datetime(2026, 7, 15, 14, 0, 0),
                    location_description="Berlin, Germany",
                )
            ],
            logo_url="https://example.com/logo.jpg",
        )
        result = data.validate_for_sync()

        assert any("end" in e["field"] for e in result.errors)

    def test_needs_review_past_date(self):
        """Past date generates warning → status='needs_review'."""
        data = FestivalData(
            name="Test Festival",
            description="A great festival description",
            full_description="A full description that is definitely long enough",
            event_dates=[
                EventDateData(
                    start=datetime(2020, 7, 15, 14, 0, 0),
                    location_description="Berlin, Germany",
                )
            ],
            logo_url="https://example.com/logo.jpg",
        )
        result = data.validate_for_sync()

        assert result.status == "needs_review"
        assert any("past" in w["message"].lower() for w in result.warnings)

    def test_invalid_missing_location(self):
        """Missing location description → error."""
        data = FestivalData(
            name="Test Festival",
            description="A great festival description",
            full_description="A full description that is definitely long enough",
            event_dates=[
                EventDateData(
                    start=datetime(2026, 7, 15, 14, 0, 0),
                    location_description="",
                )
            ],
            logo_url="https://example.com/logo.jpg",
        )
        result = data.validate_for_sync()

        assert any("location" in e["field"] for e in result.errors)

    def test_invalid_ticket_price_max_less_than_min(self):
        """ticket.price_max < price_min → error."""
        data = FestivalData(
            name="Test Festival",
            description="A great festival description",
            full_description="A full description that is definitely long enough",
            event_dates=[
                EventDateData(
                    start=datetime(2026, 7, 15, 14, 0, 0),
                    location_description="Berlin, Germany",
                    tickets=[
                        TicketInfo(
                            price_min=100,
                            price_max=50,  # Invalid: max < min
                            price_currency_code="USD",
                        )
                    ],
                )
            ],
            logo_url="https://example.com/logo.jpg",
        )
        result = data.validate_for_sync()

        assert any("price_max" in e["field"] for e in result.errors)

    def test_completeness_score_calculation(self):
        """Completeness score is 0.0-1.0."""
        data = self._make_valid()
        result = data.validate_for_sync()

        assert 0.0 <= result.completeness_score <= 1.0
        assert result.completeness_score >= 0.8

    def test_missing_fields_tracking(self):
        """Missing fields are tracked in missing_fields list."""
        # Use model_construct to bypass Pydantic validation and test the method directly
        data = FestivalData.model_construct(
            name="",
            description="",
            full_description="",
            event_dates=[
                EventDateData(
                    start=datetime(2026, 7, 15, 14, 0, 0),
                    location_description="Berlin, Germany",
                )
            ],
            logo_url=None,
        )
        result = data.validate_for_sync()

        assert "name" in result.missing_fields
        assert "description" in result.missing_fields
        assert "full_description" in result.missing_fields
        assert "logo_url" in result.missing_fields


class TestEventDateDataCleanLineup:
    """Tests for EventDateData.clean_lineup validator."""

    def test_deduplicates_artists(self):
        """Duplicate artists are removed."""
        ed = EventDateData(
            start=datetime(2026, 7, 15, 14, 0, 0),
            location_description="Berlin",
            lineup=["Artist A", "Artist A", "Artist B"],
        )
        assert ed.lineup == ["Artist A", "Artist B"]

    def test_title_cases_artists(self):
        """Artists are title-cased."""
        ed = EventDateData(
            start=datetime(2026, 7, 15, 14, 0, 0),
            location_description="Berlin",
            lineup=["artist a", "ARTIST B"],
        )
        assert ed.lineup == ["Artist A", "Artist B"]

    def test_strips_whitespace(self):
        """Whitespace is stripped from artist names."""
        ed = EventDateData(
            start=datetime(2026, 7, 15, 14, 0, 0),
            location_description="Berlin",
            lineup=["  Artist A  ", " Artist B "],
        )
        assert ed.lineup == ["Artist A", "Artist B"]

    def test_case_insensitive_dedup(self):
        """Case-insensitive deduplication."""
        ed = EventDateData(
            start=datetime(2026, 7, 15, 14, 0, 0),
            location_description="Berlin",
            lineup=["Artist A", "artist a", "ARTIST A"],
        )
        assert ed.lineup == ["Artist A"]

    def test_empty_lineup(self):
        """Empty lineup stays empty."""
        ed = EventDateData(
            start=datetime(2026, 7, 15, 14, 0, 0),
            location_description="Berlin",
            lineup=[],
        )
        assert ed.lineup == []

    def test_none_lineup(self):
        """None lineup becomes empty list."""
        ed = EventDateData(
            start=datetime(2026, 7, 15, 14, 0, 0),
            location_description="Berlin",
            lineup=None,
        )
        assert ed.lineup == []

    def test_filters_empty_strings(self):
        """Empty strings are filtered out."""
        ed = EventDateData(
            start=datetime(2026, 7, 15, 14, 0, 0),
            location_description="Berlin",
            lineup=["Artist A", "", "   ", "Artist B"],
        )
        assert ed.lineup == ["Artist A", "Artist B"]


class TestTicketInfoCurrencyCode:
    """Tests for TicketInfo.price_currency_code regex."""

    def test_valid_uppercase_currency(self):
        """3 uppercase letters pass."""
        ticket = TicketInfo(price_currency_code="USD")
        assert ticket.price_currency_code == "USD"

    def test_valid_eur(self):
        ticket = TicketInfo(price_currency_code="EUR")
        assert ticket.price_currency_code == "EUR"

    def test_lowercase_fails(self):
        """Lowercase fails regex pattern."""
        with pytest.raises(Exception):
            TicketInfo(price_currency_code="usd")

    def test_two_chars_fails(self):
        """Only 2 chars fails."""
        with pytest.raises(Exception):
            TicketInfo(price_currency_code="US")

    def test_four_chars_fails(self):
        """4 chars fails."""
        with pytest.raises(Exception):
            TicketInfo(price_currency_code="USDD")

    def test_numbers_fails(self):
        """Numbers fail."""
        with pytest.raises(Exception):
            TicketInfo(price_currency_code="US1")


class TestFestivalUpdateRequest:
    """Tests for FestivalUpdateRequest validators."""

    def test_rejects_empty_dict(self):
        """Empty research_data raises ValueError."""
        with pytest.raises(ValueError, match="cannot be empty"):
            FestivalUpdateRequest(research_data={})

    def test_rejects_missing_name(self):
        """research_data without 'name' raises ValueError."""
        with pytest.raises(ValueError, match="must contain 'name'"):
            FestivalUpdateRequest(research_data={"description": "test"})

    def test_accepts_valid_data(self):
        """Valid research_data with name passes."""
        req = FestivalUpdateRequest(research_data={"name": "Test Festival"})
        assert req.research_data["name"] == "Test Festival"

    def test_rejects_non_dict(self):
        """Non-dict research_data raises ValidationError (Pydantic v2 type check runs first)."""
        with pytest.raises(Exception):  # Pydantic ValidationError
            FestivalUpdateRequest(research_data="not a dict")


class TestSystemSettingUpdate:
    """Tests for SystemSettingUpdate validators."""

    def test_rejects_none_value(self):
        """None value raises ValueError."""
        with pytest.raises(ValueError, match="cannot be None"):
            SystemSettingUpdate(value=None)

    def test_accepts_string(self):
        """String value passes."""
        req = SystemSettingUpdate(value="test")
        assert req.value == "test"

    def test_accepts_boolean(self):
        """Boolean value passes."""
        req = SystemSettingUpdate(value=True)
        assert req.value is True

    def test_accepts_zero(self):
        """Zero (falsy but not None) passes."""
        req = SystemSettingUpdate(value=0)
        assert req.value == 0

    def test_accepts_empty_string(self):
        """Empty string (falsy but not None) passes."""
        req = SystemSettingUpdate(value="")
        assert req.value == ""


class TestRRuleData:
    """Tests for RRuleData field validation."""

    def test_defaults(self):
        """Default values are sensible."""
        rrule = RRuleData()
        assert rrule.recurringType == 3  # yearly
        assert rrule.separationCount == 1
        assert rrule.dayOfWeek is None
        assert rrule.exact is False

    def test_valid_fields(self):
        """Valid field values pass."""
        rrule = RRuleData(
            recurringType=2,
            separationCount=3,
            dayOfWeek=1,
            weekOfMonth=2,
            monthOfYear=6,
            dayOfMonth=15,
            exact=True,
        )
        assert rrule.recurringType == 2
        assert rrule.separationCount == 3

    def test_negative_separation_count(self):
        """Negative separationCount is allowed by schema (validated elsewhere)."""
        rrule = RRuleData(separationCount=-1)
        assert rrule.separationCount == -1


class TestPartyMapCreateEventRequest:
    """Tests for PartyMapCreateEventRequest schema."""

    def test_required_fields(self):
        """Minimum required fields pass."""
        req = PartyMapCreateEventRequest(
            name="Test Festival",
            description="A great festival",
            full_description="A much longer description for the festival",
        )
        assert req.name == "Test Festival"
        assert req.description == "A great festival"

    def test_optional_fields(self):
        """Optional fields are accepted."""
        req = PartyMapCreateEventRequest(
            name="Test",
            description="Desc",
            full_description="Full desc",
            youtube_url="https://youtube.com/watch?v=123",
            url="https://example.com",
            tags=["music", "festival"],
            logo={"url": "https://example.com/logo.jpg"},
            media_items=[{"url": "https://example.com/photo.jpg", "caption": "Photo"}],
        )
        assert req.logo["url"] == "https://example.com/logo.jpg"
        assert len(req.media_items) == 1

    def test_no_ticket_url_field(self):
        """Schema does not include ticket_url (tickets go on EventDate, not Event)."""
        assert "ticket_url" not in PartyMapCreateEventRequest.model_fields


class TestPartyMapAddEventDateRequest:
    """Tests for PartyMapAddEventDateRequest schema."""

    def test_required_start(self):
        """Start date is required."""
        req = PartyMapAddEventDateRequest(
            start=datetime(2026, 7, 15, 14, 0, 0),
        )
        assert req.start.year == 2026

    def test_uses_tickets_not_ticket_url(self):
        """Schema accepts structured tickets, NOT a flat ticket_url."""
        assert "ticket_url" not in PartyMapAddEventDateRequest.model_fields
        req = PartyMapAddEventDateRequest(
            start=datetime(2026, 7, 15, 14, 0, 0),
            tickets=[
                {
                    "url": "https://tickets.example.com",
                    "description": "GA",
                    "price_min": 50.0,
                    "price_max": 100.0,
                    "price_currency_code": "USD",
                }
            ],
        )
        assert req.tickets[0]["url"] == "https://tickets.example.com"

    def test_artists_format(self):
        """Artists are list of dicts with name."""
        req = PartyMapAddEventDateRequest(
            start=datetime(2026, 7, 15, 14, 0, 0),
            artists=[{"name": "Artist A"}, {"name": "Artist B"}],
        )
        assert len(req.artists) == 2

    def test_lineup_images(self):
        """Lineup images accepted as list of dicts."""
        req = PartyMapAddEventDateRequest(
            start=datetime(2026, 7, 15, 14, 0, 0),
            lineup_images=[{"url": "https://example.com/lineup.jpg"}],
        )
        assert req.lineup_images[0]["url"] == "https://example.com/lineup.jpg"


class TestPartyMapUpdateEventRequest:
    """Tests for PartyMapUpdateEventRequest schema."""

    def test_all_optional(self):
        """All fields are optional for updates."""
        req = PartyMapUpdateEventRequest()
        assert req.message == "Updated by festival bot"

    def test_partial_update(self):
        """Partial update with just name works."""
        req = PartyMapUpdateEventRequest(name="New Name")
        assert req.name == "New Name"
        assert req.description is None

    def test_tag_mutations(self):
        """add_tags and remove_tags are lists."""
        req = PartyMapUpdateEventRequest(
            add_tags=["electronic"],
            remove_tags=["old_tag"],
        )
        assert req.add_tags == ["electronic"]

    def test_no_ticket_url_field(self):
        """Update event schema does not include ticket_url."""
        assert "ticket_url" not in PartyMapUpdateEventRequest.model_fields


class TestPartyMapUpdateEventDateRequest:
    """Tests for PartyMapUpdateEventDateRequest schema."""

    def test_all_optional(self):
        """All fields are optional for date updates."""
        req = PartyMapUpdateEventDateRequest()
        assert req.start is None
        assert req.end is None

    def test_uses_tickets_not_ticket_url(self):
        """Schema accepts structured tickets, NOT a flat ticket_url."""
        assert "ticket_url" not in PartyMapUpdateEventDateRequest.model_fields
        req = PartyMapUpdateEventDateRequest(
            tickets=[{"url": "https://tickets.example.com", "price_currency_code": "EUR"}],
        )
        assert req.tickets[0]["price_currency_code"] == "EUR"


class TestDiscoveredFestival:
    """Tests for DiscoveredFestival schema."""

    def test_defaults(self):
        """Default values are sensible."""
        df = DiscoveredFestival(source="goabase")
        assert df.state == FestivalState.DISCOVERED
        assert df.discovered_data == {}
        assert df.update_required is False
        assert df.update_reasons == []

    def test_from_attributes_config(self):
        """model_config has from_attributes=True."""
        assert DiscoveredFestival.model_config.get("from_attributes") is True


class TestResearchedFestival:
    """Tests for ResearchedFestival schema."""

    def test_defaults(self):
        """Default values are sensible."""
        rf = ResearchedFestival(
            festival_data=FestivalData(
                name="Test",
                description="A great festival description",
                full_description="A full description that is definitely long enough",
                event_dates=[
                    EventDateData(
                        start=datetime(2026, 7, 15, 14, 0, 0),
                        location_description="Berlin",
                    )
                ],
            )
        )
        assert rf.is_duplicate is False
        assert rf.date_confirmed is True
        assert rf.partymap_event_id is None

    def test_partymap_event_id_is_int(self):
        """partymap_event_id should be an int (PartyMap API uses integer IDs)."""
        rf = ResearchedFestival(
            festival_data=FestivalData(
                name="Test",
                description="A great festival description",
                full_description="A full description that is definitely long enough",
                event_dates=[
                    EventDateData(
                        start=datetime(2026, 7, 15, 14, 0, 0),
                        location_description="Berlin",
                    )
                ],
            ),
            partymap_event_id=12345,
        )
        assert rf.partymap_event_id == 12345
        assert isinstance(rf.partymap_event_id, int)


class TestDuplicateCheckResult:
    """Tests for DuplicateCheckResult schema."""

    def test_defaults(self):
        """Default values for non-duplicate result."""
        dcr = DuplicateCheckResult(is_duplicate=False)
        assert dcr.confidence == 0.0
        assert dcr.reason == ""
        assert dcr.is_new_event_date is False
        assert dcr.date_confirmed is True
        assert dcr.existing_event_data is None

    def test_duplicate_with_data(self):
        """Duplicate result with cached event data."""
        dcr = DuplicateCheckResult(
            is_duplicate=True,
            existing_event_id=12345,
            confidence=0.95,
            reason="Name and location match",
            existing_event_data={"id": 12345, "name": "Test Festival"},
        )
        assert dcr.existing_event_id == 12345
        assert dcr.existing_event_data["name"] == "Test Festival"


class TestResearchResult:
    """Tests for ResearchResult and ResearchFailure schemas."""

    def test_successful_research(self):
        """Successful research has festival_data."""
        data = FestivalData(
            name="Test",
            description="A great festival description",
            full_description="A full description that is definitely long enough",
            event_dates=[
                EventDateData(
                    start=datetime(2026, 7, 15, 14, 0, 0),
                    location_description="Berlin",
                )
            ],
        )
        result = ResearchResult(success=True, festival_data=data)
        assert result.festival_data.name == "Test"
        assert result.failure is None

    def test_failed_research(self):
        """Failed research has failure info."""
        failure = ResearchFailure(
            reason="dates",
            message="Dates not released yet",
            completeness_score=0.3,
        )
        result = ResearchResult(success=False, failure=failure)
        assert result.festival_data is None
        assert result.failure.reason == "dates"
        assert result.failure.completeness_score == 0.3

    def test_research_failure_bounds(self):
        """Completeness score must be between 0 and 1."""
        with pytest.raises(Exception):
            ResearchFailure(reason="test", message="test", completeness_score=1.5)


class TestSchemaValidationResult:
    """Tests for SchemaValidationResult schema."""

    def test_valid_result(self):
        """Valid result has high score."""
        result = SchemaValidationResult(
            is_valid=True,
            failure_reason="none",
            completeness_score=0.95,
        )
        assert result.missing_fields == []

    def test_score_bounds(self):
        """Score must be 0.0-1.0."""
        with pytest.raises(Exception):
            SchemaValidationResult(
                is_valid=False,
                failure_reason="test",
                completeness_score=1.5,
            )


class TestFestivalActionSchemas:
    """Tests for action request/response schemas."""

    def test_action_request(self):
        """Valid action request."""
        req = FestivalActionRequest(action="research")
        assert req.action.value == "research"
        assert req.reason is None

    def test_action_request_with_reason(self):
        """Action request with optional reason."""
        req = FestivalActionRequest(action="sync", reason="Manual retry")
        assert req.reason == "Manual retry"

    def test_action_response(self):
        """Action response construction."""
        resp = FestivalActionResponse(
            festival_id="550e8400-e29b-41d4-a716-446655440000",
            action="research",
            result="queued",
            message="Queued for research",
            previous_state=FestivalState.NEEDS_RESEARCH_NEW,
            new_state=FestivalState.RESEARCHING,
            queued=True,
        )
        assert resp.result.value == "queued"
        assert resp.queued is True


class TestDeduplicationResultResponse:
    """Tests for DeduplicationResultResponse schema."""

    def test_new_event(self):
        """Result for a new (non-duplicate) event."""
        resp = DeduplicationResultResponse(
            festival_id="550e8400-e29b-41d4-a716-446655440000",
            is_duplicate=False,
            confidence=0.0,
            reason="No matching event found",
            action_taken="research queued",
            auto_queued=True,
        )
        assert resp.is_duplicate is False
        assert resp.is_new_event_date is False

    def test_duplicate_event(self):
        """Result for a duplicate event."""
        resp = DeduplicationResultResponse(
            festival_id="550e8400-e29b-41d4-a716-446655440000",
            is_duplicate=True,
            existing_event_id="550e8400-e29b-41d4-a716-446655440001",
            confidence=0.95,
            reason="Exact name and location match",
            action_taken="marked synced",
            auto_queued=False,
        )
        assert resp.existing_event_id is not None


class TestFestivalUpdateResponse:
    """Tests for FestivalUpdateResponse schema."""

    def test_construction(self):
        """Valid response construction."""
        resp = FestivalUpdateResponse(
            festival_id="123",
            message="Updated successfully",
            previous_state="researched_partial",
            new_state="researched",
            updated_fields=["logo_url", "media_items"],
            timestamp="2026-01-01T00:00:00Z",
        )
        assert resp.new_state == "researched"
        assert len(resp.updated_fields) == 2


class TestAgentDecisionLog:
    """Tests for AgentDecisionLog schema."""

    def test_construction(self):
        """Valid decision log."""
        log = AgentDecisionLog(
            agent_type="research",
            step_number=1,
            thought="Need to find dates",
            action="search_web",
            action_input={"query": "festival 2026 dates"},
            observation="Found dates on official site",
            next_step="extract_dates",
            confidence=0.9,
            cost_cents=15,
        )
        assert log.agent_type == "research"
        assert log.cost_cents == 15
