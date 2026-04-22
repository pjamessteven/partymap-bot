"""Refresh agent graph definition."""

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from src.agents.refresh.nodes import evaluate_node, research_node, search_node
from src.agents.refresh.state import RefreshState


def create_refresh_graph(checkpointer=None):
    """Create and compile the refresh agent graph."""

    # Build graph
    builder = StateGraph(RefreshState)

    # Add nodes
    builder.add_node("search", search_node)
    builder.add_node("research", research_node)
    builder.add_node("evaluate", evaluate_node)

    # Define edges
    builder.add_edge(START, "search")
    builder.add_edge("search", "research")
    builder.add_edge("research", "evaluate")

    # Always end after evaluate
    builder.add_edge("evaluate", END)

    # Use memory checkpointer
    if checkpointer is None:
        checkpointer = MemorySaver()

    return builder.compile(checkpointer=checkpointer)


# Global instance
_refresh_graph = None


def get_refresh_graph():
    """Get or create singleton refresh graph."""
    global _refresh_graph
    if _refresh_graph is None:
        _refresh_graph = create_refresh_graph()
    return _refresh_graph
