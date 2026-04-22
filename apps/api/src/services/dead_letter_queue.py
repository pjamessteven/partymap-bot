"""Dead Letter Queue for failed festivals.

The DLQ quarantines festivals that have failed repeatedly and cannot be processed.
Quarantined festivals are kept for 30 days and can be manually retried.

Features:
- Automatic quarantine after max retries
- Manual retry with validation
- 30-day retention for quarantined items
- Bulk operations for cleanup
"""

import logging
from datetime import datetime, timedelta
from src.utils.utc_now import utc_now
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select, update, delete, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models import Festival, FestivalState
from src.core.schemas import FestivalData
from src.core.validators import validate_festival_for_sync
from src.core.error_classification import ErrorCategory

logger = logging.getLogger(__name__)

# Configuration
QUARANTINE_RETENTION_DAYS = 30
MAX_RETRIES_BEFORE_QUARANTINE = 5


class DeadLetterQueue:
    """Dead Letter Queue for quarantining failed festivals."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def quarantine(
        self,
        festival_id: UUID,
        reason: str,
        error_category: Optional[ErrorCategory] = None,
        error_context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Move a festival to quarantine.
        
        :param festival_id: Festival ID to quarantine
        :param reason: Reason for quarantine
        :param error_category: Category of error that caused quarantine
        :param error_context: Additional error context
        :return: True if quarantined successfully
        """
        try:
            now = utc_now()
            
            result = await self.db.execute(
                update(Festival)
                .where(Festival.id == festival_id)
                .values(
                    state=FestivalState.QUARANTINED.value,
                    quarantined_at=now,
                    quarantine_reason=reason,
                    error_category=error_category.value if error_category else None,
                    error_context=error_context,
                    max_retries_reached=True,
                    updated_at=now,
                )
            )
            
            await self.db.commit()
            
            if result.rowcount > 0:
                logger.warning(
                    f"Festival {festival_id} quarantined: {reason}"
                )
                return True
            else:
                logger.error(f"Festival {festival_id} not found for quarantine")
                return False
                
        except Exception as e:
            logger.error(f"Failed to quarantine festival {festival_id}: {e}")
            await self.db.rollback()
            return False
    
    async def should_quarantine(self, festival_id: UUID) -> bool:
        """
        Check if a festival should be quarantined based on retry count.
        
        :param festival_id: Festival ID to check
        :return: True if should quarantine
        """
        result = await self.db.execute(
            select(Festival.retry_count, Festival.max_retries_reached)
            .where(Festival.id == festival_id)
        )
        row = result.first()
        
        if not row:
            return False
        
        retry_count, max_reached = row
        
        # Quarantine if max retries reached or retry count exceeds threshold
        if max_reached or (retry_count and retry_count >= MAX_RETRIES_BEFORE_QUARANTINE):
            return True
        
        return False
    
    async def retry(
        self,
        festival_id: UUID,
        force: bool = False,
        new_state: Optional[FestivalState] = None,
    ) -> Dict[str, Any]:
        """
        Retry a quarantined festival.
        
        :param festival_id: Festival ID to retry
        :param force: Force retry even if validation fails
        :param new_state: State to transition to (default: NEEDS_RESEARCH_NEW)
        :return: Result dict with success status and message
        """
        try:
            # Get festival data
            result = await self.db.execute(
                select(Festival).where(Festival.id == festival_id)
            )
            festival = result.scalar_one_or_none()
            
            if not festival:
                return {
                    "success": False,
                    "message": "Festival not found",
                }
            
            if festival.state != FestivalState.QUARANTINED.value and not force:
                return {
                    "success": False,
                    "message": f"Festival is not quarantined (current state: {festival.state})",
                }
            
            # Validate if we have research data
            validation_result = None
            if festival.research_data:
                try:
                    festival_data = FestivalData(**festival.research_data)
                    validation_result = validate_festival_for_sync(festival_data)
                    
                    if not validation_result.is_valid and not force:
                        return {
                            "success": False,
                            "message": "Validation failed",
                            "validation": validation_result.dict(),
                        }
                except Exception as e:
                    if not force:
                        return {
                            "success": False,
                            "message": f"Failed to validate festival data: {e}",
                        }
            
            # Reset retry count and state
            now = utc_now()
            target_state = (new_state.value if new_state else None) or FestivalState.NEEDS_RESEARCH_NEW.value
            
            await self.db.execute(
                update(Festival)
                .where(Festival.id == festival_id)
                .values(
                    state=target_state,
                    retry_count=0,
                    max_retries_reached=False,
                    quarantined_at=None,
                    quarantine_reason=None,
                    error_category=None,
                    error_context=None,
                    last_error=None,
                    failure_reason=None,
                    failure_message=None,
                    first_error_at=None,
                    last_retry_at=now,
                    updated_at=now,
                )
            )
            
            await self.db.commit()
            
            logger.info(f"Festival {festival_id} retried from quarantine, new state: {target_state}")
            
            return {
                "success": True,
                "message": f"Festival moved to {target_state.value}",
                "new_state": target_state.value,
                "validation": validation_result.dict() if validation_result else None,
            }
            
        except Exception as e:
            logger.error(f"Failed to retry festival {festival_id}: {e}")
            await self.db.rollback()
            return {
                "success": False,
                "message": f"Error retrying festival: {e}",
            }
    
    async def get_quarantined(
        self,
        limit: int = 50,
        offset: int = 0,
        error_category: Optional[str] = None,
    ) -> List[Festival]:
        """
        Get quarantined festivals.
        
        :param limit: Max results
        :param offset: Pagination offset
        :param error_category: Filter by error category
        :return: List of quarantined festivals
        """
        query = select(Festival).where(Festival.state == FestivalState.QUARANTINED.value)
        
        if error_category:
            query = query.where(Festival.error_category == error_category)
        
        query = query.order_by(Festival.quarantined_at.desc())
        query = query.limit(limit).offset(offset)
        
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def get_quarantined_count(self, error_category: Optional[str] = None) -> int:
        """Get count of quarantined festivals."""
        query = select(Festival).where(Festival.state == FestivalState.QUARANTINED.value)
        
        if error_category:
            query = query.where(Festival.error_category == error_category)
        
        result = await self.db.execute(query)
        return len(result.scalars().all())
    
    async def cleanup_expired(self) -> int:
        """
        Remove festivals that have been quarantined for more than 30 days.
        
        :return: Number of festivals removed
        """
        cutoff = utc_now() - timedelta(days=QUARANTINE_RETENTION_DAYS)
        
        try:
            result = await self.db.execute(
                delete(Festival)
                .where(
                    and_(
                        Festival.state == FestivalState.QUARANTINED.value,
                        Festival.quarantined_at < cutoff,
                    )
                )
            )
            
            await self.db.commit()
            
            count = result.rowcount
            if count > 0:
                logger.info(f"Cleaned up {count} expired quarantined festivals")
            
            return count
            
        except Exception as e:
            logger.error(f"Failed to cleanup expired quarantined festivals: {e}")
            await self.db.rollback()
            return 0
    
    async def bulk_retry(
        self,
        festival_ids: List[UUID],
        force: bool = False,
        new_state: Optional[FestivalState] = None,
    ) -> Dict[str, Any]:
        """
        Retry multiple quarantined festivals.
        
        :param festival_ids: List of festival IDs to retry
        :param force: Force retry even if validation fails
        :param new_state: State to transition to
        :return: Summary of results
        """
        results = {
            "total": len(festival_ids),
            "successful": 0,
            "failed": 0,
            "details": [],
        }
        
        for festival_id in festival_ids:
            result = await self.retry(festival_id, force=force, new_state=new_state)
            
            if result["success"]:
                results["successful"] += 1
            else:
                results["failed"] += 1
            
            results["details"].append({
                "festival_id": str(festival_id),
                "success": result["success"],
                "message": result["message"],
            })
        
        return results
    
    async def get_quarantine_stats(self) -> Dict[str, Any]:
        """
        Get statistics about quarantined festivals.
        
        :return: Statistics dict
        """
        # Get counts by error category
        result = await self.db.execute(
            select(Festival.error_category, Festival.id)
            .where(Festival.state == FestivalState.QUARANTINED.value)
        )
        rows = result.all()
        
        by_category = {}
        for row in rows:
            category = row.error_category or "unknown"
            by_category[category] = by_category.get(category, 0) + 1
        
        # Get total count
        total = len(rows)
        
        # Get expiring soon (within 7 days)
        week_from_now = utc_now() + timedelta(days=7)
        expiring_result = await self.db.execute(
            select(Festival.id)
            .where(
                and_(
                    Festival.state == FestivalState.QUARANTINED.value,
                    Festival.quarantined_at < week_from_now - timedelta(days=QUARANTINE_RETENTION_DAYS - 7),
                )
            )
        )
        expiring_soon = len(expiring_result.scalars().all())
        
        return {
            "total_quarantined": total,
            "by_category": by_category,
            "expiring_soon": expiring_soon,
            "retention_days": QUARANTINE_RETENTION_DAYS,
        }


async def check_and_quarantine(
    db: AsyncSession,
    festival_id: UUID,
    error_message: str,
    error_category: Optional[ErrorCategory] = None,
    error_context: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Check if festival should be quarantined and quarantine if needed.
    
    Convenience function for use in error handlers.
    
    :param db: Database session
    :param festival_id: Festival ID
    :param error_message: Error message
    :param error_category: Error category
    :param error_context: Error context
    :return: True if festival was quarantined
    """
    dlq = DeadLetterQueue(db)
    
    if await dlq.should_quarantine(festival_id):
        return await dlq.quarantine(
            festival_id=festival_id,
            reason=error_message,
            error_category=error_category,
            error_context=error_context,
        )
    
    return False