"""PartyMap API client with proper Event/EventDate handling."""

import asyncio
import logging
from typing import List, Optional

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.config import Settings
from src.core.database import get_async_redis_client
from src.core.schemas import (
    DuplicateCheckResult,
    EventDateData,
    FestivalData,
)
from src.services.circuit_breaker import circuit_breaker
from src.utils.utc_now import utc_now

logger = logging.getLogger(__name__)

# Redis key for global rate limiting
_PARTYMAP_RATE_LIMIT_KEY = "ratelimit:partymap:last_request"


class PartyMapAPIError(Exception):
    """PartyMap API error."""

    def __init__(self, message: str, status_code: int = None, response: dict = None):
        super().__init__(message)
        self.status_code = status_code
        self.response = response


class PartyMapClient:
    """
    Client for PartyMap API.

    Base URL: https://api.partymap.com/api

    CRITICAL: Uses proper Event/EventDate separation:
    - Event object: General info only (name, description, media, URL, tags)
    - EventDate objects: Date-specific info (dates, location, lineup, tickets)

    NEVER update date_time/location/rrule on main Event (would delete future EventDates!)
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self.base_url = settings.effective_partymap_base_url
        self.client = httpx.AsyncClient(
            headers={
                "X-API-Key": settings.partymap_api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=30.0,
        )

    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    async def _rate_limit(self):
        """Apply global rate limiting between requests using Redis."""
        min_interval = 0.5  # 500ms between requests = max 120 req/min

        try:
            redis = get_async_redis_client()
            # Use Redis to enforce global rate limit across all instances
            # Get current time and last request time atomically
            now = utc_now().timestamp()

            # Get the last request time from Redis
            last_request = await redis.get(_PARTYMAP_RATE_LIMIT_KEY)
            if last_request:
                elapsed = now - float(last_request)
                if elapsed < min_interval:
                    sleep_time = min_interval - elapsed
                    logger.debug(f"Global rate limiting PartyMap: sleeping {sleep_time:.3f}s")
                    await asyncio.sleep(sleep_time)

            # Update the last request time
            await redis.set(_PARTYMAP_RATE_LIMIT_KEY, utc_now().timestamp())
        except (ConnectionError, TimeoutError, OSError) as e:
            # If Redis fails, fall back to simple delay to be safe
            logger.warning(f"Redis rate limiting failed, using fallback: {e}")
            await asyncio.sleep(min_interval)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.NetworkError)),
        reraise=True,
    )
    async def _raw_request(self, method: str, url: str, **kwargs) -> httpx.Response:
        """Make raw HTTP request with tenacity retry on 5xx/network errors."""
        response = await self.client.request(method, url, **kwargs)
        response.raise_for_status()
        return response

    @circuit_breaker("partymap", failure_threshold=5, recovery_timeout=30.0)
    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        """Make rate-limited HTTP request with retries and error conversion."""
        await self._rate_limit()

        # Fix double slash issue
        base = self.base_url.rstrip("/")
        path_clean = path.lstrip("/")
        url = f"{base}/{path_clean}"

        # Debug: Log headers (with masked API key)
        headers = self.client.headers
        debug_headers = dict(headers)
        if "X-API-Key" in debug_headers:
            key = debug_headers["X-API-Key"]
            debug_headers["X-API-Key"] = f"{key[:5]}...{key[-5:]}" if len(key) > 10 else "***"
        logger.debug(f"PartyMap API request: {method} {url} - Headers: {debug_headers}")

        try:
            return await self._raw_request(method, url, **kwargs)
        except httpx.HTTPStatusError as e:
            logger.error(f"PartyMap API error: {e.response.status_code} - {e.response.text}")
            try:
                error_body = e.response.json() if e.response.content else None
            except Exception:
                error_body = {"raw": e.response.text}
            raise PartyMapAPIError(
                f"API error: {e.response.status_code}",
                status_code=e.response.status_code,
                response=error_body,
            )

    # ==================== Event Operations ====================

    async def create_event(self, festival_data: FestivalData) -> int:
        """
        Create new Event in PartyMap.

        POST /api/event/

        Sends combined event + first event_date data with all enhanced fields.
        """
        # Build payload with event + first event_date
        event_date = festival_data.event_dates[0] if festival_data.event_dates else None

        payload = {
            "name": festival_data.name,
            "description": festival_data.description or f"{festival_data.name} music festival",
            "description_attribute": None,
            "full_description": festival_data.full_description or "",
            "full_description_attribute": None,
            "youtube_url": str(festival_data.youtube_url) if festival_data.youtube_url else None,
            "url": str(festival_data.website_url) if festival_data.website_url else None,
            "tags": festival_data.tags[:5] if festival_data.tags else [],  # Max 5 tags
        }

        # Add logo if present
        if festival_data.logo_url:
            payload["logo"] = {"url": str(festival_data.logo_url)}

        # Add media items (gallery photos) with captions
        if festival_data.media_items:
            payload["media_items"] = [
                {
                    "url": str(m.url),
                    "caption": m.caption or f"Photo from {festival_data.source_url or 'festival website'}"
                }
                for m in festival_data.media_items
            ]

        # Add RRULE if festival is recurring
        if festival_data.is_recurring and festival_data.rrule:
            payload["rrule"] = {
                "recurringType": festival_data.rrule.recurringType,
                "separationCount": festival_data.rrule.separationCount,
                "dayOfWeek": festival_data.rrule.dayOfWeek,
                "weekOfMonth": festival_data.rrule.weekOfMonth,
                "monthOfYear": festival_data.rrule.monthOfYear,
                "dayOfMonth": festival_data.rrule.dayOfMonth,
                "exact": festival_data.rrule.exact,
            }

        # Add first event_date data
        if event_date:
            payload["date_time"] = {"start": event_date.start.isoformat()}
            if event_date.end:
                payload["date_time"]["end"] = event_date.end.isoformat()
            payload["location"] = {"description": event_date.location_description}

            # Lineup artists
            if event_date.lineup:
                payload["next_event_date_artists"] = [{"name": name} for name in event_date.lineup]

            # Size (capacity/attendance)
            size = getattr(event_date, 'size', None) or getattr(event_date, 'expected_size', None)
            if size:
                payload["next_event_date_size"] = size

            # Structured tickets with pricing
            if event_date.tickets:
                payload["tickets"] = [
                    {
                        "url": str(ticket.url) if ticket.url else None,
                        "description": ticket.description,
                        "price_min": float(ticket.price_min) if ticket.price_min else None,
                        "price_max": float(ticket.price_max) if ticket.price_max else None,
                        "price_currency_code": ticket.price_currency_code,
                    }
                    for ticket in event_date.tickets
                ]

            # Lineup images
            lineup_images = getattr(event_date, 'lineup_images', None)
            if lineup_images:
                payload["next_event_date_lineup_images"] = [
                    {
                        "url": url,
                        "caption": f"Lineup from {festival_data.source_url or 'festival website'}"
                    }
                    for url in lineup_images
                ]

        try:
            response = await self._request("POST", "/api/event/", json=payload)
            result = response.json()

            event_id = result.get("id")
            if not event_id:
                raise PartyMapAPIError("No event ID returned from create")

            logger.info(f"Created PartyMap event: {festival_data.name} (ID: {event_id})")
            return int(event_id) if isinstance(event_id, (str, int)) else event_id
        except PartyMapAPIError as e:
            # PartyMap server may return 500/503 but still create the event
            # (known bug with SQLAlchemy session serialization)
            if e.status_code in (500, 503):
                logger.warning(f"PartyMap returned {e.status_code} but event may have been created")
                return None  # Caller should search for the event
            raise

    async def update_event(
        self, event_id: int, festival_data: FestivalData, message: str = "Updated by festival bot"
    ) -> None:
        """
        Update general Event info.

        PUT /api/event/{event_id}

        Only updates general fields (NO date_time, location, rrule!).
        Adding date_time/location here would DELETE all future EventDates!
        """
        payload = {
            "message": message,
        }

        # Only include fields that have values
        if festival_data.name:
            payload["name"] = festival_data.name
        if festival_data.description:
            payload["description"] = festival_data.description
        if festival_data.full_description:
            payload["full_description"] = festival_data.full_description
        if festival_data.youtube_url:
            payload["youtube_url"] = str(festival_data.youtube_url)
        if festival_data.website_url:
            payload["url"] = str(festival_data.website_url)
        if festival_data.tags:
            payload["add_tags"] = festival_data.tags[:5]  # Max 5 tags
        if festival_data.logo_url:
            payload["logo"] = {"url": str(festival_data.logo_url)}
        if festival_data.media_items:
            payload["media_items"] = [
                {
                    "url": str(m.url),
                    "caption": m.caption or f"Photo from {festival_data.source_url or 'festival website'}"
                }
                for m in festival_data.media_items
            ]

        # NOTE: We intentionally do NOT include:
        # - date_time (would delete EventDates)
        # - location (would delete EventDates)
        # - rrule (would affect recurrence)

        await self._request("PUT", f"/api/event/{event_id}", json=payload)
        logger.info(f"Updated PartyMap event: {event_id}")

    # ==================== EventDate Operations ====================

    async def add_event_date(self, event_id: int, event_date: EventDateData) -> int:
        """
        Add EventDate to existing Event.

        POST /api/date/event/{event_id}

        Contains date-specific info (dates, location, lineup, tickets).
        """
        payload = self._event_date_to_payload(event_date)

        response = await self._request("POST", f"/api/date/event/{event_id}", json=payload)

        result = response.json()
        date_id = result.get("id")

        if not date_id:
            raise PartyMapAPIError("No event date ID returned")

        logger.info(f"Added EventDate to {event_id}: {event_date.start} (ID: {date_id})")
        return int(date_id) if isinstance(date_id, (str, int)) else date_id

    async def update_event_date(self, event_date_id: int, event_date: EventDateData) -> None:
        """
        Update existing EventDate.

        PUT /api/date/{id}
        """
        payload = self._event_date_to_payload(event_date)

        await self._request("PUT", f"/api/date/{event_date_id}", json=payload)
        logger.info(f"Updated EventDate {event_date_id}")

    def _event_date_to_payload(self, event_date: EventDateData, source_url: str = None) -> dict:
        """Convert EventDateData to PartyMap API payload."""
        payload = {
            "date_time": {"start": event_date.start.isoformat()},
            "location": {"description": event_date.location_description},
        }
        if event_date.end:
            payload["date_time"]["end"] = event_date.end.isoformat()

        # Add URL (source_url for this date)
        if event_date.source_url:
            payload["url"] = event_date.source_url

        # Add size (capacity/attendance)
        size = getattr(event_date, 'size', None) or getattr(event_date, 'expected_size', None)
        if size:
            payload["size"] = size

        # Add artists
        if event_date.lineup:
            payload["artists"] = [{"name": name} for name in event_date.lineup]

        # Add structured tickets with pricing
        if event_date.tickets:
            payload["tickets"] = [
                {
                    "url": str(ticket.url) if ticket.url else None,
                    "description": ticket.description,
                    "price_min": float(ticket.price_min) if ticket.price_min else None,
                    "price_max": float(ticket.price_max) if ticket.price_max else None,
                    "price_currency_code": ticket.price_currency_code,
                }
                for ticket in event_date.tickets
            ]

        # Add lineup images
        lineup_images = getattr(event_date, 'lineup_images', None)
        if lineup_images:
            payload["lineup_images"] = [
                {
                    "url": url,
                    "caption": f"Lineup from {source_url or 'festival website'}"
                }
                for url in lineup_images
            ]

        return payload

    # ==================== Search & Discovery ====================

    async def search_events(self, query: str, limit: int = 20) -> List[dict]:
        """
        Search existing events in PartyMap.

        GET /api/event/?search={query}
        """
        try:
            response = await self._request(
                "GET",
                "/api/event/",
                params={"search": query, "per_page": limit},
            )
            data = response.json()
            # Handle both { "items": [...] } and direct array
            events = data.get("items", data) if isinstance(data, dict) else data
            return events[:limit] if isinstance(events, list) else []
        except PartyMapAPIError as e:
            logger.error(f"Failed to search events: {e}")
            return []

    async def get_event(self, event_id: int) -> Optional[dict]:
        """
        Get event details by ID including EventDates.

        GET /api/event/{event_id}
        """
        try:
            response = await self._request("GET", f"/api/event/{event_id}")
            return response.json()
        except PartyMapAPIError as e:
            if e.status_code == 404:
                return None
            raise

    async def get_event_by_url(self, url: str) -> Optional[dict]:
        """
        Search for event by URL.

        Checks both event.url and event_dates.url fields.

        :param url: The URL to search for
        :return: Event dict if found, None otherwise
        """
        if not url:
            return None

        try:
            # Search with URL as query term
            events = await self.search_events(url, limit=20)

            for event in events:
                # Check event's main URL
                if event.get("url") == url:
                    return event

                # Check event_dates URLs
                for date in event.get("event_dates", []):
                    if date.get("url") == url:
                        return event

            return None

        except Exception as e:
            logger.error(f"Failed to search event by URL: {e}")
            return None

    async def update_event_by_id(
        self, event_id: int, festival_data: FestivalData, message: str = "Updated by Goabase sync"
    ) -> bool:
        """
        Update existing event by ID.

        PUT /api/event/{event_id}

        :param event_id: The PartyMap event ID (int)
        :param festival_data: The festival data to update
        :param message: Update message
        :return: True if successful
        """
        try:
            payload = {
                "message": message,
            }

            # Include all fields that have values
            if festival_data.name:
                payload["name"] = festival_data.name
            if festival_data.description:
                payload["description"] = festival_data.description
            if festival_data.full_description:
                payload["full_description"] = festival_data.full_description
            if festival_data.youtube_url:
                payload["youtube_url"] = str(festival_data.youtube_url)
            if festival_data.website_url:
                payload["url"] = str(festival_data.website_url)
            if festival_data.tags:
                payload["add_tags"] = festival_data.tags
            if festival_data.logo_url:
                payload["logo"] = {"url": str(festival_data.logo_url)}
            if festival_data.media_items:
                payload["media_items"] = [
                    {
                        "url": str(m.url),
                        "caption": m.caption or f"Photo from {festival_data.source_url or 'festival website'}"
                    }
                    for m in festival_data.media_items
                ]

            await self._request("PUT", f"/api/event/{event_id}", json=payload)
            logger.info(f"Updated PartyMap event {event_id}: {festival_data.name}")
            return True

        except Exception as e:
            logger.error(f"Failed to update event {event_id}: {e}")
            return False

    # ==================== Duplicate Checking ====================

    async def check_duplicate(
        self,
        name: str,
        clean_name: Optional[str] = None,
        source_url: Optional[str] = None,
        location: Optional[str] = None,
        event_date: Optional[EventDateData] = None,
    ) -> DuplicateCheckResult:
        """
        Check if festival already exists in PartyMap.

        Uses two-stage approach:
        1. Search by clean_name (canonical name without years/numbers)
        2. Search by raw name as fallback

        Returns DuplicateCheckResult with:
        - is_duplicate: bool
        - existing_event_id: UUID if exists
        - is_new_event_date: bool (if existing but new date/location)
        - date_confirmed: bool (if False, need to update)
        """
        try:
            # Try search by clean_name first (more accurate)
            search_name = clean_name if clean_name else name
            events = await self.search_events(search_name, limit=20)

            # If no results with clean_name, try raw name
            if not events and clean_name and clean_name != name:
                events = await self.search_events(name, limit=20)

            if not events:
                return DuplicateCheckResult(
                    is_duplicate=False, confidence=1.0, reason="No events found with similar name"
                )

            # Check for exact source URL match on EventDates
            if source_url:
                for event in events:
                    event_id = event.get("id")
                    for date in event.get("event_dates", []):
                        if date.get("url") == source_url:
                            return DuplicateCheckResult(
                                is_duplicate=True,
                                existing_event_id=int(event_id)
                                if isinstance(event_id, (str, int))
                                else None,
                                is_new_event_date=False,
                                date_confirmed=True,
                                confidence=1.0,
                                reason="Exact source URL match",
                            )

            # Check name + location similarity using BOTH clean_name and raw name
            best_match = None
            best_score = 0.0

            for event in events:
                event_name = event.get("name", "")

                # Try matching with clean_name first (higher weight)
                if clean_name:
                    clean_score = self._calculate_similarity(clean_name, event_name)
                    if clean_score > 0.8:  # Very high similarity on clean name
                        if location:
                            event_loc = event.get("location", {}).get("description", "")
                            loc_score = self._location_similarity(location, event_loc)
                            if loc_score > 0.5:
                                clean_score += 0.2

                        if clean_score > best_score:
                            best_score = clean_score
                            best_match = event
                            continue  # Skip raw name check if clean match is good

                # Fallback to raw name matching
                score = self._calculate_similarity(name, event_name)

                if score > 0.7:  # High name similarity
                    if location:
                        event_loc = event.get("location", {}).get("description", "")
                        loc_score = self._location_similarity(location, event_loc)
                        if loc_score > 0.5:
                            score += 0.2

                    if score > best_score:
                        best_score = score
                        best_match = event

            if not best_match:
                return DuplicateCheckResult(
                    is_duplicate=False, confidence=1.0, reason="No similar events found"
                )

            # Found potential match
            existing_id = best_match.get("id")
            existing_event_id = int(existing_id) if isinstance(existing_id, (str, int)) else None

            # Check if new EventDate
            if event_date:
                is_new_date = await self._is_new_event_date(
                    existing_event_id, event_date, best_match.get("event_dates", [])
                )

                if is_new_date:
                    return DuplicateCheckResult(
                        is_duplicate=True,
                        existing_event_id=existing_event_id,
                        is_new_event_date=True,
                        date_confirmed=True,
                        confidence=best_score,
                        reason="Existing event series, new date/location",
                        existing_event_data=best_match,
                    )
                else:
                    # Same date, check if needs update
                    date_confirmed = self._check_date_confirmed(
                        best_match.get("event_dates", []), event_date
                    )

                    return DuplicateCheckResult(
                        is_duplicate=True,
                        existing_event_id=existing_event_id,
                        is_new_event_date=False,
                        date_confirmed=date_confirmed,
                        confidence=best_score,
                        reason="Existing event and date"
                        + (" (needs update)" if not date_confirmed else ""),
                        existing_event_data=best_match,
                    )

            # No event date to compare, assume general match
            return DuplicateCheckResult(
                is_duplicate=True,
                existing_event_id=existing_event_id,
                is_new_event_date=False,
                date_confirmed=True,
                confidence=best_score,
                reason="Similar name and location found",
                existing_event_data=best_match,
            )

        except Exception as e:
            logger.error(f"Duplicate check failed: {e}")
            return DuplicateCheckResult(
                is_duplicate=False, confidence=0.0, reason=f"Check failed: {e}"
            )

    def _calculate_similarity(self, name1: str, name2: str) -> float:
        """Calculate name similarity (0-1)."""
        n1 = name1.lower().strip()
        n2 = name2.lower().strip()

        if not n1 or not n2:
            return 0.0

        if n1 == n2:
            return 1.0

        if n1 in n2 or n2 in n1:
            return 0.9

        words1 = set(n1.split())
        words2 = set(n2.split())

        intersection = words1 & words2
        union = words1 | words2

        return len(intersection) / len(union)

    def _location_similarity(self, loc1: str, loc2: str) -> float:
        """Calculate location similarity (0-1)."""
        if not loc1 or not loc2:
            return 0.0

        l1 = loc1.lower()
        l2 = loc2.lower()

        if l1 in l2 or l2 in l1:
            return 1.0

        parts1 = set(l1.split(","))
        parts2 = set(l2.split(","))

        intersection = parts1 & parts2
        if intersection:
            return len(intersection) / max(len(parts1), len(parts2))

        return 0.0

    async def _is_new_event_date(
        self, existing_event_id: int, event_date: EventDateData, existing_dates: list
    ) -> bool:
        """Check if this is a new EventDate for the series."""
        from dateutil import parser

        new_start = event_date.start
        new_location = event_date.location_description.lower()

        for existing in existing_dates:
            existing_start_str = existing.get("start")
            if not existing_start_str:
                continue

            try:
                existing_start = parser.parse(existing_start_str)

                # Check if same date (within 1 day tolerance)
                if abs((existing_start - new_start).days) < 2:
                    # Check location similarity
                    existing_loc = existing.get("location", {}).get("description", "").lower()
                    if self._location_similarity(new_location, existing_loc) > 0.7:
                        return False  # Same date + location = existing

            except Exception:
                continue

        return True  # New date

    def _check_date_confirmed(self, existing_dates: list, event_date: EventDateData) -> bool:
        """
        Check if existing date is confirmed or needs update.

        Returns False if data seems incomplete (no lineup, no tickets, etc.)
        """
        from dateutil import parser

        new_start = event_date.start

        for existing in existing_dates:
            existing_start_str = existing.get("start")
            if not existing_start_str:
                continue

            try:
                existing_start = parser.parse(existing_start_str)

                if abs((existing_start - new_start).days) < 2:
                    # Same date, check completeness
                    lineup = existing.get("artists", [])
                    has_tickets = existing.get("tickets")

                    # Consider confirmed if has lineup AND tickets
                    if lineup and has_tickets:
                        return True
                    else:
                        return False

            except Exception:
                continue

        return False  # Not found, needs update

    # ==================== Sync Strategy ====================

    async def sync_festival(
        self, festival_data: FestivalData, duplicate_check: DuplicateCheckResult
    ) -> dict:
        """
        Main sync method that handles all cases.

        Cases:
        1. New event → Create Event + add EventDate(s)
        2. New EventDate for existing → Add EventDate
        3. Update general info → PUT /events/{id}
        4. Update EventDate → PUT /api/date/event/{id}/{date_id}
        """
        result = {
            "action": "unknown",
            "event_id": None,
            "event_date_ids": [],
        }

        if not duplicate_check.is_duplicate:
            # Case 1: New event
            event_id = await self.create_event(festival_data)
            result["event_id"] = event_id
            result["action"] = "created"

            # Add all EventDates
            for event_date in festival_data.event_dates:
                date_id = await self.add_event_date(event_id, event_date)
                result["event_date_ids"].append(str(date_id))

        elif duplicate_check.is_new_event_date:
            # Case 2: New EventDate for existing event
            event_id = duplicate_check.existing_event_id
            result["event_id"] = event_id
            result["action"] = "added_event_date"

            for event_date in festival_data.event_dates:
                date_id = await self.add_event_date(event_id, event_date)
                result["event_date_ids"].append(str(date_id))

        elif not duplicate_check.date_confirmed:
            # Case 3 & 4: Update existing
            event_id = duplicate_check.existing_event_id
            result["event_id"] = event_id
            result["action"] = "updated"

            # Update general info
            await self.update_event(event_id, festival_data)

            # For EventDates, we need to find matching ones or add new
            # For now, add as new (PartyMap should handle deduplication)
            for event_date in festival_data.event_dates:
                date_id = await self.add_event_date(event_id, event_date)
                result["event_date_ids"].append(str(date_id))

        else:
            # Up to date, skip
            result["action"] = "skipped"
            result["event_id"] = duplicate_check.existing_event_id
            logger.info(f"Festival up to date, skipping: {festival_data.name}")

        return result

    # ==================== Tag Operations ====================

    async def get_tags(
        self,
        sort: str = "count",
        per_page: int = 150,
        page: int = 1,
        desc: bool = True,
    ) -> Optional[dict]:
        """
        Get popular tags from PartyMap.

        GET /api/tag/?sort=count&per_page=150&page=1&desc=true

        :param sort: Property to sort on ("count" or "created_at")
        :param per_page: Items per page (max 150)
        :param page: Page number (1-indexed)
        :param desc: Reverse sort results
        :return: Tag response with items array
        """
        try:
            response = await self._request(
                "GET",
                "/api/tag/",
                params={
                    "sort": sort,
                    "per_page": min(per_page, 150),  # Max 150
                    "page": page,
                    "desc": str(desc).lower(),
                },
            )
            return response.json()
        except PartyMapAPIError as e:
            logger.error(f"Failed to get tags: {e}")
            raise

    # ==================== Refresh Pipeline ====================

    async def get_unconfirmed_event_dates(
        self,
        days_ahead: int = 120,
        limit: int = 100,
        offset: int = 0,
    ) -> List[dict]:
        """
        Get EventDates with unconfirmed dates from PartyMap.

        These are future dates from RRULE that need verification.
        Only returns dates within the specified window.

        GET /api/event_date/?date_unconfirmed=true&start_after=...&start_before=...

        :param days_ahead: Only get dates within this many days
        :param limit: Max results
        :param offset: Pagination offset
        :return: List of EventDate objects with parent Event info
        """
        from datetime import timedelta

        start_after = utc_now().isoformat()
        start_before = (utc_now() + timedelta(days=days_ahead)).isoformat()

        try:
            response = await self._request(
                "GET",
                "/api/event_date/",
                params={
                    "date_unconfirmed": "true",
                    "start_after": start_after,
                    "start_before": start_before,
                    "limit": limit,
                    "offset": offset,
                },
            )
            data = response.json()
            items = data.get("items", data) if isinstance(data, dict) else data
            return items if isinstance(items, list) else []
        except PartyMapAPIError as e:
            logger.error(f"Failed to get unconfirmed event dates: {e}")
            return []

    async def get_event_with_dates(self, event_id: int) -> Optional[dict]:
        """
        Get full Event with all EventDates.

        Provides complete context for refresh agent.

        GET /api/event/{event_id}

        :param event_id: PartyMap event ID
        :return: Event dict with all EventDates
        """
        return await self.get_event(event_id)

    async def update_event_date_fields(
        self,
        event_date_id: int,
        updates: dict,
        message: str = "Updated by refresh pipeline",
    ) -> bool:
        """
        Update an existing EventDate with confirmed/improved data.

        PUT /api/date/{event_date_id}

        :param event_date_id: The EventDate ID
        :param updates: Dict of fields to update
        :param message: Update message
        :return: True if successful
        """
        try:
            payload = {"message": message, **updates}
            await self._request("PUT", f"/api/date/{event_date_id}", json=payload)
            logger.info(f"Updated EventDate {event_date_id}")
            return True
        except PartyMapAPIError as e:
            logger.error(f"Failed to update EventDate {event_date_id}: {e}")
            return False

    async def mark_event_date_cancelled(
        self,
        event_date_id: int,
        reason: str = "Date not confirmed",
    ) -> bool:
        """
        Mark an EventDate as cancelled.

        Used when date is still unconfirmed 30 days away.

        PUT /api/date/{event_date_id}

        :param event_date_id: The EventDate ID
        :param reason: Cancellation reason
        :return: True if successful
        """
        try:
            payload = {
                "message": f"Cancelled: {reason}",
                "cancelled": True,
                "cancellation_reason": reason,
            }
            await self._request("PUT", f"/api/date/{event_date_id}", json=payload)
            logger.info(f"Marked EventDate {event_date_id} as cancelled")
            return True
        except PartyMapAPIError as e:
            logger.error(f"Failed to cancel EventDate {event_date_id}: {e}")
            return False

    # ==================== Enhanced Workflow Methods ====================

    async def get_next_event_dates(self, event_id: int) -> List[dict]:
        """
        Get future/unconfirmed EventDates for an event.

        GET /api/event/{event_id}
        
        :param event_id: PartyMap event ID
        :return: List of future EventDates
        """
        try:
            event = await self.get_event(event_id)
            if not event:
                return []

            event_dates = event.get("event_dates", [])
            from datetime import datetime

            # Filter for future dates (or dates without end in past)
            future_dates = []
            now = utc_now()

            for date in event_dates:
                start = date.get("start")
                if start:
                    try:
                        date_start = datetime.fromisoformat(start.replace('Z', '+00:00'))
                        if date_start > now:
                            future_dates.append(date)
                    except (ValueError, TypeError):
                        # If can't parse, include it (better safe than sorry)
                        future_dates.append(date)
                else:
                    # No start date, include for review
                    future_dates.append(date)

            return future_dates

        except Exception as e:
            logger.error(f"Failed to get next event dates for {event_id}: {e}")
            return []

    async def update_event_partial(
        self,
        event_id: int,
        updates: dict,
        update_reasons: List[str],
        message: str = "Updated via Festival Bot"
    ) -> bool:
        """
        Update specific fields of an existing event based on update reasons.

        PUT /api/event/{event_id}

        :param event_id: PartyMap event ID
        :param updates: Dict of fields to update
        :param update_reasons: List of reasons for update ["missing_dates", "location_change", ...]
        :param message: Update message
        :return: True if successful
        """
        try:
            payload = {
                "message": f"{message} (reasons: {', '.join(update_reasons)})",
            }

            # Add all provided updates
            payload.update(updates)

            await self._request("PUT", f"/api/event/{event_id}", json=payload)
            logger.info(f"Updated PartyMap event {event_id} (reasons: {update_reasons})")
            return True

        except PartyMapAPIError as e:
            logger.error(f"Failed to update event {event_id}: {e}")
            return False

    async def add_event_date_to_existing(
        self,
        event_id: int,
        event_date: EventDateData,
        message: str = "New event date added"
    ) -> Optional[int]:
        """
        Add a new EventDate to an existing Event.

        POST /api/date/event/{event_id}

        :param event_id: Existing PartyMap event ID
        :param event_date: New event date data
        :param message: Add message
        :return: New event_date_id if successful, None otherwise
        """
        try:
            payload = {
                "date_time": {"start": event_date.start.isoformat()},
                "location": {"description": event_date.location_description},
                "message": message,
            }
            if event_date.end:
                payload["date_time"]["end"] = event_date.end.isoformat()

            # Add optional fields
            if event_date.lineup:
                payload["artists"] = [{"name": name} for name in event_date.lineup]

            if event_date.tickets:
                payload["tickets"] = [
                    {
                        "url": str(ticket.url) if ticket.url else None,
                        "description": ticket.description,
                        "price_min": float(ticket.price_min) if ticket.price_min else None,
                        "price_max": float(ticket.price_max) if ticket.price_max else None,
                        "price_currency_code": ticket.price_currency_code,
                    }
                    for ticket in event_date.tickets
                ]

            size = getattr(event_date, 'size', None) or getattr(event_date, 'expected_size', None)
            if size:
                payload["size"] = size

            response = await self._request(
                "POST",
                f"/api/date/event/{event_id}",
                json=payload
            )

            # Extract event_date_id from response
            result = response.json()
            event_date_id = result.get("id")

            logger.info(f"Added new EventDate {event_date_id} to event {event_id}")
            return event_date_id

        except PartyMapAPIError as e:
            logger.error(f"Failed to add event date to {event_id}: {e}")
            return None
