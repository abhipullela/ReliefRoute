"""LangGraph state machine orchestration for ReliefRoute.

Phase 1 pipeline:
    START -> MONITOR -> ASSESS -> PLAN -> VALIDATE -> [SUCCESS | NEEDS_INFO | FAILURE] -> END

Phase 2 extension:
    planning_success -> await_approval -> APPROVED?
        YES -> dispatch -> DISPATCHED? -> verify -> COMPLETED | REPLAN -> replan -> monitor (cycle)
        NO  -> approval_rejected (REJECTED) | approval_pending (AWAITING_APPROVAL)
    dispatch failure -> dispatch_failed -> END
"""

from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from agent.nodes import (
    approval_pending_node,
    assess_node,
    await_approval_node,
    completed_node,
    dispatch_failed_node,
    dispatch_node,
    execute_node,
    monitor_node,
    needs_info_node,
    plan_node,
    planning_failure_node,
    planning_success_node,
    rejected_node,
    replan_node,
    route_after_approval,
    route_after_dispatch,
    route_after_validation,
    route_after_verify,
    validate_node,
    verify_node,
)
from agent.services import AgentServices
from agent.state import AgentState


def build_agent_graph(services: AgentServices | None = None) -> StateGraph:
    """Construct the LangGraph StateGraph for ReliefRoute Phase 1 + 2.

    Args:
        services: Optional dependency injection container providing external services.
    """
    workflow = StateGraph(AgentState)

    # ------------------------------------------------------------------
    # Bind node functions with injected services
    # ------------------------------------------------------------------
    async def _monitor(state: AgentState, config: RunnableConfig | None = None) -> dict[str, Any]:
        return await monitor_node(state, config, services=services)

    async def _assess(state: AgentState, config: RunnableConfig | None = None) -> dict[str, Any]:
        return await assess_node(state, config, services=services)

    async def _plan(state: AgentState, config: RunnableConfig | None = None) -> dict[str, Any]:
        return await plan_node(state, config, services=services)

    def _validate(state: AgentState, config: RunnableConfig | None = None) -> dict[str, Any]:
        return validate_node(state, config)

    # Phase 2 bound nodes
    async def _await_approval(state: AgentState, config: RunnableConfig | None = None) -> dict[str, Any]:
        return await await_approval_node(state, config, services=services)

    async def _dispatch(state: AgentState, config: RunnableConfig | None = None) -> dict[str, Any]:
        return await dispatch_node(state, config, services=services)

    async def _verify(state: AgentState, config: RunnableConfig | None = None) -> dict[str, Any]:
        return await verify_node(state, config, services=services)

    async def _replan(state: AgentState, config: RunnableConfig | None = None) -> dict[str, Any]:
        return await replan_node(state, config, services=services)

    # ------------------------------------------------------------------
    # Register Phase 1 pipeline nodes
    # ------------------------------------------------------------------
    workflow.add_node("monitor", _monitor)
    workflow.add_node("assess", _assess)
    workflow.add_node("plan", _plan)
    workflow.add_node("validate", _validate)

    # Terminal decision outcome nodes (Phase 1)
    workflow.add_node("planning_success", planning_success_node)
    workflow.add_node("needs_information", needs_info_node)
    workflow.add_node("planning_failure", planning_failure_node)

    # ------------------------------------------------------------------
    # Register Phase 2 nodes
    # ------------------------------------------------------------------
    workflow.add_node("await_approval", _await_approval)
    workflow.add_node("dispatch", _dispatch)
    workflow.add_node("verify", _verify)
    workflow.add_node("replan", _replan)

    # Phase 2 terminal nodes
    workflow.add_node("approval_pending", approval_pending_node)
    workflow.add_node("approval_rejected", rejected_node)
    workflow.add_node("dispatch_failed", dispatch_failed_node)
    workflow.add_node("completed", completed_node)

    # Legacy Phase 1 stub node (kept for backward-compatibility)
    workflow.add_node("execute", execute_node)

    # ------------------------------------------------------------------
    # Phase 1 primary edges: START -> MONITOR -> ASSESS -> PLAN -> VALIDATE
    # ------------------------------------------------------------------
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

    # Phase 1 terminal edges
    workflow.add_edge("needs_information", END)
    workflow.add_edge("planning_failure", END)

    # ------------------------------------------------------------------
    # Phase 2: planning_success -> await_approval -> dispatch -> verify
    # ------------------------------------------------------------------
    workflow.add_edge("planning_success", "await_approval")

    workflow.add_conditional_edges(
        "await_approval",
        route_after_approval,
        {
            "dispatch": "dispatch",
            "approval_pending": "approval_pending",
            "approval_rejected": "approval_rejected",
            "approval_failed": "planning_failure",
        },
    )

    # Approval terminal nodes
    workflow.add_edge("approval_pending", END)
    workflow.add_edge("approval_rejected", END)

    # Dispatch routing
    workflow.add_conditional_edges(
        "dispatch",
        route_after_dispatch,
        {
            "verify": "verify",
            "dispatch_failed": "dispatch_failed",
        },
    )

    workflow.add_edge("dispatch_failed", END)

    # Verify / replan routing
    workflow.add_conditional_edges(
        "verify",
        route_after_verify,
        {
            "completed": "completed",
            "replan": "replan",
            "verify_failed": "planning_failure",
        },
    )

    workflow.add_edge("completed", END)

    # Replan loops back to monitor for a fresh planning cycle
    workflow.add_edge("replan", "monitor")

    # Legacy execute stub
    workflow.add_edge("execute", END)

    return workflow


def create_agent_workflow(services: AgentServices | None = None) -> CompiledStateGraph:
    """Build and compile the LangGraph workflow ready for invocation."""
    graph = build_agent_graph(services)
    return graph.compile()
