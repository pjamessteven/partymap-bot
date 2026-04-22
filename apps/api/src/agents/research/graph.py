"""Research agent graph definition."""

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from src.agents.research.state import ResearchState
from src.agents.research.nodes import planner_node, tools_node, evaluator_node


def create_research_graph(checkpointer=None):
    """Create and compile the research agent graph."""

    # Build graph
    builder = StateGraph(ResearchState)

    # Add nodes
    builder.add_node("planner", planner_node)
    builder.add_node("tools", tools_node)
    builder.add_node("evaluator", evaluator_node)

    # Define edges
    builder.add_edge(START, "planner")
    builder.add_edge("planner", "tools")
    builder.add_edge("tools", "evaluator")

    # Conditional: complete or continue
    def should_continue(state: ResearchState):
        if state.final_result:
            return END
        if state.iteration >= state.max_iterations:
            return END
        return "planner"

    builder.add_conditional_edges(
        "evaluator", should_continue, {END: END, "planner": "planner"}
    )

    # Use Postgres checkpointer for persistence across restarts.
    # Falls back to MemorySaver if Postgres is unavailable.
    if checkpointer is None:
        try:
            from src.core.database import get_postgres_checkpointer
            checkpointer = get_postgres_checkpointer()
        except Exception:
            checkpointer = MemorySaver()

    return builder.compile(checkpointer=checkpointer)


# Global instance
_research_graph = None


def get_research_graph():
    """Get or create singleton research graph."""
    global _research_graph
    if _research_graph is None:
        _research_graph = create_research_graph()
    return _research_graph
