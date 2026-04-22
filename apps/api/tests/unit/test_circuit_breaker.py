"""Tests for circuit breaker state machine."""

import pytest
import asyncio
from unittest.mock import AsyncMock

from src.services.circuit_breaker import (
    CircuitBreaker,
    CircuitState,
    CircuitBreakerOpen,
    circuit_breaker,
)


class TestCircuitBreakerStates:
    """Tests for circuit breaker state transitions."""

    def test_starts_closed(self):
        """Circuit breaker starts in CLOSED state."""
        cb = CircuitBreaker("test_service")
        assert cb.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_opens_after_failures(self):
        """Opens after threshold failures."""
        cb = CircuitBreaker("test_service")
        cb.config.failure_threshold = 3
        
        async def fail_func():
            raise ConnectionError("Failed")
        
        # Trigger 3 failures
        for _ in range(3):
            with pytest.raises(ConnectionError):
                await cb.call(fail_func)
        
        assert cb.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_half_open_after_timeout(self):
        """Transitions to HALF_OPEN after recovery timeout."""
        cb = CircuitBreaker("test_service")
        cb.config.failure_threshold = 1
        cb.config.recovery_timeout = 0.1  # 100ms for testing
        
        async def fail_func():
            raise ConnectionError("Failed")
        
        with pytest.raises(ConnectionError):
            await cb.call(fail_func)
        
        assert cb.state == CircuitState.OPEN
        
        # Wait for timeout
        await asyncio.sleep(0.15)
        
        # Check state updated (via _update_state in call)
        async def success_func():
            return "ok"
        
        # Should be half-open now
        result = await cb.call(success_func)
        assert cb.state in (CircuitState.HALF_OPEN, CircuitState.CLOSED)

    @pytest.mark.asyncio
    async def test_closes_after_successes(self):
        """Closes after enough successes in half-open."""
        cb = CircuitBreaker("test_service")
        cb.config.failure_threshold = 1
        cb.config.recovery_timeout = 0.1
        cb.config.success_threshold = 1
        
        async def fail_func():
            raise ConnectionError("Failed")
        
        with pytest.raises(ConnectionError):
            await cb.call(fail_func)
        
        await asyncio.sleep(0.15)
        
        async def success_func():
            return "ok"
        
        result = await cb.call(success_func)
        assert cb.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_fails_fast_when_open(self):
        """Raises CircuitBreakerOpen when circuit is open."""
        cb = CircuitBreaker("test_service")
        cb.config.failure_threshold = 1
        cb.config.recovery_timeout = 60.0  # Long timeout
        
        async def fail_func():
            raise ConnectionError("Failed")
        
        with pytest.raises(ConnectionError):
            await cb.call(fail_func)
        
        assert cb.state == CircuitState.OPEN
        
        # Next call should fail fast
        async def any_func():
            return "should not reach"
        
        with pytest.raises(CircuitBreakerOpen) as exc_info:
            await cb.call(any_func)
        
        assert "test_service" in str(exc_info.value)
        assert exc_info.value.seconds_until_retry > 0

    @pytest.mark.asyncio
    async def test_half_open_failure_reopens(self):
        """Failure in half-open reopens the circuit."""
        cb = CircuitBreaker("test_service")
        cb.config.failure_threshold = 1
        cb.config.recovery_timeout = 0.1
        
        async def fail_func():
            raise ConnectionError("Failed")
        
        with pytest.raises(ConnectionError):
            await cb.call(fail_func)
        
        await asyncio.sleep(0.15)
        
        # Fail again in half-open
        with pytest.raises(ConnectionError):
            await cb.call(fail_func)
        
        assert cb.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_success_clears_failures(self):
        """Successful calls clear failure count."""
        cb = CircuitBreaker("test_service")
        cb.config.failure_threshold = 5
        
        async def success_func():
            return "ok"
        
        # Multiple successes should keep it closed
        for _ in range(10):
            result = await cb.call(success_func)
            assert result == "ok"
        
        assert cb.state == CircuitState.CLOSED
        assert cb.metrics.total_successes == 10

    def test_reset_manually(self):
        """Manual reset returns to CLOSED."""
        cb = CircuitBreaker("test_service")
        cb._state = CircuitState.OPEN
        
        cb.reset()
        
        assert cb.state == CircuitState.CLOSED
        assert len(cb._failure_times) == 0

    def test_singleton_per_name(self):
        """Same name returns same instance."""
        cb1 = CircuitBreaker("service_a")
        cb2 = CircuitBreaker("service_a")
        cb3 = CircuitBreaker("service_b")
        
        assert cb1 is cb2
        assert cb1 is not cb3


class TestCircuitBreakerDecorator:
    """Tests for @circuit_breaker decorator."""

    @pytest.mark.asyncio
    async def test_decorator_wraps_function(self):
        """Decorator adds circuit breaker protection."""
        
        @circuit_breaker("decorated_test", failure_threshold=2, recovery_timeout=0.1)
        async def my_function():
            return "success"
        
        result = await my_function()
        assert result == "success"
        
        # Check breaker is accessible
        assert hasattr(my_function, '_circuit_breaker')
        assert my_function._circuit_breaker.name == "decorated_test"

    @pytest.mark.asyncio
    async def test_decorator_fails_open(self):
        """Decorator fails fast when open."""
        
        call_count = 0
        
        @circuit_breaker("decorated_fail", failure_threshold=1, recovery_timeout=60.0)
        async def failing_function():
            nonlocal call_count
            call_count += 1
            raise ConnectionError("Failed")
        
        with pytest.raises(ConnectionError):
            await failing_function()
        
        with pytest.raises(CircuitBreakerOpen):
            await failing_function()
        
        # Should not have called the function again
        assert call_count == 1


class TestCircuitBreakerMetrics:
    """Tests for circuit breaker metrics."""

    @pytest.mark.asyncio
    async def test_tracks_total_calls(self):
        """Metrics track total calls."""
        cb = CircuitBreaker("metrics_test")
        
        async def success():
            return "ok"
        
        async def fail():
            raise ValueError("err")
        
        await cb.call(success)
        await cb.call(success)
        
        with pytest.raises(ValueError):
            await cb.call(fail)
        
        metrics = cb.metrics
        assert metrics.total_calls == 3
        assert metrics.total_successes == 2
        assert metrics.total_failures == 1
        assert metrics.state == CircuitState.CLOSED
