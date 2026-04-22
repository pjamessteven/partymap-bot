"""Error classification and tracking for festival pipeline.

This module provides:
- Error categorization (transient, permanent, validation, external, budget)
- Error context tracking for debugging
- Automatic retry decision logic
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from src.utils.utc_now import utc_now

logger = logging.getLogger(__name__)


class ErrorCategory(str, Enum):
    """Categories of errors for retry decisions and UI display."""

    TRANSIENT = "transient"  # Temporary issue, should retry (e.g., rate limit, timeout)
    PERMANENT = "permanent"  # Permanent failure, don't retry (e.g., 404, auth failure)
    VALIDATION = "validation"  # Data validation failure
    EXTERNAL = "external"  # External service failure (e.g., PartyMap API down)
    BUDGET = "budget"  # Budget limit exceeded
    UNKNOWN = "unknown"  # Uncategorized error


@dataclass
class ErrorContext:
    """Rich error context for debugging and UI display."""

    # Core error info
    category: ErrorCategory
    message: str
    exception_type: Optional[str] = None
    traceback: Optional[str] = None

    # Service context
    service: Optional[str] = None  # "partymap", "exa", "openrouter", "database"
    operation: Optional[str] = None  # "create_event", "search", "research"

    # HTTP context (for API errors)
    status_code: Optional[int] = None
    response_body: Optional[str] = None
    request_url: Optional[str] = None

    # Retry context
    retry_count: int = 0
    max_retries: int = 3
    is_retryable: bool = True

    # Timing
    timestamp: datetime = field(default_factory=utc_now)
    first_error_at: Optional[datetime] = None

    # Additional metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "category": self.category.value,
            "message": self.message,
            "exception_type": self.exception_type,
            "service": self.service,
            "operation": self.operation,
            "status_code": self.status_code,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "is_retryable": self.is_retryable,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "first_error_at": self.first_error_at.isoformat() if self.first_error_at else None,
            "metadata": self.metadata,
        }

    @classmethod
    def from_exception(
        cls,
        exception: Exception,
        category: Optional[ErrorCategory] = None,
        service: Optional[str] = None,
        operation: Optional[str] = None,
    ) -> "ErrorContext":
        """Create ErrorContext from an exception."""
        import traceback as tb

        # Auto-categorize if not provided
        if category is None:
            category = categorize_error(exception, service)

        # Extract HTTP status code if available
        status_code = None
        if hasattr(exception, "status_code"):
            status_code = exception.status_code
        elif hasattr(exception, "response") and hasattr(exception.response, "status_code"):
            status_code = exception.response.status_code

        # Extract response body if available
        response_body = None
        if hasattr(exception, "response"):
            try:
                response_body = exception.response.text if hasattr(exception.response, "text") else str(exception.response)
            except Exception:
                pass

        return cls(
            category=category,
            message=str(exception),
            exception_type=type(exception).__name__,
            traceback="".join(tb.format_exception(type(exception), exception, exception.__traceback__)),
            service=service,
            operation=operation,
            status_code=status_code,
            response_body=response_body,
            is_retryable=is_retryable_error(exception, category),
        )


def categorize_error(exception: Exception, service: Optional[str] = None) -> ErrorCategory:
    """
    Automatically categorize an error based on exception type and service.
    
    :param exception: The exception to categorize
    :param service: The service that raised the error (optional)
    :return: ErrorCategory
    """
    exception_type = type(exception).__name__
    message = str(exception).lower()

    # Check for HTTP status codes first
    status_code = None
    if hasattr(exception, "status_code"):
        status_code = exception.status_code
    elif hasattr(exception, "response") and hasattr(exception.response, "status_code"):
        status_code = exception.response.status_code

    if status_code:
        # 4xx errors (client errors) are usually permanent
        if 400 <= status_code < 500:
            if status_code in (429, 408):  # Rate limit, timeout
                return ErrorCategory.TRANSIENT
            elif status_code == 422:  # Validation error
                return ErrorCategory.VALIDATION
            elif status_code in (401, 403):  # Auth errors
                return ErrorCategory.PERMANENT
            else:
                return ErrorCategory.PERMANENT

        # 5xx errors (server errors) are usually transient
        if status_code >= 500:
            return ErrorCategory.EXTERNAL

    # Check exception types
    transient_exceptions = (
        "TimeoutError",
        "AsyncTimeoutError",
        "ConnectionError",
        "ConnectionResetError",
        "ConnectionRefusedError",
        "NetworkError",
        "RateLimitError",
        "ReadTimeout",
        "ConnectTimeout",
    )

    if exception_type in transient_exceptions:
        return ErrorCategory.TRANSIENT

    # Check for rate limiting in message
    rate_limit_keywords = [
        "rate limit", "too many requests", "throttled",
        "quota exceeded", "limit exceeded"
    ]
    if any(keyword in message for keyword in rate_limit_keywords):
        return ErrorCategory.TRANSIENT

    # Check for validation errors
    validation_keywords = [
        "validation", "invalid", "required", "schema",
        "missing field", "bad request"
    ]
    if any(keyword in message for keyword in validation_keywords):
        return ErrorCategory.VALIDATION

    # Check for budget errors
    budget_keywords = [
        "budget", "cost limit", "quota exceeded",
        "insufficient funds", "payment required"
    ]
    if any(keyword in message for keyword in budget_keywords):
        return ErrorCategory.BUDGET

    # Check for not found errors (permanent)
    not_found_keywords = [
        "not found", "does not exist", "404"
    ]
    if any(keyword in message for keyword in not_found_keywords):
        return ErrorCategory.PERMANENT

    # Service-specific categorization
    if service == "partymap":
        # PartyMap-specific errors
        if "event" in message and "not found" in message:
            return ErrorCategory.PERMANENT
        if "duplicate" in message:
            return ErrorCategory.VALIDATION

    elif service == "exa":
        # Exa API errors
        if "invalid query" in message:
            return ErrorCategory.VALIDATION

    # Default to unknown for unclassified errors
    return ErrorCategory.UNKNOWN


def is_retryable_error(exception: Exception, category: Optional[ErrorCategory] = None) -> bool:
    """
    Determine if an error is retryable.
    
    :param exception: The exception to check
    :param category: Pre-determined category (optional)
    :return: True if error is retryable
    """
    if category is None:
        category = categorize_error(exception)

    return category in (
        ErrorCategory.TRANSIENT,
        ErrorCategory.EXTERNAL,
        ErrorCategory.UNKNOWN,  # Retry unknown errors once
    )


def get_retry_delay(exception: Exception, retry_count: int, base_delay: float = 1.0) -> float:
    """
    Calculate retry delay with exponential backoff.
    
    :param exception: The exception that caused the failure
    :param retry_count: Current retry attempt (0-indexed)
    :param base_delay: Base delay in seconds
    :return: Delay in seconds
    """
    import random

    # Exponential backoff: base_delay * 2^retry_count + jitter
    delay = base_delay * (2 ** retry_count)

    # Add jitter (±20%)
    jitter = delay * 0.2 * (random.random() - 0.5)
    delay = delay + jitter

    # Cap at 60 seconds
    return min(delay, 60.0)


class ErrorTracker:
    """Track errors for a festival with full context."""

    def __init__(self, festival_id: str, max_history: int = 10):
        self.festival_id = festival_id
        self.max_history = max_history
        self.errors: list = []
        self.first_error_at: Optional[datetime] = None
        self.last_error_at: Optional[datetime] = None
        self.retry_count: int = 0

    def record_error(self, context: ErrorContext) -> None:
        """Record a new error."""
        now = utc_now()

        if not self.first_error_at:
            self.first_error_at = now
        self.last_error_at = now

        if context.is_retryable:
            self.retry_count += 1

        # Add to history, keeping max_history entries
        self.errors.append(context)
        if len(self.errors) > self.max_history:
            self.errors.pop(0)

        logger.warning(
            f"Error recorded for festival {self.festival_id}: "
            f"{context.category.value} - {context.message}"
        )

    def should_retry(self, max_retries: int = 3) -> bool:
        """Determine if we should retry based on error history."""
        if not self.errors:
            return True

        last_error = self.errors[-1]

        # Don't retry non-retryable errors
        if not last_error.is_retryable:
            return False

        # Check retry count
        if self.retry_count >= max_retries:
            return False

        return True

    def get_error_summary(self) -> Dict[str, Any]:
        """Get summary of errors for UI display."""
        if not self.errors:
            return {
                "has_errors": False,
                "error_count": 0,
                "retry_count": self.retry_count,
            }

        last_error = self.errors[-1]

        return {
            "has_errors": True,
            "error_count": len(self.errors),
            "retry_count": self.retry_count,
            "last_error": {
                "category": last_error.category.value,
                "message": last_error.message,
                "service": last_error.service,
                "timestamp": last_error.timestamp.isoformat(),
            },
            "categories": list(set(e.category.value for e in self.errors)),
            "first_error_at": self.first_error_at.isoformat() if self.first_error_at else None,
            "last_error_at": self.last_error_at.isoformat() if self.last_error_at else None,
        }


def format_error_for_display(context: ErrorContext) -> str:
    """Format error context for human-readable display."""
    parts = [f"[{context.category.value.upper()}]"]

    if context.service:
        parts.append(f"{context.service}")

    if context.operation:
        parts.append(f"({context.operation})")

    parts.append(f": {context.message}")

    if context.status_code:
        parts.append(f" (HTTP {context.status_code})")

    return " ".join(parts)
