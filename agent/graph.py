"""LangGraph state machine orchestration for ReliefRoute.


Connects the decision pipeline:
START -> MONITOR -> ASSESS -> PLAN -> VALIDATE -> [SUCCESS | NEEDS_INFO | FAILURE] -> END

Prepared for Phase 2:
EXECUTE and VERIFY architectural placeholders are defined and guarded.
"""

from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from agent.nodes import (
    assess_node,
    execute_node,
    monitor_node,
    needs_info_node,
    plan_node,
    planning_failure_node,
    planning_success_node,
    route_after_validation,
    validate_node,
    verify_node,
)
from agent.services import AgentServices
from agent.state import AgentState


def build_agent_graph(services: AgentServices | None = None) -> StateGraph:
    """Construct the LangGraph StateGraph for ReliefRoute Phase 1.

    Args:
        services: Optional dependency injection container providing external services.
    """
    workflow = StateGraph(AgentState)

    # Bind node functions with injected services
    async def _monitor(state: AgentState, config: RunnableConfig | None = None) -> dict[str, Any]:
        return await monitor_node(state, config, services=services)

    async def _assess(state: AgentState, config: RunnableConfig | None = None) -> dict[str, Any]:
        return await assess_node(state, config, services=services)

    async def _plan(state: AgentState, config: RunnableConfig | None = None) -> dict[str, Any]:
        return await plan_node(state, config, services=services)

    def _validate(state: AgentState, config: RunnableConfig | None = None) -> dict[str, Any]:
        return validate_node(state, config)

    # Register core pipeline nodes
    workflow.add_node("monitor", _monitor)
    workflow.add_node("assess", _assess)
    workflow.add_node("plan", _plan)
    workflow.add_node("validate", _validate)

    # Register terminal decision outcome nodes
    workflow.add_node("planning_success", planning_success_node)
    workflow.add_node("needs_information", needs_info_node)
    workflow.add_node("planning_failure", planning_failure_node)

    # Register architectural placeholder nodes for Phase 2
    workflow.add_node("execute", execute_node)
    workflow.add_node("verify", verify_node)

    # Primary workflow edges: START -> MONITOR -> ASSESS -> PLAN -> VALIDATE
    workflow.add_edge(START, "monitor")
    workflow.add_edge("monitor", "assess")
    workflow.add_edge("assess", "plan")
    workflow.add_edge("plan", "validate")

    # Conditional branching following deterministic validation
    workflow.add_conditional_edges(
        "validate",
        route_after_validation,
        {
            "planning_success": "planning_success",
            "needs_information": "needs_information",
            "planning_failure": "planning_failure",
        },
    )

    # Terminal edges to END
    workflow.add_edge("planning_success", END)
    workflow.add_edge("needs_information", END)
    workflow.add_edge("planning_failure", END)

    return workflow


def create_agent_workflow(services: AgentServices | None = None) -> CompiledStateGraph:
    """Build and compile the LangGraph workflow ready for invocation."""
    graph = build_agent_graph(services)
    return graph.compile()
