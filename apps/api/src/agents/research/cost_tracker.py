"""Cost tracking system for research agent tools."""

import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class CostBreakdown:
    """Detailed cost breakdown for research execution."""
    
    per_tool: Dict[str, int] = field(default_factory=dict)
    total_cents: int = 0
    
    def add_tool_cost(self, tool_name: str, cost_cents: int):
        """Add cost for a specific tool."""
        self.per_tool[tool_name] = self.per_tool.get(tool_name, 0) + cost_cents
        self.total_cents += cost_cents
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "per_tool": self.per_tool,
            "total_cents": self.total_cents,
            "total_dollars": round(self.total_cents / 100, 4)
        }


class CostTracker:
    """
    Track costs for research agent tool execution.
    
    Tracks per-tool costs from:
    - OpenRouter LLM calls (cost from response.usage.cost)
    - Exa searches (~$0.10 per search)
    """
    
    # Cost constants
    EXA_SEARCH_COST_CENTS = 10  # $0.10 per search
    
    def __init__(self, budget_cents: int = 50):
        """
        Initialize cost tracker.
        
        Args:
            budget_cents: Maximum budget in cents (default 50 = $0.50)
        """
        self.budget_cents = budget_cents
        self.breakdown = CostBreakdown()
        self._is_exceeded = False
    
    def track_llm_call(self, tool_name: str, response: Any) -> int:
        """
        Track cost from an LLM call using OpenRouter response.
        
        OpenRouter returns cost in the response.usage.cost field (in dollars).
        
        Args:
            tool_name: Name of the tool making the call
            response: OpenRouter response object with usage.cost
            
        Returns:
            Cost in cents for this call
        """
        try:
            # Extract cost from OpenRouter response
            # Response structure: response.usage.cost (in dollars)
            if hasattr(response, 'usage') and hasattr(response.usage, 'cost'):
                cost_dollars = response.usage.cost
            elif isinstance(response, dict) and 'usage' in response:
                cost_dollars = response['usage'].get('cost', 0)
            else:
                cost_dollars = 0
            
            # Convert to cents
            cost_cents = int(cost_dollars * 100)
            
            self.breakdown.add_tool_cost(tool_name, cost_cents)
            self._check_budget()
            
            logger.debug(f"Tracked LLM cost for {tool_name}: {cost_cents}c")
            return cost_cents
            
        except Exception as e:
            logger.warning(f"Failed to track LLM cost for {tool_name}: {e}")
            return 0
    
    def track_exa_search(self, tool_name: str = "search_alternatives") -> int:
        """
        Track cost for an Exa search.
        
        Exa costs approximately $0.10 per search.
        
        Args:
            tool_name: Name of the tool making the search
            
        Returns:
            Cost in cents for this search
        """
        self.breakdown.add_tool_cost(tool_name, self.EXA_SEARCH_COST_CENTS)
        self._check_budget()
        
        logger.debug(f"Tracked Exa search cost for {tool_name}: {self.EXA_SEARCH_COST_CENTS}c")
        return self.EXA_SEARCH_COST_CENTS
    
    def track_tool_execution(self, tool_name: str, cost_cents: int):
        """
        Track arbitrary tool execution cost.
        
        Args:
            tool_name: Name of the tool
            cost_cents: Cost in cents
        """
        self.breakdown.add_tool_cost(tool_name, cost_cents)
        self._check_budget()
    
    def _check_budget(self):
        """Check if budget has been exceeded."""
        if self.breakdown.total_cents >= self.budget_cents:
            self._is_exceeded = True
            logger.warning(
                f"Budget exceeded: {self.breakdown.total_cents}c / {self.budget_cents}c"
            )
    
    @property
    def is_exceeded(self) -> bool:
        """Check if budget has been exceeded."""
        return self._is_exceeded
    
    @property
    def remaining_cents(self) -> int:
        """Get remaining budget in cents."""
        remaining = self.budget_cents - self.breakdown.total_cents
        return max(0, remaining)
    
    def can_afford(self, estimated_cost_cents: int) -> bool:
        """
        Check if remaining budget can afford an operation.
        
        Args:
            estimated_cost_cents: Estimated cost of operation
            
        Returns:
            True if affordable, False otherwise
        """
        return (self.breakdown.total_cents + estimated_cost_cents) <= self.budget_cents
    
    def get_report(self) -> Dict[str, Any]:
        """Get full cost report."""
        return {
            **self.breakdown.to_dict(),
            "budget_cents": self.budget_cents,
            "remaining_cents": self.remaining_cents,
            "is_exceeded": self.is_exceeded,
            "utilization_percent": round(
                (self.breakdown.total_cents / self.budget_cents) * 100, 2
            ) if self.budget_cents > 0 else 0
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for state storage."""
        return self.get_report()
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CostTracker":
        """Restore from dictionary."""
        tracker = cls(budget_cents=data.get("budget_cents", 50))
        tracker.breakdown.per_tool = data.get("per_tool", {})
        tracker.breakdown.total_cents = data.get("total_cents", 0)
        tracker._is_exceeded = data.get("is_exceeded", False)
        return tracker
