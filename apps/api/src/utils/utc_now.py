"""UTC datetime helpers for backward-compatible naive datetimes."""

from datetime import datetime, timezone


def utc_now() -> datetime:
    """Return current UTC time as a naive datetime.

    Equivalent to the deprecated datetime.utcnow() but uses the
    non-deprecated datetime.now(timezone.utc) under the hood.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)
