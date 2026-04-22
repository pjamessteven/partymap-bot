"""Schema validator for PartyMap API requirements."""

import logging
from typing import Dict, List, Tuple, Any, Optional
from urllib.parse import urlparse

from src.core.schemas import FestivalData

logger = logging.getLogger(__name__)


class PartyMapSchemaValidator:
    """Validator that checks research data against PartyMap schema requirements."""
    
    # Required fields for PartyMap API (addEvent.schema.json)
    REQUIRED_FIELDS = {
        "name": {
            "description": "Event name",
            "validator": lambda d: bool(d.get("name") and len(str(d.get("name", "")).strip()) > 0)
        },
        "description": {
            "description": "Brief event description",
            "validator": lambda d: bool(d.get("description") and len(str(d.get("description", "")).strip()) > 10)
        },
        "logo": {
            "description": "Logo/cover image URL",
            "validator": lambda d: bool(d.get("logo_url") and self._is_valid_url(d.get("logo_url")))
        },
        "url": {
            "description": "Event website URL",
            "validator": lambda d: bool(d.get("website_url") and self._is_valid_url(d.get("website_url")))
        },
        "start_date": {
            "description": "Event start date",
            "validator": lambda d: bool(
                d.get("event_dates") and 
                len(d.get("event_dates", [])) > 0 and
                d.get("event_dates", [{}])[0].get("start")
            )
        },
        "tags": {
            "description": "List of event tags",
            "validator": lambda d: bool(d.get("tags") and len(d.get("tags", [])) > 0)
        }
    }
    
    # Field to failure reason mapping
    FIELD_TO_REASON = {
        "name": "not_found",
        "description": "description",
        "logo": "logo",
        "url": "url",
        "start_date": "dates",
        "tags": "classification"
    }
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def validate(self, research_data: Dict[str, Any]) -> "ValidationResult":
        """Validate research data against PartyMap schema requirements."""
        missing_fields = []
        
        # Check each required field
        for field_name, field_config in self.REQUIRED_FIELDS.items():
            if not field_config["validator"](research_data):
                missing_fields.append(field_name)
        
        # Calculate completeness score
        completeness_score = 1.0 - (len(missing_fields) / len(self.REQUIRED_FIELDS))
        
        # Determine failure reason
        failure_reason = self._determine_failure_reason(missing_fields, research_data)
        
        # Determine if data is valid (100% complete)
        is_valid = completeness_score == 1.0
        
        # Import ValidationResult here to avoid circular imports
        from src.core.schemas import ValidationResult
        
        return ValidationResult(
            is_valid=is_valid,
            missing_fields=missing_fields,
            failure_reason=failure_reason,
            completeness_score=completeness_score
        )
    
    def _determine_failure_reason(self, missing_fields: List[str], research_data: Dict[str, Any]) -> str:
        """Map missing fields to failure reason categories."""
        
        if not research_data or not research_data.get("name"):
            return "not_found"
        
        # Check for specific missing fields
        for missing_field in missing_fields:
            reason = self.FIELD_TO_REASON.get(missing_field, "unknown")
            return reason
        
        # If no missing fields but still here, check for empty data
        if not research_data or all(not v for v in research_data.values() if not isinstance(v, (list, dict))):
            return "not_found"
        
        return "unknown"
    
    def _is_valid_url(self, url: Optional[str]) -> bool:
        """Check if a URL is valid."""
        if not url:
            return False
        
        try:
            result = urlparse(str(url))
            return all([result.scheme, result.netloc])
        except:
            return False
    
    def generate_failure_message(self, failure_reason: str, missing_fields: List[str]) -> str:
        """Generate human-readable failure message."""
        messages = {
            "dates": "Dates for this festival haven't been released yet",
            "not_found": "A festival with this name couldn't be found",
            "logo": "Could not find a suitable logo/cover image",
            "description": "Insufficient information found to create description",
            "url": "Festival website URL could not be found or is invalid",
            "location": "Location information could not be found",
            "classification": "Could not determine festival tags/category",
            "unknown": "Research failed for unknown reasons"
        }
        
        if failure_reason in messages:
            return messages[failure_reason]
        
        # Default message with missing fields
        if missing_fields:
            return f"Missing required fields: {', '.join(missing_fields)}"
        
        return "Research failed"
    
    def validate_festival_data(self, festival_data: FestivalData) -> "ValidationResult":
        """Convenience method to validate FestivalData object."""
        # Convert FestivalData to dict for validation
        data_dict = festival_data.model_dump() if hasattr(festival_data, 'model_dump') else dict(festival_data)
        return self.validate(data_dict)