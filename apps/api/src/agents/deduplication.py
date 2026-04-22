"""Deduplication logic with LLM-based matching for PartyMap festivals.

This module provides intelligent duplicate detection using LLM to compare
discovered festivals with existing PartyMap events.
"""

import json
import logging
from dataclasses import dataclass
from typing import List, Optional

from src.config import Settings
from src.partymap.client import PartyMapClient
from src.services.llm_client import LLMClient

logger = logging.getLogger(__name__)


@dataclass
class DeduplicationResult:
    """Result of deduplication check."""
    is_duplicate: bool
    confidence: float
    event_id: Optional[int] = None
    event_data: Optional[dict] = None
    update_reasons: List[str] = None
    reasoning: str = ""

    def __post_init__(self):
        if self.update_reasons is None:
            self.update_reasons = []


class DeduplicationAgent:
    """
    Agent for intelligent festival deduplication using LLM.
    
    Uses a two-stage approach:
    1. Search PartyMap for potential matches
    2. Use LLM to determine if it's a duplicate and what needs updating
    """

    UPDATE_REASONS = [
        "missing_dates",      # No future dates in PartyMap
        "dates_unconfirmed",  # Dates exist but not confirmed
        "location_change",    # Significant location change
        "lineup_released",    # New lineup information available
        "event_cancelled",    # Event was cancelled
        "description_update", # Better description available
        "media_update",       # New images/media available
        "url_update",         # Website URL changed
    ]

    def __init__(self, settings: Settings, llm: LLMClient, partymap: PartyMapClient):
        self.settings = settings
        self.llm = llm
        self.partymap = partymap

    async def check_duplicate(
        self,
        discovered_name: str,
        discovered_location: str,
        discovered_dates: Optional[str] = None,
        discovered_description: Optional[str] = None,
        clean_name: Optional[str] = None,
    ) -> DeduplicationResult:
        """
        Check if a discovered festival is a duplicate of an existing PartyMap event.
        
        :param discovered_name: Name of discovered festival
        :param discovered_location: Location of discovered festival
        :param discovered_dates: Date string (optional)
        :param discovered_description: Description (optional)
        :param clean_name: Canonical name without years/numbers
        :return: DeduplicationResult with duplicate status and update info
        """
        # Stage 1: Search PartyMap for potential matches
        search_query = clean_name if clean_name else discovered_name
        potential_matches = await self.partymap.search_events(search_query, limit=10)

        if not potential_matches:
            logger.info(f"No potential matches found for: {discovered_name}")
            return DeduplicationResult(
                is_duplicate=False,
                confidence=1.0,
                reasoning="No events found with similar name"
            )

        # Stage 2: Use LLM to evaluate each potential match
        best_match = None
        best_confidence = 0.0

        for event in potential_matches:
            result = await self._evaluate_match_with_llm(
                discovered_name=discovered_name,
                discovered_location=discovered_location,
                discovered_dates=discovered_dates,
                discovered_description=discovered_description,
                existing_event=event
            )

            if result.is_duplicate and result.confidence > best_confidence:
                best_match = result
                best_confidence = result.confidence
                best_match.event_data = event
                best_match.event_id = event.get("id")

        if best_match:
            logger.info(f"Found duplicate: {discovered_name} -> Event ID {best_match.event_id} "
                       f"(confidence: {best_match.confidence:.2f}, reasons: {best_match.update_reasons})")
            return best_match

        logger.info(f"No duplicate found for: {discovered_name}")
        return DeduplicationResult(
            is_duplicate=False,
            confidence=1.0,
            reasoning="LLM determined no matches are duplicates"
        )

    async def _evaluate_match_with_llm(
        self,
        discovered_name: str,
        discovered_location: str,
        discovered_dates: Optional[str],
        discovered_description: Optional[str],
        existing_event: dict
    ) -> DeduplicationResult:
        """
        Use LLM to evaluate if a discovered festival matches an existing event.
        
        :return: DeduplicationResult with LLM analysis
        """
        # Extract existing event info
        existing_name = existing_event.get("name", "")
        existing_location = existing_event.get("location", {}).get("description", "")

        # Get next dates info
        next_dates = existing_event.get("next_date", {})
        existing_dates = ""
        date_confirmed = True

        if next_dates:
            start = next_dates.get("start", "")
            end = next_dates.get("end", "")
            existing_dates = f"{start} to {end}" if end else start
            date_confirmed = next_dates.get("confirmed", True)

        # Build prompt
        prompt = f"""Compare this discovered festival with an existing PartyMap event and determine if they are the same festival.

DISCOVERED FESTIVAL:
- Name: {discovered_name}
- Location: {discovered_location}
- Dates: {discovered_dates or "Not specified"}
- Description: {discovered_description or "Not provided"}

EXISTING PARTYMAP EVENT:
- Name: {existing_name}
- Location: {existing_location}
- Next Dates: {existing_dates or "No future dates"}
- Dates Confirmed: {date_confirmed}

Analyze and answer:
1. Is this the same festival? Consider name similarity, location, and overall context.
2. What is your confidence level (0.0 to 1.0)?
3. If it is the same, what information needs updating?
   - "missing_dates" - if PartyMap has no future dates
   - "dates_unconfirmed" - if dates exist but aren't confirmed
   - "location_change" - if location is significantly different
   - "lineup_released" - if there's new lineup information
   - "event_cancelled" - if the event was cancelled
   - "description_update" - if description can be improved
   - "media_update" - if new images/media available
   - "url_update" - if website URL changed

Return ONLY a JSON object in this format:
{{
    "is_duplicate": true/false,
    "confidence": 0.95,
    "update_reasons": ["missing_dates", "description_update"],
    "reasoning": "Brief explanation of your decision"
}}"""

        try:
            response = await self.llm.chat_completion(
                messages=[
                    {
                        "role": "system",
                        "content": "You are a festival deduplication specialist. Compare festivals carefully and provide accurate duplicate detection."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                response_format={"type": "json_object"},
                temperature=0.1  # Low temperature for consistent results
            )

            result_data = json.loads(response)

            return DeduplicationResult(
                is_duplicate=result_data.get("is_duplicate", False),
                confidence=result_data.get("confidence", 0.0),
                update_reasons=result_data.get("update_reasons", []),
                reasoning=result_data.get("reasoning", "")
            )

        except Exception as e:
            logger.error(f"LLM deduplication evaluation failed: {e}")
            # Default to not duplicate on error
            return DeduplicationResult(
                is_duplicate=False,
                confidence=0.0,
                reasoning=f"Error during evaluation: {str(e)}"
            )

    async def batch_check_duplicates(
        self,
        festivals: List[dict],
        progress_callback: Optional[callable] = None
    ) -> List[DeduplicationResult]:
        """
        Check duplicates for multiple festivals in batch.
        
        :param festivals: List of festival dicts with name, location, etc.
        :param progress_callback: Optional callback(current, total)
        :return: List of DeduplicationResults
        """
        results = []
        total = len(festivals)

        for idx, festival in enumerate(festivals):
            result = await self.check_duplicate(
                discovered_name=festival.get("name", ""),
                discovered_location=festival.get("location", ""),
                discovered_dates=festival.get("dates"),
                discovered_description=festival.get("description"),
                clean_name=festival.get("clean_name")
            )
            results.append(result)

            if progress_callback:
                await progress_callback(idx + 1, total)

        return results
