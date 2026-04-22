"""Pre-flight validators for PartyMap sync."""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from src.core.schemas import FestivalData, ValidationResult

logger = logging.getLogger(__name__)


class PartyMapSyncValidator:
    """
    Pre-flight validator for PartyMap sync operations.
    
    Validates festival data against PartyMap API requirements before attempting sync.
    This prevents wasting API calls on data that will definitely fail.
    
    PartyMap Required Fields (from addEvent.schema.json):
    - name: string
    - description: string
    - full_description: string
    - date_time: {start, end}
    - location: {description}
    - logo: {url}
    """
    
    # PartyMap API requirements
    REQUIRED_FIELDS = ["name", "description", "full_description", "event_dates"]
    MIN_NAME_LENGTH = 2
    MIN_DESCRIPTION_LENGTH = 10
    MIN_FULL_DESCRIPTION_LENGTH = 20
    MIN_LOCATION_LENGTH = 3
    MAX_TAGS = 5
    
    def __init__(self):
        self.errors: List[Dict[str, Any]] = []
        self.warnings: List[Dict[str, Any]] = []
        self.missing_fields: List[str] = []
    
    def validate(self, festival_data: FestivalData) -> ValidationResult:
        """
        Run all validations and return comprehensive result.
        
        :param festival_data: Festival data to validate
        :return: ValidationResult with status, errors, warnings, and completeness score
        """
        self.errors = []
        self.warnings = []
        self.missing_fields = []
        
        # Run all validation checks
        self._validate_basic_info(festival_data)
        self._validate_event_dates(festival_data)
        self._validate_media(festival_data)
        self._validate_classification(festival_data)
        self._validate_optional_fields(festival_data)
        
        # Calculate completeness score
        completeness_score = self._calculate_completeness(festival_data)
        
        # Determine final status
        if self.errors:
            status = "invalid"
            is_valid = False
        elif self.warnings or completeness_score < 0.8:
            status = "needs_review"
            is_valid = False
        else:
            status = "ready"
            is_valid = True
        
        return ValidationResult(
            is_valid=is_valid,
            status=status,
            completeness_score=round(completeness_score, 2),
            errors=self.errors,
            warnings=self.warnings,
            missing_fields=self.missing_fields
        )
    
    def _validate_basic_info(self, data: FestivalData) -> None:
        """Validate basic festival information."""
        # Name validation
        if not data.name:
            self.errors.append({
                "field": "name",
                "message": "Name is required",
                "severity": "error"
            })
            self.missing_fields.append("name")
        elif len(data.name.strip()) < self.MIN_NAME_LENGTH:
            self.errors.append({
                "field": "name",
                "message": f"Name must be at least {self.MIN_NAME_LENGTH} characters",
                "severity": "error"
            })
        elif len(data.name) > 500:
            self.warnings.append({
                "field": "name",
                "message": "Name exceeds 500 characters, will be truncated",
                "severity": "warning"
            })
        
        # Description validation
        if not data.description:
            self.errors.append({
                "field": "description",
                "message": "Description is required",
                "severity": "error"
            })
            self.missing_fields.append("description")
        elif len(data.description.strip()) < self.MIN_DESCRIPTION_LENGTH:
            self.errors.append({
                "field": "description",
                "message": f"Description must be at least {self.MIN_DESCRIPTION_LENGTH} characters",
                "severity": "error"
            })
        
        # Full description validation
        if not data.full_description:
            self.errors.append({
                "field": "full_description",
                "message": "Full description is required",
                "severity": "error"
            })
            self.missing_fields.append("full_description")
        elif len(data.full_description.strip()) < self.MIN_FULL_DESCRIPTION_LENGTH:
            self.errors.append({
                "field": "full_description",
                "message": f"Full description must be at least {self.MIN_FULL_DESCRIPTION_LENGTH} characters",
                "severity": "error"
            })
        
        # URL validation (optional but recommended)
        if data.website_url:
            if not self._is_valid_url(str(data.website_url)):
                self.warnings.append({
                    "field": "website_url",
                    "message": "Website URL appears to be invalid",
                    "severity": "warning"
                })
        
        if data.youtube_url:
            if not self._is_valid_url(str(data.youtube_url)):
                self.warnings.append({
                    "field": "youtube_url",
                    "message": "YouTube URL appears to be invalid",
                    "severity": "warning"
                })
    
    def _validate_event_dates(self, data: FestivalData) -> None:
        """Validate event dates."""
        if not data.event_dates:
            self.errors.append({
                "field": "event_dates",
                "message": "At least one event date is required",
                "severity": "error"
            })
            self.missing_fields.append("event_dates")
            return
        
        now = datetime.now()
        
        for idx, event_date in enumerate(data.event_dates):
            prefix = f"event_dates[{idx}]"
            
            # Start date validation
            if not event_date.start:
                self.errors.append({
                    "field": f"{prefix}.start",
                    "message": "Start date is required",
                    "severity": "error"
                })
                if "event_dates" not in self.missing_fields:
                    self.missing_fields.append("event_dates")
            else:
                # Check date is in the future (with 1 day grace period for timezone issues)
                if event_date.start < now - timedelta(days=1):
                    self.warnings.append({
                        "field": f"{prefix}.start",
                        "message": "Event date is in the past",
                        "severity": "warning"
                    })
            
            # End date validation
            if event_date.end:
                if event_date.start and event_date.end <= event_date.start:
                    self.errors.append({
                        "field": f"{prefix}.end",
                        "message": "End date must be after start date",
                        "severity": "error"
                    })
                
                # Check if event is too long (more than 30 days)
                if event_date.start and (event_date.end - event_date.start).days > 30:
                    self.warnings.append({
                        "field": f"{prefix}.end",
                        "message": "Event duration exceeds 30 days, please verify",
                        "severity": "warning"
                    })
            
            # Location validation
            if not event_date.location_description:
                self.errors.append({
                    "field": f"{prefix}.location_description",
                    "message": "Location description is required",
                    "severity": "error"
                })
                if "location" not in self.missing_fields:
                    self.missing_fields.append("location")
            elif len(event_date.location_description.strip()) < self.MIN_LOCATION_LENGTH:
                self.errors.append({
                    "field": f"{prefix}.location_description",
                    "message": f"Location must be at least {self.MIN_LOCATION_LENGTH} characters",
                    "severity": "error"
                })
            
            # Ticket validation
            if event_date.tickets:
                for t_idx, ticket in enumerate(event_date.tickets):
                    if ticket.price_min is not None and ticket.price_max is not None:
                        if ticket.price_max < ticket.price_min:
                            self.errors.append({
                                "field": f"{prefix}.tickets[{t_idx}].price_max",
                                "message": "Maximum price must be >= minimum price",
                                "severity": "error"
                            })
            
            # Lineup validation
            if event_date.lineup:
                # Check for duplicates (case-insensitive)
                lineup_lower = [a.lower().strip() for a in event_date.lineup if a.strip()]
                duplicates = set([a for a in lineup_lower if lineup_lower.count(a) > 1])
                if duplicates:
                    self.warnings.append({
                        "field": f"{prefix}.lineup",
                        "message": f"Duplicate artists found: {', '.join(duplicates)}",
                        "severity": "warning"
                    })
    
    def _validate_media(self, data: FestivalData) -> None:
        """Validate media items."""
        # Logo is required per PartyMap schema
        if not data.logo_url:
            self.errors.append({
                "field": "logo_url",
                "message": "Logo image is required for PartyMap sync",
                "severity": "error"
            })
            self.missing_fields.append("logo_url")
        else:
            # Validate logo URL format
            if not self._is_valid_url(str(data.logo_url)):
                self.errors.append({
                    "field": "logo_url",
                    "message": "Logo URL is not a valid URL",
                    "severity": "error"
                })
        
        # Validate media items
        if data.media_items:
            for idx, media in enumerate(data.media_items):
                if not self._is_valid_url(str(media.url)):
                    self.warnings.append({
                        "field": f"media_items[{idx}].url",
                        "message": f"Invalid URL for media item {idx + 1}",
                        "severity": "warning"
                    })
                
                # Check caption length
                if media.caption and len(media.caption) > 500:
                    self.warnings.append({
                        "field": f"media_items[{idx}].caption",
                        "message": "Caption exceeds 500 characters, may be truncated",
                        "severity": "warning"
                    })
    
    def _validate_classification(self, data: FestivalData) -> None:
        """Validate tags and category."""
        if not data.tags:
            self.warnings.append({
                "field": "tags",
                "message": "No tags assigned, consider adding for better discoverability",
                "severity": "warning"
            })
        else:
            if len(data.tags) > self.MAX_TAGS:
                self.warnings.append({
                    "field": "tags",
                    "message": f"Too many tags ({len(data.tags)}), only first {self.MAX_TAGS} will be used",
                    "severity": "warning"
                })
            
            # Check for empty or very short tags
            short_tags = [t for t in data.tags if len(t.strip()) < 2]
            if short_tags:
                self.warnings.append({
                    "field": "tags",
                    "message": f"Very short tags found: {short_tags}",
                    "severity": "warning"
                })
    
    def _validate_optional_fields(self, data: FestivalData) -> None:
        """Validate optional fields that improve data quality."""
        # Recurrence rule validation
        if data.is_recurring and data.rrule:
            if data.rrule.recurringType not in range(4):  # 0-3
                self.warnings.append({
                    "field": "rrule.recurringType",
                    "message": "Invalid recurrence type (must be 0-3)",
                    "severity": "warning"
                })
            
            if data.rrule.separationCount < 0:
                self.warnings.append({
                    "field": "rrule.separationCount",
                    "message": "Separation count must be >= 0",
                    "severity": "warning"
                })
    
    def _calculate_completeness(self, data: FestivalData) -> float:
        """Calculate data completeness score (0.0 - 1.0)."""
        required_fields = {
            "name": bool(data.name and len(data.name.strip()) >= self.MIN_NAME_LENGTH),
            "description": bool(data.description and len(data.description.strip()) >= self.MIN_DESCRIPTION_LENGTH),
            "full_description": bool(data.full_description and len(data.full_description.strip()) >= self.MIN_FULL_DESCRIPTION_LENGTH),
            "event_dates": bool(data.event_dates),
            "logo": bool(data.logo_url),
        }
        
        optional_fields = {
            "website_url": bool(data.website_url),
            "youtube_url": bool(data.youtube_url),
            "media_items": bool(data.media_items and len(data.media_items) > 0),
            "tags": bool(data.tags and len(data.tags) > 0),
            "location_country": any(ed.location_country for ed in data.event_dates) if data.event_dates else False,
            "coordinates": any(ed.location_lat and ed.location_lng for ed in data.event_dates) if data.event_dates else False,
            "tickets": any(ed.tickets for ed in data.event_dates) if data.event_dates else False,
            "lineup": any(ed.lineup for ed in data.event_dates) if data.event_dates else False,
        }
        
        required_score = sum(required_fields.values()) / len(required_fields)
        optional_score = sum(optional_fields.values()) / len(optional_fields)
        
        # Weight: 70% required, 30% optional
        return (required_score * 0.7) + (optional_score * 0.3)
    
    def _is_valid_url(self, url: str) -> bool:
        """Basic URL validation."""
        try:
            result = urlparse(url)
            return all([result.scheme in ("http", "https"), result.netloc])
        except Exception:
            return False
    
    def validate_for_create(self, data: FestivalData) -> ValidationResult:
        """
        Validate specifically for creating a new event.
        More strict than update validation.
        """
        result = self.validate(data)
        
        # Additional checks for new events
        if not data.event_dates:
            self.errors.append({
                "field": "event_dates",
                "message": "New events must have at least one date",
                "severity": "error"
            })
        
        return result
    
    def validate_for_update(self, data: FestivalData) -> ValidationResult:
        """
        Validate for updating an existing event.
        Less strict - only validates provided fields.
        """
        result = self.validate(data)
        
        # For updates, we can be more lenient with some fields
        # Remove errors for fields that weren't provided
        if not data.name:
            self.errors = [e for e in self.errors if e["field"] != "name"]
        if not data.description:
            self.errors = [e for e in self.errors if e["field"] != "description"]
        
        # Recalculate status
        if self.errors:
            result.status = "invalid"
            result.is_valid = False
        elif self.warnings:
            result.status = "needs_review"
            result.is_valid = False
        else:
            result.status = "ready"
            result.is_valid = True
        
        return result


def validate_festival_for_sync(festival_data: FestivalData) -> ValidationResult:
    """
    Convenience function for quick validation.
    
    :param festival_data: Festival data to validate
    :return: ValidationResult
    """
    validator = PartyMapSyncValidator()
    return validator.validate(festival_data)