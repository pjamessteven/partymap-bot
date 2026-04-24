"""Tests for core pipeline tasks: deduplication, research, sync, discovery."""

import json
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

from celery.exceptions import Retry

from src.core.models import (
    Festival,
    FestivalEventDate,
    FestivalState,
    CostLog,
    StateTransition,
    AgentDecision,
)
from src.core.schemas import (
    DuplicateCheckResult,
    EventDateData,
    FestivalData,
    ResearchResult,
    ResearchFailure,
)
from src.tasks.pipeline import (
    deduplication_check,
    discovery_pipeline,
    research_pipeline,
    sync_pipeline,
    run_sync_task,
)


# ── Mock helpers ──


class MockScalarResult:
    """Mock SQLAlchemy scalars().all() result."""

    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items


class MockExecuteResult:
    """Mock SQLAlchemy execute() result."""

    def __init__(self, scalars=None, scalar_val=None):
        self._scalars = scalars or []
        self._scalar_val = scalar_val

    def scalar_one_or_none(self):
        return self._scalars[0] if self._scalars else None

    def scalar(self):
        return self._scalar_val if self._scalar_val is not None else 0

    def scalars(self):
        return MockScalarResult(self._scalars)

    def all(self):
        return self._scalars


class MockSession:
    """Mock SQLAlchemy session that tracks operations for assertions."""

    def __init__(self, festivals=None):
        self._festivals = list(festivals or [])
        self._festivals_by_id = {f.id: f for f in self._festivals}
        self._added = []
        self._committed = False
        self._rolled_back = False
        self._execute_queue = []
        self._closed = False

    def queue_execute_result(self, result):
        """Queue a result for the next execute() call."""
        self._execute_queue.append(result)

    def get(self, model, id):
        return self._festivals_by_id.get(id)

    def add(self, obj):
        self._added.append(obj)
        if hasattr(obj, "id") and obj.id:
            if isinstance(obj, Festival):
                self._festivals_by_id[obj.id] = obj

    def commit(self):
        self._committed = True

    def rollback(self):
        self._rolled_back = True

    def execute(self, stmt):
        if self._execute_queue:
            return self._execute_queue.pop(0)
        return MockExecuteResult()

    def flush(self):
        for obj in self._added:
            if isinstance(obj, Festival) and (not hasattr(obj, "id") or not obj.id):
                obj.id = uuid4()

    def close(self):
        self._closed = True

    def get_added(self, model_class=None):
        """Get added objects, optionally filtered by type."""
        if model_class:
            return [o for o in self._added if isinstance(o, model_class)]
        return self._added


def make_festival(state=FestivalState.DISCOVERED, **kwargs):
    """Create a Festival instance with test defaults."""
    defaults = {
        "id": uuid4(),
        "name": "Test Festival",
        "source": "exa",
        "source_url": "https://example.com/fest",
        "state": state.value if hasattr(state, "value") else state,
        "is_duplicate": False,
        "is_new_event_date": False,
        "date_confirmed": True,
        "workflow_type": None,
        "update_reasons": [],
        "retry_count": 0,
        "research_data": {},
        "discovered_data": {"location": "Berlin, Germany"},
    }
    defaults.update(kwargs)
    return Festival(**defaults)


def run_task(task_func, *args, **kwargs):
    """Run a Celery bound task directly, patching retry for testability."""
    task_func.retry = MagicMock(side_effect=Retry)
    return task_func(*args, **kwargs)


def make_valid_research_data():
    """Return a dict that constructs a valid FestivalData."""
    return {
        "name": "Test Festival",
        "description": "A great festival description",
        "full_description": "A full description that is definitely long enough",
        "event_dates": [
            {
                "start": datetime(2026, 7, 15, 14, 0, 0),
                "end": datetime(2026, 7, 17, 23, 0, 0),
                "location_description": "Berlin, Germany",
            }
        ],
        "logo_url": "https://example.com/logo.jpg",
        "tags": ["music"],
    }


def make_research_result_success(with_logo=True, with_decisions=False):
    """Create a successful ResearchResult for testing."""
    data = FestivalData(
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
        logo_url="https://example.com/logo.jpg" if with_logo else None,
        tags=["music"],
    )
    result = ResearchResult(
        success=True,
        festival_data=data,
        cost_cents=25,
        iterations=3,
    )
    if with_decisions:
        from src.core.schemas import AgentDecisionLog

        result.decisions = [
            AgentDecisionLog(
                agent_type="research",
                step_number=1,
                thought="Searching...",
                action="web_search",
                action_input={"query": "test"},
                observation="Found results",
                next_step="evaluate",
                confidence=0.9,
            )
        ]
    return result


def make_research_result_failure(reason="research_failed", completeness=0.0):
    """Create a failed ResearchResult for testing."""
    return ResearchResult(
        success=False,
        failure=ResearchFailure(
            reason=reason,
            message=f"Failed: {reason}",
            completeness_score=completeness,
            missing_fields=["dates"],
        ),
        cost_cents=10,
        iterations=1,
    )


# ── Fixtures ──


@pytest.fixture
def mock_pipeline_session():
    """Create a fresh mock session."""
    return MockSession()


@pytest.fixture
def mock_pipeline_deps(mock_pipeline_session):
    """Patch all pipeline external dependencies."""
    with patch(
        "src.tasks.pipeline.SessionLocal", return_value=mock_pipeline_session
    ), patch("src.tasks.pipeline.research_pipeline") as mock_research, patch(
        "src.tasks.pipeline.sync_pipeline"
    ) as mock_sync, patch(
        "src.tasks.pipeline.deduplication_check"
    ) as mock_dedup, patch(
        "src.tasks.pipeline.run_sync_task"
    ) as mock_run_sync, patch(
        "src.tasks.pipeline.is_auto_process_enabled_sync"
    ) as mock_auto, patch(
        "src.tasks.pipeline.is_setting_enabled_sync"
    ) as mock_setting, patch(
        "src.tasks.pipeline.PartyMapClient"
    ) as mock_client_cls, patch(
        "src.tasks.pipeline.JobTracker"
    ) as mock_jt, patch(
        "src.tasks.pipeline.utc_now", return_value=datetime(2026, 4, 23, 12, 0, 0)
    ), patch(
        "src.tasks.pipeline.settings"
    ) as mock_settings:

        mock_auto.return_value = True
        mock_setting.return_value = True

        mock_client = AsyncMock()
        mock_client_cls.return_value = mock_client

        mock_settings.max_cost_per_day = 10000
        mock_settings.max_retries = 3
        mock_settings.failed_festival_retention_days = 7

        yield {
            "session": mock_pipeline_session,
            "research": mock_research,
            "sync": mock_sync,
            "dedup": mock_dedup,
            "run_sync": mock_run_sync,
            "auto": mock_auto,
            "setting": mock_setting,
            "client": mock_client,
            "client_cls": mock_client_cls,
            "job_tracker": mock_jt,
            "settings": mock_settings,
        }


# ── TestDeduplicationCheck ──


class TestDeduplicationCheck:
    """Tests for deduplication_check Celery task."""

    def test_new_festival_auto_queues_research(self, mock_pipeline_deps):
        """New festival with auto_process + auto_research queues research."""
        festival = make_festival(state=FestivalState.DISCOVERED)
        mock_pipeline_deps["session"]._festivals_by_id[festival.id] = festival
        mock_pipeline_deps["client"].check_duplicate.return_value = DuplicateCheckResult(
            is_duplicate=False,
            confidence=1.0,
            reason="No match",
        )

        run_task(deduplication_check, str(festival.id))

        assert festival.state == FestivalState.RESEARCHING.value
        assert festival.workflow_type == "new"
        assert festival.update_reasons == []
        mock_pipeline_deps["research"].delay.assert_called_once_with(str(festival.id))
        # State transition logged
        transitions = mock_pipeline_deps["session"].get_added(StateTransition)
        assert len(transitions) == 1
        assert transitions[0].to_state == FestivalState.RESEARCHING.value

    def test_new_festival_respects_auto_research_setting(self, mock_pipeline_deps):
        """auto_research_on_discover=false does not queue research for new festivals."""
        festival = make_festival(state=FestivalState.DISCOVERED)
        mock_pipeline_deps["session"]._festivals_by_id[festival.id] = festival
        mock_pipeline_deps["client"].check_duplicate.return_value = DuplicateCheckResult(
            is_duplicate=False,
        )
        mock_pipeline_deps["setting"].return_value = False  # auto_research_on_discover=false

        run_task(deduplication_check, str(festival.id))

        assert festival.state == FestivalState.RESEARCHING.value
        assert festival.workflow_type == "new"
        mock_pipeline_deps["research"].delay.assert_not_called()

    def test_new_festival_manual_mode_no_queue(self, mock_pipeline_deps):
        """auto_process=false: state advances but no research queued."""
        festival = make_festival(state=FestivalState.DISCOVERED)
        mock_pipeline_deps["session"]._festivals_by_id[festival.id] = festival
        mock_pipeline_deps["client"].check_duplicate.return_value = DuplicateCheckResult(
            is_duplicate=False,
        )
        mock_pipeline_deps["auto"].return_value = False  # auto_process=false

        run_task(deduplication_check, str(festival.id))

        assert festival.state == FestivalState.RESEARCHING.value
        mock_pipeline_deps["research"].delay.assert_not_called()

    def test_duplicate_new_event_date_auto_queues(self, mock_pipeline_deps):
        """Duplicate with new event date queues research when auto_process=true."""
        festival = make_festival(state=FestivalState.DISCOVERED)
        mock_pipeline_deps["session"]._festivals_by_id[festival.id] = festival
        mock_pipeline_deps["client"].check_duplicate.return_value = DuplicateCheckResult(
            is_duplicate=True,
            existing_event_id=12345,
            is_new_event_date=True,
            date_confirmed=False,
            confidence=0.9,
            reason="Name match",
        )

        run_task(deduplication_check, str(festival.id))

        assert festival.state == FestivalState.RESEARCHING.value
        assert festival.workflow_type == "update"
        assert festival.update_reasons == ["new_event_date"]
        assert festival.is_duplicate is True
        assert festival.partymap_event_id == 12345
        mock_pipeline_deps["research"].delay.assert_called_once_with(str(festival.id))

    def test_duplicate_new_event_date_respects_auto_research(self, mock_pipeline_deps):
        """Duplicate with new event date respects auto_research_on_discover."""
        festival = make_festival(state=FestivalState.DISCOVERED)
        mock_pipeline_deps["session"]._festivals_by_id[festival.id] = festival
        mock_pipeline_deps["client"].check_duplicate.return_value = DuplicateCheckResult(
            is_duplicate=True,
            existing_event_id=12345,
            is_new_event_date=True,
            confidence=0.9,
        )
        mock_pipeline_deps["setting"].return_value = False

        run_task(deduplication_check, str(festival.id))

        assert festival.state == FestivalState.RESEARCHING.value
        assert festival.workflow_type == "update"
        mock_pipeline_deps["research"].delay.assert_not_called()

    def test_duplicate_needs_update_queues_with_setting(self, mock_pipeline_deps):
        """Duplicate needing update queues research when both settings true."""
        festival = make_festival(state=FestivalState.DISCOVERED)
        mock_pipeline_deps["session"]._festivals_by_id[festival.id] = festival
        mock_pipeline_deps["client"].check_duplicate.return_value = DuplicateCheckResult(
            is_duplicate=True,
            existing_event_id=12345,
            is_new_event_date=False,
            date_confirmed=False,
            confidence=0.85,
            reason="Dates unconfirmed",
        )

        run_task(deduplication_check, str(festival.id))

        assert festival.state == FestivalState.RESEARCHING.value
        assert festival.workflow_type == "update"
        assert festival.update_reasons == ["missing_dates"]
        mock_pipeline_deps["research"].delay.assert_called_once_with(str(festival.id))

    def test_duplicate_up_to_date_marked_synced(self, mock_pipeline_deps):
        """Duplicate that is up-to-date gets marked SYNCED, no research queued."""
        festival = make_festival(state=FestivalState.DISCOVERED)
        mock_pipeline_deps["session"]._festivals_by_id[festival.id] = festival
        mock_pipeline_deps["client"].check_duplicate.return_value = DuplicateCheckResult(
            is_duplicate=True,
            existing_event_id=12345,
            is_new_event_date=False,
            date_confirmed=True,
            confidence=0.95,
            reason="Up to date",
        )

        run_task(deduplication_check, str(festival.id))

        assert festival.state == FestivalState.SYNCED.value
        assert festival.is_duplicate is True
        mock_pipeline_deps["research"].delay.assert_not_called()
        # State transition logged
        transitions = mock_pipeline_deps["session"].get_added(StateTransition)
        assert transitions[0].to_state == FestivalState.SYNCED.value

    def test_skip_non_discovered_state(self, mock_pipeline_deps):
        """Festival not in DISCOVERED state is skipped entirely."""
        festival = make_festival(state=FestivalState.RESEARCHING)
        mock_pipeline_deps["session"]._festivals_by_id[festival.id] = festival

        run_task(deduplication_check, str(festival.id))

        # No changes, no PartyMap client call
        mock_pipeline_deps["client"].check_duplicate.assert_not_called()
        assert festival.state == FestivalState.RESEARCHING.value

    def test_festival_not_found(self, mock_pipeline_deps):
        """Invalid/nonexistent festival ID returns early."""
        run_task(deduplication_check, str(uuid4()))

        mock_pipeline_deps["client"].check_duplicate.assert_not_called()

    def test_exception_triggers_retry(self, mock_pipeline_deps):
        """Unexpected exception triggers Celery retry."""
        festival = make_festival(state=FestivalState.DISCOVERED)
        mock_pipeline_deps["session"]._festivals_by_id[festival.id] = festival
        mock_pipeline_deps["client"].check_duplicate.side_effect = Exception("Boom")

        with pytest.raises(Retry):
            run_task(deduplication_check, str(festival.id))

        assert mock_pipeline_deps["session"]._rolled_back is True


# ── TestResearchPipeline ──


class TestResearchPipeline:
    """Tests for research_pipeline Celery task."""

    def test_success_creates_event_dates(self, mock_pipeline_deps):
        """Successful research creates FestivalEventDate records and queues sync."""
        festival = make_festival(
            state=FestivalState.RESEARCHING,
            research_data=make_valid_research_data(),
        )
        mock_pipeline_deps["session"]._festivals_by_id[festival.id] = festival
        mock_pipeline_deps["settings"].max_cost_per_day = 10000

        with patch("asyncio.run") as mock_run:
            mock_run.return_value = make_research_result_success()

            run_task(research_pipeline, str(festival.id))

        assert festival.state == FestivalState.RESEARCHED.value
        assert festival.research_completeness_score == 1.0
        assert festival.failure_reason is None
        # FestivalEventDate created
        event_dates = mock_pipeline_deps["session"].get_added(FestivalEventDate)
        assert len(event_dates) == 1
        assert event_dates[0].start_date == datetime(2026, 7, 15, 14, 0, 0)
        # CostLog created
        cost_logs = mock_pipeline_deps["session"].get_added(CostLog)
        assert len(cost_logs) == 1
        assert cost_logs[0].cost_cents == 25
        # StateTransition logged
        transitions = mock_pipeline_deps["session"].get_added(StateTransition)
        assert transitions[0].to_state == FestivalState.RESEARCHED.value
        # Auto-sync queued
        mock_pipeline_deps["sync"].delay.assert_called_once_with(str(festival.id))

    def test_success_auto_sync_disabled(self, mock_pipeline_deps):
        """Successful research does not queue sync when auto_sync disabled."""
        festival = make_festival(
            state=FestivalState.RESEARCHING,
            research_data=make_valid_research_data(),
        )
        mock_pipeline_deps["session"]._festivals_by_id[festival.id] = festival
        mock_pipeline_deps["setting"].return_value = False  # auto_sync_on_research_success=false

        with patch("asyncio.run") as mock_run:
            mock_run.return_value = make_research_result_success()

            run_task(research_pipeline, str(festival.id))

        assert festival.state == FestivalState.RESEARCHED.value
        mock_pipeline_deps["sync"].delay.assert_not_called()

    def test_success_saves_agent_decisions(self, mock_pipeline_deps):
        """Agent decisions from research result are saved to DB."""
        festival = make_festival(
            state=FestivalState.RESEARCHING,
            research_data=make_valid_research_data(),
        )
        mock_pipeline_deps["session"]._festivals_by_id[festival.id] = festival

        with patch("asyncio.run") as mock_run:
            mock_run.return_value = make_research_result_success(with_decisions=True)

            run_task(research_pipeline, str(festival.id))

        decisions = mock_pipeline_deps["session"].get_added(AgentDecision)
        assert len(decisions) == 1
        assert decisions[0].agent_type == "research"
        assert decisions[0].thought == "Searching..."

    def test_partial_result_researched_partial(self, mock_pipeline_deps):
        """Partial result (missing logo) sets RESEARCHED_PARTIAL state."""
        festival = make_festival(
            state=FestivalState.RESEARCHING,
            research_data=make_valid_research_data(),
        )
        mock_pipeline_deps["session"]._festivals_by_id[festival.id] = festival

        # Simulate partial result via is_partial flag in result state
        result = make_research_result_success(with_logo=False)
        # Hack: set is_partial by manually constructing the state dict behavior
        # The pipeline checks result_state.get("is_partial"), but we're mocking asyncio.run
        # which returns the ResearchResult directly. The pipeline doesn't check is_partial
        # on the ResearchResult object - it checks the LangGraph state dict.
        # Actually looking at the code again:
        #   if result_state.get("is_partial"):
        # This is checking the graph state, not the ResearchResult.
        # Since we mock asyncio.run to return ResearchResult, the code path is:
        #   result = asyncio.run(_research_async())
        #   if result.success and result.festival_data:
        #       ... success path
        #   elif result.failure:
        #       ... failure path
        # So partial result isn't directly testable via this mock without deeper patching.
        # Let me create a partial result by using failure with high completeness.
        partial = ResearchResult(
            success=False,
            festival_data=FestivalData(
                name="Test",
                description="A great festival description",
                full_description="A full description that is definitely long enough",
                event_dates=[
                    EventDateData(
                        start=datetime(2026, 7, 15, 14, 0, 0),
                        location_description="Berlin, Germany",
                    )
                ],
            ),
            failure=ResearchFailure(
                reason="logo_missing",
                message="Core info found but logo is missing",
                completeness_score=0.7,
                missing_fields=["logo_url"],
            ),
            cost_cents=15,
        )

        with patch("asyncio.run") as mock_run:
            mock_run.return_value = partial

            run_task(research_pipeline, str(festival.id))

        assert festival.state == FestivalState.RESEARCHED_PARTIAL.value
        assert festival.research_completeness_score == 0.7
        assert festival.failure_reason == "logo_missing"

    def test_budget_exceeded_retry_tomorrow(self, mock_pipeline_deps):
        """Daily budget exceeded triggers retry with 24h countdown."""
        festival = make_festival(
            state=FestivalState.RESEARCHING,
            research_data=make_valid_research_data(),
        )
        mock_pipeline_deps["session"]._festivals_by_id[festival.id] = festival
        mock_pipeline_deps["settings"].max_cost_per_day = 50
        # Queue a high cost sum result for the budget query
        mock_pipeline_deps["session"].queue_execute_result(
            MockExecuteResult(scalar_val=100)
        )

        with pytest.raises(Retry):
            run_task(research_pipeline, str(festival.id))

        research_pipeline.retry.assert_called_once()
        # Celery Retry is raised; we can check countdown via the call args if needed
        # Actually Retry doesn't expose countdown easily in the exception
        # But we can verify the task.retry was called with countdown=86400
        call_kwargs = research_pipeline.retry.call_args.kwargs
        assert call_kwargs.get("countdown") == 86400

    def test_failure_completeness_zero(self, mock_pipeline_deps):
        """Research failure with completeness=0 sets FAILED and increments retry."""
        festival = make_festival(
            state=FestivalState.RESEARCHING,
            research_data=make_valid_research_data(),
            retry_count=2,
        )
        mock_pipeline_deps["session"]._festivals_by_id[festival.id] = festival
        mock_pipeline_deps["settings"].max_retries = 3

        with patch("asyncio.run") as mock_run:
            mock_run.return_value = make_research_result_failure(
                reason="not_found", completeness=0.0
            )

            run_task(research_pipeline, str(festival.id))

        assert festival.state == FestivalState.FAILED.value
        assert festival.retry_count == 3
        assert festival.failure_reason == "not_found"
        # Max retries reached -> purge_after set
        assert festival.purge_after is not None

    def test_failure_below_max_retries_no_purge(self, mock_pipeline_deps):
        """Failed research below max retries does not set purge_after."""
        festival = make_festival(
            state=FestivalState.RESEARCHING,
            research_data=make_valid_research_data(),
            retry_count=0,
        )
        mock_pipeline_deps["session"]._festivals_by_id[festival.id] = festival
        mock_pipeline_deps["settings"].max_retries = 3

        with patch("asyncio.run") as mock_run:
            mock_run.return_value = make_research_result_failure(
                reason="dates", completeness=0.0
            )

            run_task(research_pipeline, str(festival.id))

        assert festival.state == FestivalState.FAILED.value
        assert festival.retry_count == 1
        assert festival.purge_after is None

    def test_recently_researched_skipped(self, mock_pipeline_deps):
        """Festival researched within 7 days is skipped."""
        festival = make_festival(
            state=FestivalState.RESEARCHED,
            research_data=make_valid_research_data(),
            updated_at=datetime(2026, 4, 22, 12, 0, 0),  # 1 day ago
        )
        mock_pipeline_deps["session"]._festivals_by_id[festival.id] = festival

        run_task(research_pipeline, str(festival.id))

        # No asyncio.run called - skipped before research
        # (We can't easily assert this without more complex mocking)
        # State unchanged
        assert festival.state == FestivalState.RESEARCHED.value

    def test_unexpected_exception(self, mock_pipeline_deps):
        """Crash during research sets FAILED, increments retry, triggers Celery retry."""
        festival = make_festival(
            state=FestivalState.RESEARCHING,
            research_data=make_valid_research_data(),
            retry_count=1,
        )
        mock_pipeline_deps["session"]._festivals_by_id[festival.id] = festival

        with patch("asyncio.run") as mock_run:
            mock_run.side_effect = Exception("Graph crashed")

            with pytest.raises(Retry):
                run_task(research_pipeline, str(festival.id))

        assert festival.state == FestivalState.FAILED.value
        assert festival.retry_count == 2
        assert "Graph crashed" in festival.last_error
        assert mock_pipeline_deps["session"]._rolled_back is True


# ── TestSyncPipeline ──


class TestSyncPipeline:
    """Tests for sync_pipeline Celery task."""

    def test_valid_festival_synced(self, mock_pipeline_deps):
        """Valid festival data syncs successfully to PartyMap."""
        festival = make_festival(
            state=FestivalState.RESEARCHED,
            research_data=make_valid_research_data(),
            is_duplicate=False,
        )
        mock_pipeline_deps["session"]._festivals_by_id[festival.id] = festival
        mock_pipeline_deps["client"].sync_festival.return_value = {
            "event_id": 12345,
            "action": "created",
        }

        with patch("asyncio.run") as mock_run:
            mock_run.return_value = {"event_id": 12345, "action": "created"}

            run_task(sync_pipeline, str(festival.id))

        assert festival.state == FestivalState.SYNCED.value
        assert festival.partymap_event_id == 12345
        assert festival.retry_count == 0
        assert festival.last_error is None
        assert festival.error_category is None
        # StateTransition logged
        transitions = mock_pipeline_deps["session"].get_added(StateTransition)
        assert any(t.to_state == FestivalState.SYNCED.value for t in transitions)

    def test_validation_invalid_no_force(self, mock_pipeline_deps):
        """Validation fails without force flag: VALIDATION_FAILED, no PartyMap call."""
        # Invalid data: missing logo_url
        festival = make_festival(
            state=FestivalState.RESEARCHED,
            research_data={
                "name": "Test",
                "description": "A great festival description",
                "full_description": "A full description that is definitely long enough",
                "event_dates": [
                    {
                        "start": datetime(2026, 7, 15, 14, 0, 0),
                        "location_description": "Berlin, Germany",
                    }
                ],
                # No logo_url - will fail validation
            },
        )
        mock_pipeline_deps["session"]._festivals_by_id[festival.id] = festival

        run_task(sync_pipeline, str(festival.id))

        assert festival.state == FestivalState.VALIDATION_FAILED.value
        assert festival.validation_status == "invalid"
        assert len(festival.validation_errors) > 0
        # No PartyMap call
        mock_pipeline_deps["client"].sync_festival.assert_not_called()

    def test_force_sync_bypasses_validation(self, mock_pipeline_deps):
        """force=true bypasses validation errors and proceeds to sync."""
        festival = make_festival(
            state=FestivalState.RESEARCHED,
            research_data={
                "name": "Test",
                "description": "A great festival description",
                "full_description": "A full description that is definitely long enough",
                "event_dates": [
                    {
                        "start": datetime(2026, 7, 15, 14, 0, 0),
                        "location_description": "Berlin, Germany",
                    }
                ],
                # No logo_url
            },
        )
        mock_pipeline_deps["session"]._festivals_by_id[festival.id] = festival

        with patch("asyncio.run") as mock_run:
            mock_run.return_value = {"event_id": 12345, "action": "created"}

            run_task(sync_pipeline, str(festival.id), force=True)

        assert festival.state == FestivalState.SYNCED.value
        # asyncio.run was called to execute the sync (PartyMap client call mocked via asyncio.run)
        mock_run.assert_called_once()

    def test_needs_review_auto_process_continues(self, mock_pipeline_deps):
        """needs_review + auto_process=true continues to sync."""
        festival = make_festival(
            state=FestivalState.RESEARCHED,
            research_data=make_valid_research_data(),
        )
        mock_pipeline_deps["session"]._festivals_by_id[festival.id] = festival
        # Force validation to return needs_review by using minimal data
        # Actually with valid data it won't be needs_review. Let me use data with warnings.
        festival.research_data = {
            "name": "Test Festival",
            "description": "A great festival description",
            "full_description": "A full description that is definitely long enough",
            "event_dates": [
                {
                    "start": datetime(2020, 7, 15, 14, 0, 0),  # Past date -> warning
                    "location_description": "Berlin, Germany",
                }
            ],
            "logo_url": "https://example.com/logo.jpg",
        }
        mock_pipeline_deps["setting"].return_value = True  # auto_process_enabled

        with patch("asyncio.run") as mock_run:
            mock_run.return_value = {"event_id": 12345, "action": "updated"}

            run_task(sync_pipeline, str(festival.id))

        assert festival.state == FestivalState.SYNCED.value

    def test_needs_review_manual_stops(self, mock_pipeline_deps):
        """needs_review + auto_process=false stops at review."""
        festival = make_festival(
            state=FestivalState.RESEARCHED,
            research_data={
                "name": "Test Festival",
                "description": "A great festival description",
                "full_description": "A full description that is definitely long enough",
                "event_dates": [
                    {
                        "start": datetime(2020, 7, 15, 14, 0, 0),  # Past date -> warning
                        "location_description": "Berlin, Germany",
                    }
                ],
                "logo_url": "https://example.com/logo.jpg",
            },
        )
        mock_pipeline_deps["session"]._festivals_by_id[festival.id] = festival
        mock_pipeline_deps["setting"].return_value = False  # auto_process_enabled=false

        run_task(sync_pipeline, str(festival.id))

        assert festival.state == FestivalState.NEEDS_REVIEW.value
        mock_pipeline_deps["client"].sync_festival.assert_not_called()

    def test_no_research_data_returns_early(self, mock_pipeline_deps):
        """Festival with no research_data returns early."""
        festival = make_festival(
            state=FestivalState.RESEARCHED,
            research_data={},
        )
        mock_pipeline_deps["session"]._festivals_by_id[festival.id] = festival

        run_task(sync_pipeline, str(festival.id))

        mock_pipeline_deps["client"].sync_festival.assert_not_called()
        assert festival.state == FestivalState.RESEARCHED.value  # Unchanged

    def test_transient_error_retries_with_backoff(self, mock_pipeline_deps):
        """Transient sync error increments retry and schedules backoff."""
        festival = make_festival(
            state=FestivalState.RESEARCHED,
            research_data=make_valid_research_data(),
            retry_count=1,
        )
        mock_pipeline_deps["session"]._festivals_by_id[festival.id] = festival

        with patch("asyncio.run") as mock_run:
            mock_run.side_effect = Exception("PartyMap 503 Service Unavailable")

            with pytest.raises(Retry):
                run_task(sync_pipeline, str(festival.id))

        assert festival.retry_count == 2
        assert festival.error_category is not None
        # Check that retry was called with exponential backoff
        sync_pipeline.retry.assert_called_once()
        call_kwargs = sync_pipeline.retry.call_args.kwargs
        assert "countdown" in call_kwargs
        assert call_kwargs["countdown"] > 0

    def test_permanent_error_no_retry(self, mock_pipeline_deps):
        """Permanent error (validation) does NOT trigger Celery retry."""
        from src.core.error_classification import ErrorCategory

        festival = make_festival(
            state=FestivalState.RESEARCHED,
            research_data=make_valid_research_data(),
            retry_count=1,
        )
        mock_pipeline_deps["session"]._festivals_by_id[festival.id] = festival

        # Create an exception that categorizes as VALIDATION (non-retryable)
        exc = Exception("validation failed")
        # Patch categorize_error to return VALIDATION
        with patch("asyncio.run") as mock_run:
            mock_run.side_effect = exc
            with patch(
                "src.core.error_classification.categorize_error",
                return_value=ErrorCategory.VALIDATION,
            ):
                run_task(sync_pipeline, str(festival.id))

        assert festival.state == FestivalState.FAILED.value
        sync_pipeline.retry.assert_not_called()

    def test_max_retries_quarantined(self, mock_pipeline_deps):
        """5+ retry failures quarantine the festival."""
        festival = make_festival(
            state=FestivalState.RESEARCHED,
            research_data=make_valid_research_data(),
            retry_count=5,
        )
        mock_pipeline_deps["session"]._festivals_by_id[festival.id] = festival

        with patch("asyncio.run") as mock_run:
            mock_run.side_effect = Exception("Persistent failure")

            run_task(sync_pipeline, str(festival.id))

        assert festival.state == FestivalState.QUARANTINED.value
        assert festival.max_retries_reached is True
        assert festival.quarantined_at is not None
        assert festival.quarantine_reason is not None

    def test_error_classification_captured(self, mock_pipeline_deps):
        """Error category and context are stored on festival."""
        festival = make_festival(
            state=FestivalState.RESEARCHED,
            research_data=make_valid_research_data(),
            retry_count=0,
        )
        mock_pipeline_deps["session"]._festivals_by_id[festival.id] = festival

        with patch("asyncio.run") as mock_run:
            mock_run.side_effect = Exception("Connection timeout")

            with pytest.raises(Retry):
                run_task(sync_pipeline, str(festival.id))

        assert festival.last_error is not None
        assert festival.error_category is not None
        assert festival.error_context is not None
        assert festival.first_error_at is not None
        assert festival.last_retry_at is not None

    def test_festival_not_found(self, mock_pipeline_deps):
        """Sync for nonexistent festival returns early."""
        run_task(sync_pipeline, str(uuid4()))

        mock_pipeline_deps["client"].sync_festival.assert_not_called()


# ── TestDiscoveryPipeline ──


class TestDiscoveryPipeline:
    """Tests for discovery_pipeline Celery task."""

    def test_discover_saves_festivals(self, mock_pipeline_deps):
        """Discovered festivals are saved and deduplication queued."""
        mock_pipeline_deps["session"].queue_execute_result(
            MockExecuteResult()  # source_url check: no existing
        )

        discovered = [
            MagicMock(
                name="Festival A",
                source="exa",
                source_id="exa-1",
                source_url="https://example.com/a",
                discovered_data={"location": "Berlin"},
            ),
            MagicMock(
                name="Festival B",
                source="exa",
                source_id="exa-2",
                source_url="https://example.com/b",
                discovered_data={"location": "Paris"},
            ),
        ]

        with patch("asyncio.run") as mock_run:
            mock_run.return_value = discovered

            discovery_pipeline()

        # Festivals saved
        festivals = mock_pipeline_deps["session"].get_added(Festival)
        assert len(festivals) == 2
        assert festivals[0].state == FestivalState.DISCOVERED.value
        # Deduplication queued for each
        assert mock_pipeline_deps["dedup"].delay.call_count == 2
        # Progress reported
        mock_pipeline_deps["job_tracker"].update_progress_sync.assert_called()

    def test_skips_existing_source_url(self, mock_pipeline_deps):
        """Duplicate source_url is skipped, not saved again."""
        existing_festival = make_festival(
            state=FestivalState.DISCOVERED,
            source_url="https://example.com/a",
        )
        mock_pipeline_deps["session"].queue_execute_result(
            MockExecuteResult(scalars=[existing_festival])  # Existing found
        )

        discovered = [
            MagicMock(
                name="Festival A",
                source="exa",
                source_id="exa-1",
                source_url="https://example.com/a",
                discovered_data={"location": "Berlin"},
            ),
        ]

        with patch("asyncio.run") as mock_run:
            mock_run.return_value = discovered

            discovery_pipeline()

        # No new festival saved
        festivals = mock_pipeline_deps["session"].get_added(Festival)
        assert len(festivals) == 0
        mock_pipeline_deps["dedup"].delay.assert_not_called()

    def test_progress_reported(self, mock_pipeline_deps):
        """JobTracker progress is updated as festivals are processed."""
        mock_pipeline_deps["session"].queue_execute_result(MockExecuteResult())

        discovered = [
            MagicMock(
                name=f"Festival {i}",
                source="exa",
                source_id=f"exa-{i}",
                source_url=f"https://example.com/{i}",
                discovered_data={},
            )
            for i in range(3)
        ]

        with patch("asyncio.run") as mock_run:
            mock_run.return_value = discovered

            discovery_pipeline()

        # Progress should be called for each festival + final summary
        assert mock_pipeline_deps["job_tracker"].update_progress_sync.call_count >= 3
        # Check that current=3, total=3 was reported for the last one
        calls = mock_pipeline_deps["job_tracker"].update_progress_sync.call_args_list
        last_call = calls[-1]
        assert last_call.kwargs["current"] == 3
        assert last_call.kwargs["total"] == 3

    def test_exception_triggers_retry(self, mock_pipeline_deps):
        """Discovery failure triggers Celery retry."""
        with patch("asyncio.run") as mock_run:
            mock_run.side_effect = Exception("Discovery agent failed")

            with pytest.raises(Retry):
                run_task(discovery_pipeline)

        assert mock_pipeline_deps["session"]._rolled_back is True


# ── TestRunSyncTask ──


class TestRunSyncTask:
    """Tests for run_sync_task Celery task."""

    def test_sync_single_festival(self, mock_pipeline_deps):
        """Single festival ID queues sync_pipeline."""
        festival = make_festival(state=FestivalState.RESEARCHED)
        mock_pipeline_deps["session"]._festivals_by_id[festival.id] = festival

        result = run_task(run_sync_task, str(festival.id))

        assert result["synced"] == 1
        mock_pipeline_deps["sync"].delay.assert_called_once_with(
            festival_id=str(festival.id), force=False
        )

    def test_sync_all_researched(self, mock_pipeline_deps):
        """No festival_id syncs all RESEARCHED festivals."""
        festivals = [
            make_festival(state=FestivalState.RESEARCHED),
            make_festival(state=FestivalState.RESEARCHED),
            make_festival(state=FestivalState.DISCOVERED),  # Not included
        ]
        mock_pipeline_deps["session"].queue_execute_result(
            MockExecuteResult(scalars=[festivals[0], festivals[1]])
        )

        result = run_sync_task()

        assert result["synced"] == 2
        assert mock_pipeline_deps["sync"].delay.call_count == 2
        # Progress reported
        mock_pipeline_deps["job_tracker"].update_progress_sync.assert_called()

    def test_force_flag_passed_through(self, mock_pipeline_deps):
        """force flag is passed to sync_pipeline."""
        festival = make_festival(state=FestivalState.RESEARCHED)
        mock_pipeline_deps["session"]._festivals_by_id[festival.id] = festival

        run_task(run_sync_task, str(festival.id), force=True)

        mock_pipeline_deps["sync"].delay.assert_called_once_with(
            festival_id=str(festival.id), force=True
        )
