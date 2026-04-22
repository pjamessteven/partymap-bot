"""Structured logging configuration using structlog.

Provides a hybrid setup where:
- Existing stdlib `logging.getLogger(__name__)` calls continue to work
- Output is formatted as structured JSON (production) or pretty console (dev)
- New code can optionally use `structlog.get_logger()` for full structured logging

Usage:
    from src.utils.logging import get_logger
    logger = get_logger(__name__)
    logger.info("event_happened", key="value")

Or continue using stdlib logging (output will still be structured):
    import logging
    logger = logging.getLogger(__name__)
    logger.info("message: %s", value)
"""

import logging
import sys

import structlog

from src.config import get_settings


def configure_logging() -> None:
    """Configure structured logging for the application.

    Should be called once at application startup (e.g. in main.py lifespan).
    """
    settings = get_settings()
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    # Configure stdlib logging to route through structlog processors
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.ExtraAdder(),
    ]

    if settings.is_development:
        # Pretty console output for development
        processors = shared_processors + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ]
        formatter = structlog.dev.ConsoleRenderer(colors=True)
    else:
        # JSON output for production (easier to parse in log aggregation)
        processors = shared_processors + [
            structlog.processors.dict_tracebacks,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ]
        formatter = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Replace all existing handlers with structlog formatter
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            processor=formatter,
            foreign_pre_chain=shared_processors,
        )
    )

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(log_level)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Get a structured logger instance.

    Args:
        name: Logger name (usually __name__). If None, returns the root logger.

    Returns:
        A structlog BoundLogger that supports kwargs for structured output:
            logger.info("event", user_id=123, action="login")
    """
    return structlog.get_logger(name)
