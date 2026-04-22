"""Base interface for festival discovery sources."""

from abc import ABC, abstractmethod
from typing import List

from src.core.schemas import DiscoveredFestival, ResearchedFestival


class SourceInterface(ABC):
    """Abstract base class for festival discovery sources."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Source name identifier."""
        pass

    @abstractmethod
    async def discover(self) -> List[DiscoveredFestival]:
        """
        Discover festivals from this source.

        Returns:
            List of discovered festivals (raw data)
        """
        pass

    @abstractmethod
    async def research(self, discovered: DiscoveredFestival) -> ResearchedFestival:
        """
        Research a discovered festival to enrich with full details.

        Args:
            discovered: Discovered festival from discover()

        Returns:
            Fully researched festival with all details
        """
        pass

    async def health_check(self) -> bool:
        """
        Check if source is available and healthy.

        Returns:
            True if source is operational
        """
        return True
