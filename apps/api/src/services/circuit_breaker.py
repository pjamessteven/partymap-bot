"""Circuit breaker pattern for external service resilience.

Provides circuit breakers for:
- PartyMap API
- Exa API
- LLM/OpenRouter API

Circuit breaker states:
- CLOSED: Normal operation, requests pass through
- OPEN: Service failing, requests fail fast
- HALF_OPEN: Testing if service recovered

Configuration:
- failure_threshold: Number of failures before opening (default: 5)
- recovery_timeout: Seconds to wait before half-open (default: 30)
- half_open_max_calls: Max calls in half-open state (default: 3)
"""

import asyncio
import binascii
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing fast
    HALF_OPEN = "half_open"  # Testing recovery


class CircuitBreakerOpen(Exception):
    """Raised when circuit breaker is open."""

    def __init__(self, service: str, seconds_until_retry: float):
        self.service = service
        self.seconds_until_retry = seconds_until_retry
        super().__init__(f"Circuit breaker open for {service}. Retry in {seconds_until_retry:.1f}s")


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""

    # Thresholds
    failure_threshold: int = 5           # Failures before opening
    recovery_timeout: float = 30.0       # Seconds before half-open
    half_open_max_calls: int = 3         # Calls to allow in half-open state

    # Timing
    failure_window: float = 60.0         # Window for counting failures (seconds)
    success_threshold: int = 2           # Successes needed to close from half-open

    # Exceptions that count as failures (service-level failures)
    expected_exceptions: tuple = field(default_factory=lambda: (Exception,))

    # Exceptions to ignore for circuit breaker (don't count as failures)
    # These are typically data/parsing errors, not service failures
    ignored_exceptions: tuple = field(
        default_factory=lambda: (
            ValueError,          # JSON parsing, validation errors
            TypeError,           # Type mismatches
            KeyError,            # Missing keys in data structures
            AttributeError,      # Missing attributes
            IndexError,          # Index out of range
            UnicodeDecodeError,  # Encoding issues
            binascii.Error,  # Base64 decoding errors
        )
    )


@dataclass
class CircuitBreakerMetrics:
    """Metrics for circuit breaker monitoring."""

    state: CircuitState
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: Optional[float] = None
    last_success_time: Optional[float] = None
    opened_at: Optional[float] = None
    closed_at: Optional[float] = None
    total_calls: int = 0
    total_failures: int = 0
    total_successes: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "last_failure_time": self.last_failure_time,
            "last_success_time": self.last_success_time,
            "opened_at": self.opened_at,
            "closed_at": self.closed_at,
            "total_calls": self.total_calls,
            "total_failures": self.total_failures,
            "total_successes": self.total_successes,
        }


class CircuitBreaker:
    """Circuit breaker for external service calls."""

    _instances: Dict[str, "CircuitBreaker"] = {}

    def __new__(cls, name: str, config: Optional[CircuitBreakerConfig] = None):
        """Singleton pattern - one circuit breaker per service name."""
        if name not in cls._instances:
            instance = super().__new__(cls)
            cls._instances[name] = instance
        return cls._instances[name]

    def __init__(self, name: str, config: Optional[CircuitBreakerConfig] = None):
        # Only initialize once (singleton pattern)
        if hasattr(self, '_initialized'):
            return

        self.name = name
        self.config = config or CircuitBreakerConfig()
        self._state = CircuitState.CLOSED
        self._failure_times: list = []  # Timestamps of failures
        self._half_open_calls = 0
        self._half_open_successes = 0
        self._lock = asyncio.Lock()
        self._metrics = CircuitBreakerMetrics(state=CircuitState.CLOSED)
        self._opened_at: Optional[float] = None

        self._initialized = True

    @property
    def state(self) -> CircuitState:
        """Current circuit state."""
        return self._state

    @property
    def metrics(self) -> CircuitBreakerMetrics:
        """Current metrics."""
        self._metrics.state = self._state
        return self._metrics

    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function with circuit breaker protection.
        
        :param func: Async function to call
        :param args: Function arguments
        :param kwargs: Function keyword arguments
        :return: Function result
        :raises CircuitBreakerOpen: If circuit is open
        :raises: Original exception if function fails
        """
        async with self._lock:
            await self._update_state()

            if self._state == CircuitState.OPEN:
                seconds_until_retry = self._get_seconds_until_retry()
                logger.warning(f"Circuit breaker OPEN for {self.name}, failing fast")
                raise CircuitBreakerOpen(self.name, seconds_until_retry)

            if self._state == CircuitState.HALF_OPEN:
                if self._half_open_calls >= self.config.half_open_max_calls:
                    seconds_until_retry = self._get_seconds_until_retry()
                    raise CircuitBreakerOpen(self.name, seconds_until_retry)
                self._half_open_calls += 1

            self._metrics.total_calls += 1

        # Execute the function outside the lock
        try:
            result = await func(*args, **kwargs)
            await self._on_success()
            return result
        except Exception as e:
            await self._on_failure(e)
            raise

    async def _update_state(self):
        """Update circuit state based on timing."""
        if self._state == CircuitState.OPEN:
            # Check if recovery timeout has passed
            if self._opened_at and time.time() - self._opened_at >= self.config.recovery_timeout:
                logger.info(f"Circuit breaker {self.name} transitioning to HALF_OPEN")
                self._state = CircuitState.HALF_OPEN
                self._half_open_calls = 0
                self._half_open_successes = 0

    async def _on_success(self):
        """Handle successful call."""
        async with self._lock:
            self._metrics.total_successes += 1
            self._metrics.last_success_time = time.time()

            if self._state == CircuitState.HALF_OPEN:
                self._half_open_successes += 1

                # Check if we can close the circuit
                if self._half_open_successes >= self.config.success_threshold:
                    logger.info(f"Circuit breaker {self.name} transitioning to CLOSED")
                    self._state = CircuitState.CLOSED
                    self._metrics.closed_at = time.time()
                    self._failure_times.clear()
                    self._metrics.failure_count = 0
            else:
                # In CLOSED state, clear old failures
                self._cleanup_old_failures()

    async def _on_failure(self, exception: Exception):
        """Handle failed call."""
        # Check if we should ignore this exception
        if isinstance(exception, self.config.ignored_exceptions):
            return

        async with self._lock:
            self._metrics.total_failures += 1
            self._metrics.last_failure_time = time.time()

            now = time.time()
            self._failure_times.append(now)
            self._cleanup_old_failures()

            if self._state == CircuitState.HALF_OPEN:
                # Failure in half-open state -> open immediately
                logger.warning(f"Circuit breaker {self.name} failure in HALF_OPEN, opening")
                await self._open_circuit()
            elif self._state == CircuitState.CLOSED:
                # Check if we've hit the threshold
                if len(self._failure_times) >= self.config.failure_threshold:
                    logger.warning(
                        f"Circuit breaker {self.name} hit failure threshold "
                        f"({len(self._failure_times)} failures in {self.config.failure_window}s)"
                    )
                    await self._open_circuit()

            self._metrics.failure_count = len(self._failure_times)

    async def _open_circuit(self):
        """Open the circuit."""
        self._state = CircuitState.OPEN
        self._opened_at = time.time()
        self._metrics.opened_at = self._opened_at
        logger.error(f"Circuit breaker {self.name} OPENED")

    def _cleanup_old_failures(self):
        """Remove failures outside the window."""
        cutoff = time.time() - self.config.failure_window
        self._failure_times = [t for t in self._failure_times if t > cutoff]

    def _get_seconds_until_retry(self) -> float:
        """Calculate seconds until next retry attempt."""
        if self._state == CircuitState.OPEN and self._opened_at:
            elapsed = time.time() - self._opened_at
            remaining = self.config.recovery_timeout - elapsed
            return max(0, remaining)
        return 0

    def reset(self):
        """Manually reset the circuit breaker to CLOSED state."""
        self._state = CircuitState.CLOSED
        self._failure_times.clear()
        self._half_open_calls = 0
        self._half_open_successes = 0
        self._opened_at = None
        self._metrics = CircuitBreakerMetrics(state=CircuitState.CLOSED)
        logger.info(f"Circuit breaker {self.name} manually reset to CLOSED")


def circuit_breaker(
    name: str,
    failure_threshold: int = 5,
    recovery_timeout: float = 30.0,
    half_open_max_calls: int = 3,
    expected_exceptions: tuple = (Exception,),
    ignored_exceptions: tuple = (),
):
    """
    Decorator for adding circuit breaker to async functions.
    
    Usage:
        @circuit_breaker("partymap")
        async def create_event(data):
            # ... API call
    
    :param name: Circuit breaker name (usually service name)
    :param failure_threshold: Failures before opening
    :param recovery_timeout: Seconds before half-open
    :param half_open_max_calls: Max calls in half-open state
    :param expected_exceptions: Exceptions that count as failures
    :param ignored_exceptions: Exceptions to ignore (don't count)
    """
    config = CircuitBreakerConfig(
        failure_threshold=failure_threshold,
        recovery_timeout=recovery_timeout,
        half_open_max_calls=half_open_max_calls,
        expected_exceptions=expected_exceptions,
        ignored_exceptions=ignored_exceptions,
    )
    breaker = CircuitBreaker(name, config)

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await breaker.call(func, *args, **kwargs)

        # Attach circuit breaker for manual control
        wrapper._circuit_breaker = breaker
        return wrapper

    return decorator


# Pre-configured circuit breakers for services

class ServiceCircuitBreakers:
    """Pre-configured circuit breakers for external services."""

    @staticmethod
    def get_partymap_breaker() -> CircuitBreaker:
        """Circuit breaker for PartyMap API."""
        return CircuitBreaker(
            "partymap",
            CircuitBreakerConfig(
                failure_threshold=5,
                recovery_timeout=30.0,
                half_open_max_calls=3,
                expected_exceptions=(Exception,),
            )
        )

    @staticmethod
    def get_exa_breaker() -> CircuitBreaker:
        """Circuit breaker for Exa API."""
        return CircuitBreaker(
            "exa",
            CircuitBreakerConfig(
                failure_threshold=5,
                recovery_timeout=30.0,
                half_open_max_calls=3,
                expected_exceptions=(Exception,),
            )
        )

    @staticmethod
    def get_llm_breaker() -> CircuitBreaker:
        """Circuit breaker for LLM/OpenRouter API."""
        return CircuitBreaker(
            "llm",
            CircuitBreakerConfig(
                failure_threshold=3,  # Lower threshold for LLM (expensive)
                recovery_timeout=60.0,  # Longer timeout
                half_open_max_calls=1,  # Be cautious
                expected_exceptions=(Exception,),
            )
        )


# Global registry for monitoring
def get_all_circuit_breakers() -> Dict[str, CircuitBreaker]:
    """Get all registered circuit breakers."""
    return dict(CircuitBreaker._instances)


def get_circuit_breaker_metrics() -> Dict[str, Dict[str, Any]]:
    """Get metrics for all circuit breakers."""
    return {
        name: breaker.metrics.to_dict()
        for name, breaker in CircuitBreaker._instances.items()
    }
