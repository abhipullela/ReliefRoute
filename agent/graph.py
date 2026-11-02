"""LangGraph state machine orchestration for ReliefRoute."""

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
    extract_report_node,
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
    validate_report_node,
)
from agent.services import AgentServices
from agent.state import AgentState


def route_after_report_validation(state: AgentState) -> str:
    if state.get("workflow_status") == "FAILED":
        return "failed"

    validation = state.get("report_validation")

    if validation is None or not validation.structurally_valid:
        return "needs_information"

    return "monitor"

def route_after_start(state: AgentState) -> str:
    """Choose the correct starting node based on available input."""

    if state.get("citizen_report") is not None:
        return "extract_report"

    if state.get("incident") is not None:
        return "monitor"

    return "needs_information"

def build_agent_graph(
    services: AgentServices | None = None,
) -> StateGraph:
    """Construct the ReliefRoute Phase 1, Phase 2 and AI workflow."""

    workflow = StateGraph(AgentState)

    # --------------------------------------------------
    # Bind Phase 1 nodes
    # --------------------------------------------------

    async def _monitor(
        state: AgentState,
        config: RunnableConfig | None = None,
    ) -> dict[str, Any]:
        return await monitor_node(state, config, services=services)

    async def _assess(
        state: AgentState,
        config: RunnableConfig | None = None,
    ) -> dict[str, Any]:
        return await assess_node(state, config, services=services)

    async def _plan(
        state: AgentState,
        config: RunnableConfig | None = None,
    ) -> dict[str, Any]:
        return await plan_node(state, config, services=services)

    def _validate(
        state: AgentState,
        config: RunnableConfig | None = None,
    ) -> dict[str, Any]:
        return validate_node(state, config)

    # --------------------------------------------------
    # Bind Phase 2 nodes
    # --------------------------------------------------

    async def _await_approval(
        state: AgentState,
        config: RunnableConfig | None = None,
    ) -> dict[str, Any]:
        return await await_approval_node(
            state, config, services=services
        )

    async def _dispatch(
        state: AgentState,
        config: RunnableConfig | None = None,
    ) -> dict[str, Any]:
        return await dispatch_node(
            state, config, services=services
        )

    async def _verify(
        state: AgentState,
        config: RunnableConfig | None = None,
    ) -> dict[str, Any]:
        return await verify_node(
            state, config, services=services
        )

    async def _replan(
        state: AgentState,
        config: RunnableConfig | None = None,
    ) -> dict[str, Any]:
        return await replan_node(
            state, config, services=services
        )

    # --------------------------------------------------
    # Register AI report nodes
    # --------------------------------------------------

    workflow.add_node("extract_report", extract_report_node)
    workflow.add_node("validate_report", validate_report_node)

    # --------------------------------------------------
    # Register Phase 1 nodes
    # --------------------------------------------------

    workflow.add_node("monitor", _monitor)
    workflow.add_node("assess", _assess)
    workflow.add_node("plan", _plan)
    workflow.add_node("validate", _validate)

    workflow.add_node("planning_success", planning_success_node)
    workflow.add_node("needs_information", needs_info_node)
    workflow.add_node("planning_failure", planning_failure_node)

    # --------------------------------------------------
    # Register Phase 2 nodes
    # --------------------------------------------------

    workflow.add_node("await_approval", _await_approval)
    workflow.add_node("dispatch", _dispatch)
    workflow.add_node("verify", _verify)
    workflow.add_node("replan", _replan)

    workflow.add_node("approval_pending", approval_pending_node)
    workflow.add_node("approval_rejected", rejected_node)
    workflow.add_node("dispatch_failed", dispatch_failed_node)
    workflow.add_node("completed", completed_node)

    # Legacy execute node
    workflow.add_node("execute", execute_node)

    # --------------------------------------------------
    # Initial input routing
    # --------------------------------------------------

    workflow.add_conditional_edges(
        START,
        route_after_start,
        {
            "extract_report": "extract_report",
            "monitor": "monitor",
            "needs_information": "needs_information",
            "planning_failure": "planning_failure",
        },
    )

    # --------------------------------------------------
    # AI extraction and validation
    # --------------------------------------------------

    workflow.add_edge("extract_report", "validate_report")

    workflow.add_conditional_edges(
        "validate_report",
        route_after_report_validation,
        {
            "monitor": "monitor",
            "needs_information": "needs_information",
            "failed": "planning_failure",
        },
    )

    # --------------------------------------------------
    # Phase 1: Monitor -> Assess -> Plan -> Validate
    # --------------------------------------------------

    workflow.add_edge("monitor", "assess")
    workflow.add_edge("assess", "plan")
    workflow.add_edge("plan", "validate")

    workflow.add_conditional_edges(
        "validate",
        route_after_validation,
        {
            "planning_success": "planning_success",
            "needs_information": "needs_information",
            "planning_failure": "planning_failure",
        },
    )

    workflow.add_edge("needs_information", END)
    workflow.add_edge("planning_failure", END)

    # --------------------------------------------------
    # Phase 2: Human approval
    # --------------------------------------------------

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

    workflow.add_edge("approval_pending", END)
    workflow.add_edge("approval_rejected", END)

    # --------------------------------------------------
    # Phase 2: Dispatch
    # --------------------------------------------------

    workflow.add_conditional_edges(
        "dispatch",
        route_after_dispatch,
        {
            "verify": "verify",
            "dispatch_failed": "dispatch_failed",
        },
    )

    workflow.add_edge("dispatch_failed", END)

    # --------------------------------------------------
    # Phase 2: Verification and replanning
    # --------------------------------------------------

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
    workflow.add_edge("replan", "monitor")

    # Legacy execute node
    workflow.add_edge("execute", END)

    return workflow

def create_agent_workflow(
    services: AgentServices | None = None,
    ) -> CompiledStateGraph:
        """Build and compile the ReliefRoute workflow."""

        graph = build_agent_graph(services)
        return graph.compile()

