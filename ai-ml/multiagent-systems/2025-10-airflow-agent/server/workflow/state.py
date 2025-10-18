"""
Workflow State Definition - Shared state across all agents
"""

from typing import TypedDict, Optional, List, Dict, Any, Literal
from enum import Enum


class AgentType(str, Enum):
    """Agent type identifiers"""

    MONITOR = "MONITOR_AGENT"
    ANALYZER = "ANALYZER_AGENT"
    INTERACTION = "INTERACTION_AGENT"
    ACTION = "ACTION_AGENT"


class AgentState(TypedDict):
    """
    Global state shared across all agents in the workflow

    This state is passed through the entire LangGraph workflow
    and updated by each agent node.
    """

    # Airflow identifiers
    dag_id: Optional[str]
    dag_run_id: Optional[str]
    task_id: Optional[str]
    try_number: Optional[int]

    # Error information
    error_message: Optional[str]
    logs: Optional[str]
    dag_source: Optional[str]

    # Analysis results
    analysis_report: Optional[str]
    search_queries: List[str]
    search_results: List[str]
    root_cause: Optional[str]
    suggested_solution: Optional[str]

    # User interaction
    user_input: Optional[str]
    user_question: Optional[str]
    requires_user_input: bool

    # Action decision
    final_action: Optional[str]  # "CLEAR_TASK", "SKIP", "MANUAL"
    action_result: Optional[str]

    # Workflow control
    is_resolved: bool
    current_agent: Optional[str]
    iteration_count: int
    max_iterations: int

    # Metadata
    session_id: Optional[str]
    timestamp: Optional[str]
    error_details: Dict[str, Any]


def create_initial_state(
    dag_id: Optional[str] = None,
    dag_run_id: Optional[str] = None,
    task_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> AgentState:
    """
    Create initial agent state with default values

    Args:
        dag_id: Optional DAG identifier
        dag_run_id: Optional DAG run identifier
        task_id: Optional task identifier
        session_id: Optional session identifier

    Returns:
        Initial AgentState dictionary
    """
    from datetime import datetime

    return AgentState(
        # Identifiers
        dag_id=dag_id,
        dag_run_id=dag_run_id,
        task_id=task_id,
        try_number=1,
        # Error info
        error_message=None,
        logs=None,
        dag_source=None,
        # Analysis
        analysis_report=None,
        search_queries=[],
        search_results=[],
        root_cause=None,
        suggested_solution=None,
        # User interaction
        user_input=None,
        user_question=None,
        requires_user_input=False,
        # Action
        final_action=None,
        action_result=None,
        # Workflow
        is_resolved=False,
        current_agent=None,
        iteration_count=0,
        max_iterations=5,
        # Metadata
        session_id=session_id,
        timestamp=datetime.now().isoformat(),
        error_details={},
    )
