"""
LangGraph Workflow Definition - Orchestrates multi-agent workflow
"""

import logging
from pathlib import Path
from typing import Literal
from langgraph.graph import StateGraph, END
from server.workflow.state import AgentState, create_initial_state
from server.agents import (
    AirflowMonitorAgent,
    ErrorAnalyzerAgent,
    UserInteractionAgent,
    ActionAgent,
)
from server.services.airflow_client import AirflowClient
from server.config import settings

logger = logging.getLogger(__name__)


def create_monitoring_graph(session_id: str = None) -> StateGraph:
    """
    Create the monitoring workflow graph

    This graph orchestrates the multi-agent workflow:
    1. Monitor → Detect failed DAG runs/tasks
    2. Analyzer → Analyze errors and find solutions
    3. Interaction → Ask user for decision
    4. Action → Execute approved action
    5. END

    Args:
        session_id: Optional session identifier for tracking

    Returns:
        Compiled StateGraph ready for execution
    """
    logger.info("Creating monitoring workflow graph...")

    try:
        # Initialize Airflow client
        airflow_client = AirflowClient()
        logger.info("Airflow client initialized")

        # Initialize agents
        monitor_agent = AirflowMonitorAgent(airflow_client)
        analyzer_agent = ErrorAnalyzerAgent(airflow_client)
        interaction_agent = UserInteractionAgent()
        action_agent = ActionAgent(airflow_client)
        logger.info("All agents initialized")

        # Create state graph
        workflow = StateGraph(AgentState)

        # Add nodes for each agent
        workflow.add_node("monitor", monitor_agent)
        workflow.add_node("analyzer", analyzer_agent)
        workflow.add_node("interaction", interaction_agent)
        workflow.add_node("action", action_agent)

        logger.info("Nodes added to workflow")

        # Define conditional routing functions
        def should_analyze(
            state: AgentState,
        ) -> Literal["analyzer", "interaction", "end"]:
            """
            Decide whether to proceed to analysis

            Returns:
                "analyzer" if error found, "end" if no errors or already resolved

            *Literal["analyzer", "end"]
            - 이 함수는 정확하게 "analyzer" 또는 "end" 문자열만 반환할 수 있음을 타입 체커에게 전달
            """
            # 이미 분석이 완료되었고 user_input이 있으면 interaction으로 바로 이동
            if state.get("analysis_report") and state.get("user_input"):
                logger.info("⏭️ Analysis already complete - skipping to interaction")
                return "interaction"

            # Check if monitoring found an error
            if state.get("is_resolved"):
                logger.info("No errors to analyze - workflow ending")
                return "end"

            # dag_id, task_id 모두 있는지 체크
            if not state.get("dag_id") or not state.get("task_id"):
                logger.warning("No task identified for analysis - workflow ending")
                return "end"

            logger.info("Proceeding to error analysis")
            return "analyzer"

        def should_interact(state: AgentState) -> Literal["interaction", "end"]:
            """
            Decide whether to proceed to user interaction

            Returns:
                "interaction" if analysis complete, "end" if failed
            """
            # 분석 보고서 있는지 체크
            if not state.get("analysis_report"):
                logger.warning("No analysis report available - workflow ending")
                return "end"

            logger.info("Proceeding to user interaction")
            return "interaction"

        def should_act(
            state: AgentState,
        ) -> Literal["action", "interaction", "monitor", "end"]:
            """
            Decide whether to execute action or wait for user input

            Returns:
                "action" if user input received
                "interaction" if waiting for input
                "end" if resolved
            """
            # NEW_ANALYSIS 액션이면 monitor로 되돌아가기
            if state.get("final_action") == "NEW_ANALYSIS":
                logger.info("🔄 New analysis requested - returning to monitor")
                return "monitor"

            # 오류 존재 여부 체크
            if state.get("is_resolved"):
                logger.info("Issue already resolved - workflow ending")
                return "end"

            iteration_count = state.get("iteration_count", 0)
            max_iterations = state.get("max_iterations", 20)

            if iteration_count >= max_iterations:
                logger.warning(
                    f"⏱️ Max iterations {max_iterations} reached - ending workflow"
                )
                return "end"

            if state.get("requires_user_input"):
                if state.get("user_input"):
                    # 입력이 있으면 interaction 처리
                    logger.info("💬 Processing user input")
                    return "action"
                else:
                    # 입력이 대기 중이면 END로 종료
                    logger.info(
                        f"⏳ Iteration {iteration_count}: Waiting for user input..."
                    )
                    return "end"

            # Check if we have a decision
            if state.get("final_action"):
                logger.info("Proceeding to action execution")
                return "action"

            logger.warning("No clear path forward - workflow ending")
            return "end"

        def should_end(state: AgentState) -> Literal["end", "interaction"]:
            """
            Decide whether workflow should end or continue

            Returns:
                "end" if resolved or no more actions needed
                "interaction" if waiting for more user input
            """
            # 오류 존재 여부 체크
            if state.get("is_resolved"):
                logger.info("Workflow completed successfully")
                return "end"

            # Check if still waiting for user input
            if state.get("requires_user_input") and not state.get("user_input"):
                logger.info("Still waiting for user input")
                return "interaction"

            # Check iteration count to prevent infinite loops
            iteration = state.get("iteration_count", 0)
            max_iterations = state.get("max_iterations", 5)

            if iteration >= max_iterations:
                logger.warning(
                    f"Max iterations ({max_iterations}) reached - workflow ending"
                )
                return "end"

            return "end"

        # Set entry point
        workflow.set_entry_point("monitor")

        # Add edges with conditional routing
        workflow.add_conditional_edges(
            "monitor",
            should_analyze,
            {
                "analyzer": "analyzer",
                "interaction": "interaction",
                "end": END,
            },
        )

        workflow.add_conditional_edges(
            "analyzer", should_interact, {"interaction": "interaction", "end": END}
        )

        workflow.add_conditional_edges(
            "interaction",
            should_act,
            {
                "action": "action",
                "interaction": "interaction",
                "monitor": "monitor",
                "end": END,
            },
        )

        workflow.add_conditional_edges(
            "action", should_end, {"end": END, "interaction": "interaction"}
        )

        # Compile the graph
        logger.info("Compiling workflow graph...")
        app = workflow.compile()

        # 그래프 이미지 생성
        try:
            # PNG 파일로 저장
            graph_image = app.get_graph().draw_mermaid_png()

            # 현재 파일과 동일한 경로에 저장
            output_path = Path(__file__).parent / "workflow_graph.png"

            with open(output_path, "wb") as f:
                f.write(graph_image)

            logger.info(f"✅ Workflow graph saved to: {output_path}")

        except Exception as e:
            logger.warning(f"Failed to generate graph image: {e}")

        logger.info("Workflow graph created and compiled successfully")

        return app

    except Exception as e:
        logger.error(f"Failed to create workflow graph: {str(e)}", exc_info=True)
        raise


def run_monitoring_workflow(
    dag_id: str = None,
    dag_run_id: str = None,
    task_id: str = None,
    session_id: str = None,
    user_input: str = None,
) -> AgentState:
    """
    Run the monitoring workflow synchronously

    Args:
        dag_id: Optional specific DAG to monitor
        dag_run_id: Optional specific DAG run
        task_id: Optional specific task
        session_id: Optional session identifier
        user_input: Optional user input for interaction

    Returns:
        Final workflow state
    """
    # Create initial state
    initial_state = create_initial_state(
        dag_id=dag_id, dag_run_id=dag_run_id, task_id=task_id, session_id=session_id
    )

    if user_input:
        initial_state["user_input"] = user_input

    # Create and run graph
    app = create_monitoring_graph(session_id)

    # Execute workflow
    final_state = app.invoke(initial_state)

    return final_state
