"""Name cleaning utilities for deduplication."""

import re
from typing import Optional

from sqlalchemy import select

from src.utils.utc_now import utc_now


def clean_event_name(name: Optional[str]) -> Optional[str]:
    """
    Extract canonical event name by removing years and numbers.

    Examples:
        "Coachella Valley Music and Arts Festival 2026" -> "Coachella Valley Music and Arts Festival"
        "Burning Man 2025" -> "Burning Man"
        "Tomorrowland 2024 Edition" -> "Tomorrowland"
        "High Mountain Gathering VII" -> "High Mountain Gathering"
        "Psytrance Festival #12" -> "Psytrance Festival"
        "Dreamland Songkran Festival Pattaya 2026 House & Techno Party" -> "Dreamland Songkran Festival Pattaya House & Techno Party"

    Args:
        name: Raw event name from discovery

    Returns:
        Clean canonical name for deduplication, or None if input is None/empty
    """
    if not name or not isinstance(name, str):
        return None

    # Strip whitespace
    clean = name.strip()

    if not clean:
        return None

    # Patterns to remove:
    # - Years ANYWHERE: 2024, 2025, 2026, etc.
    # - Numbers at end: 1, 12, VII, #12, etc.
    # - Edition markers: "Edition", "Edt.", "Ed.", "Edition 2024"
    # - Generic suffixes: "Festival 2025", "Party 12"

    # Pattern 1: Remove years ANYWHERE in the string (not just at end)
    clean = re.sub(r"\s+20\d{2}\b", "", clean)

    # Pattern 2: Remove Roman numerals at the end (I, II, III, IV, V, VI, VII, VIII, IX, X, etc.)
    clean = re.sub(r"\s+[IVX]+\s*$", "", clean, flags=re.IGNORECASE)

    # Pattern 3: Remove "Edition" or "Edt." or "Ed." with optional year
    clean = re.sub(r"\s+(?:Edition|Edt\.?|Ed\.?)(?:\s+20\d{2})?\b", "", clean, flags=re.IGNORECASE)

    # Pattern 4: Remove "#number"
    clean = re.sub(r"\s+#\d+\b", "", clean)

    # Pattern 5: Remove standalone numbers at the end
    clean = re.sub(r"\s+\d+\s*$", "", clean)

    # Clean up extra whitespace and punctuation
    clean = re.sub(r"\s+", " ", clean)  # Normalize whitespace
    clean = clean.strip().rstrip(":–—")

    return clean if clean else name  # Return original if cleaning removes everything


def get_name_variations(name: str) -> list:
    """
    Get possible variations of an event name for fuzzy matching.

    Returns list of variations to check:
    - Original name
    - Lowercase version
    - Without years
    - Without common words like "festival", "party", "gathering"

    Args:
        name: Event name

    Returns:
        List of name variations
    """
    if not name:
        return []

    variations = {name, name.lower()}

    # Add cleaned version
    clean = clean_event_name(name)
    if clean and clean != name:
        variations.add(clean)
        variations.add(clean.lower())

    # Remove common generic words
    generic_words = ["festival", "party", "gathering", "event", "celebration", "edition"]
    for word in generic_words:
        # Remove word from start
        if name.lower().startswith(word + " "):
            variations.add(name[len(word) :].strip().lower())
        if clean and clean.lower().startswith(word + " "):
            variations.add(clean[len(word) :].strip().lower())

    return list(variations)


# In-memory cache for raw->clean name mappings
_name_mapping_cache: dict = {}


def _normalize_name(name: str) -> str:
    """Normalize name for cache lookup (remove spaces/punctuation)."""
    return re.sub(r"[^\w]", "", name.lower())


def store_name_mapping(raw_name: str, clean_name: str, source: str = None) -> None:
    """
    Store the raw->clean name mapping in memory cache.
    Database persistence is handled separately by the caller if needed.

    Args:
        raw_name: Original raw name
        clean_name: Cleaned canonical name
        source: Source of the mapping (e.g., 'llm', 'goabase', 'manual')
    """
    if not raw_name or not clean_name:
        return

    # Store in memory cache
    _name_mapping_cache[raw_name.lower()] = clean_name
    _name_mapping_cache[_normalize_name(raw_name)] = clean_name


def get_cached_clean_name(raw_name: str) -> Optional[str]:
    """
    Retrieve cached clean name if we've seen this raw name before.

    Args:
        raw_name: Raw name to look up

    Returns:
        Cached clean name or None
    """
    if not raw_name:
        return None

    # Try exact match first
    clean = _name_mapping_cache.get(raw_name.lower())
    if clean:
        return clean

    # Try normalized version
    return _name_mapping_cache.get(_normalize_name(raw_name))


def clean_name_with_cache(raw_name: Optional[str], source: str = None) -> Optional[str]:
    """
    Clean event name using cache if available, otherwise compute and cache.

    Args:
        raw_name: Raw event name
        source: Source of the mapping for tracking

    Returns:
        Clean canonical name
    """
    if not raw_name:
        return None

    # Check cache first
    cached = get_cached_clean_name(raw_name)
    if cached:
        return cached

    # Compute clean name
    clean = clean_event_name(raw_name)

    # Store mapping
    if clean:
        store_name_mapping(raw_name, clean, source)

    return clean


# Database-backed functions for persistent storage
# These are used when a DB session is available


def store_name_mapping_db(session, raw_name: str, clean_name: str, source: str = None) -> None:
    """
    Store name mapping in database for persistence.
    This should be called from Celery tasks with DB access.

    Args:
        session: SQLAlchemy session
        raw_name: Original raw name
        clean_name: Cleaned canonical name
        source: Source of the mapping
    """
    from src.core.models import NameMapping

    if not raw_name or not clean_name:
        return

    normalized = _normalize_name(raw_name)

    # Check if mapping already exists
    existing = session.execute(
        select(NameMapping).where(
            (NameMapping.raw_name == raw_name) | (NameMapping.normalized_raw == normalized)
        )
    ).scalar_one_or_none()

    if existing:
        # Update existing mapping
        existing.clean_name = clean_name
        existing.use_count += 1
        existing.updated_at = utc_now()
    else:
        # Create new mapping
        mapping = NameMapping(
            raw_name=raw_name,
            clean_name=clean_name,
            normalized_raw=normalized,
            source=source,
            use_count=1,
        )
        session.add(mapping)

    # Also update in-memory cache
    store_name_mapping(raw_name, clean_name, source)


def get_cached_clean_name_db(session, raw_name: str) -> Optional[str]:
    """
    Retrieve clean name from database cache.

    Args:
        session: SQLAlchemy session
        raw_name: Raw name to look up

    Returns:
        Cached clean name or None
    """
    from src.core.models import NameMapping

    if not raw_name:
        return None

    normalized = _normalize_name(raw_name)

    # Try in-memory cache first (faster)
    cached = get_cached_clean_name(raw_name)
    if cached:
        return cached

    # Try database
    mapping = session.execute(
        select(NameMapping).where(
            (NameMapping.raw_name == raw_name) | (NameMapping.normalized_raw == normalized)
        )
    ).scalar_one_or_none()

    if mapping:
        # Update in-memory cache and usage count
        _name_mapping_cache[raw_name.lower()] = mapping.clean_name
        _name_mapping_cache[normalized] = mapping.clean_name
        mapping.use_count += 1
        return mapping.clean_name

    return None


def clean_name_with_db(session, raw_name: Optional[str], source: str = None) -> Optional[str]:
    """
    Clean event name using database cache if available.

    Args:
        session: SQLAlchemy session
        raw_name: Raw event name
        source: Source of the mapping

    Returns:
        Clean canonical name
    """
    if not raw_name:
        return None

    # Try database/cache first
    cached = get_cached_clean_name_db(session, raw_name)
    if cached:
        return cached

    # Compute clean name
    clean = clean_event_name(raw_name)

    # Store in database
    if clean:
        store_name_mapping_db(session, raw_name, clean, source)

    return clean
