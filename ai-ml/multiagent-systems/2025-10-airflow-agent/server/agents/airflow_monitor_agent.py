"""
Airflow Monitor Agent - Detects failed DAG runs and tasks
"""

import logging
from typing import Dict, Any
from server.workflow.state import AgentState, AgentType
from server.services.airflow_client import AirflowClient, AirflowAPIError

logger = logging.getLogger(__name__)


class AirflowMonitorAgent:
    """
    Agent responsible for monitoring Airflow and detecting failures

    This agent:
    1. Checks for failed DAG runs
    2. Identifies failed tasks within DAG runs
    3. Extracts basic error information
    4. Populates the state for downstream agents
    """

    def __init__(self, airflow_client: AirflowClient):
        """
        Initialize monitor agent

        Args:
            airflow_client: Configured Airflow API client
        """
        self.client = airflow_client
        self.agent_type = AgentType.MONITOR

    def __call__(self, state: AgentState) -> Dict[str, Any]:
        """
        Execute monitoring logic

        Args:
            state: Current workflow state

        Returns:
            Updated state dictionary
        """
        logger.info("🔍 AirflowMonitorAgent: Starting monitoring...")

        try:
            # If specific DAG/task already provided, skip discovery
            if state.get("dag_id") and state.get("dag_run_id") and state.get("task_id"):
                logger.info(
                    f"Using provided identifiers: "
                    f"DAG={state['dag_id']}, "
                    f"Run={state['dag_run_id']}, "
                    f"Task={state['task_id']}"
                )
                return self._process_specific_failure(state)

            # Otherwise, discover failed DAG runs
            return self._discover_failures(state)

        except AirflowAPIError as e:
            logger.error(f"Airflow API error: {str(e)}")
            return {
                "error_message": f"Airflow API 오류: {str(e)}",
                "is_resolved": False,
                "current_agent": self.agent_type.value,
            }
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}")
            return {
                "error_message": f"예상치 못한 오류: {str(e)}",
                "is_resolved": False,
                "current_agent": self.agent_type.value,
            }

    def _discover_failures(self, state: AgentState) -> Dict[str, Any]:
        """
        Discover failed DAG runs and tasks

        Args:
            state: Current workflow state

        Returns:
            Updated state with discovered failures
        """
        logger.info("Discovering failed DAG runs...")

        # Get failed DAG runs
        failed_runs = self.client.get_failed_dag_runs(limit=10)

        if not failed_runs:
            logger.info("No failed DAG runs found")
            return {
                "error_message": "현재 실패한 DAG Run이 없습니다.",
                "is_resolved": True,
                "current_agent": self.agent_type.value,
            }

        # Take the most recent failed run
        most_recent = failed_runs[0]
        dag_id = most_recent["dag_id"]
        dag_run_id = most_recent["dag_run_id"]

        logger.info(f"Found failed DAG run: {dag_id} / {dag_run_id}")

        # Get failed tasks in this run
        failed_tasks = self.client.get_failed_task_instances(dag_id, dag_run_id)

        if not failed_tasks:
            logger.warning("No failed tasks found in failed DAG run")
            return {
                "dag_id": dag_id,
                "dag_run_id": dag_run_id,
                "error_message": "실패한 태스크를 찾을 수 없습니다.",
                "is_resolved": False,
                "current_agent": self.agent_type.value,
            }

        # Take the first failed task
        first_failed = failed_tasks[0]
        task_id = first_failed["task_id"]
        try_number = first_failed.get("try_number", 1)

        logger.info(f"Found failed task: {task_id} (try {try_number})")

        # Extract error information
        error_details = {
            "dag_id": dag_id,
            "dag_run_id": dag_run_id,
            "task_id": task_id,
            "try_number": try_number,
            "state": first_failed.get("state"),
            "start_date": first_failed.get("start_date"),
            "end_date": first_failed.get("end_date"),
            "duration": first_failed.get("duration"),
        }

        return {
            "dag_id": dag_id,
            "dag_run_id": dag_run_id,
            "task_id": task_id,
            "try_number": try_number,
            "error_message": (
                f"DAG '{dag_id}'의 Run '{dag_run_id}'에서 "
                f"Task '{task_id}'가 실패했습니다."
            ),
            "error_details": error_details,
            "current_agent": self.agent_type.value,
        }

    def _process_specific_failure(self, state: AgentState) -> Dict[str, Any]:
        """
        Process a specific known failure

        Args:
            state: State with known DAG/task identifiers

        Returns:
            Updated state
        """
        dag_id = state["dag_id"]
        dag_run_id = state["dag_run_id"]
        task_id = state["task_id"]

        logger.info(f"Processing specific failure: " f"{dag_id}/{dag_run_id}/{task_id}")

        # Verify the task is actually failed
        try:
            task_instance = self.client.get_task_instance(dag_id, dag_run_id, task_id)

            task_state = task_instance.get("state")
            if task_state != "failed":
                logger.warning(f"Task state is '{task_state}', not 'failed'")

            try_number = task_instance.get("try_number", 1)

            return {
                "dag_id": dag_id,
                "dag_run_id": dag_run_id,
                "task_id": task_id,
                "try_number": try_number,
                "error_message": (f"Task '{task_id}' 분석 시작 (상태: {task_state})"),
                "error_details": {
                    "state": task_state,
                    "try_number": try_number,
                    "start_date": task_instance.get("start_date"),
                    "end_date": task_instance.get("end_date"),
                },
                "current_agent": self.agent_type.value,
            }

        except AirflowAPIError:
            return {
                "error_message": (
                    f"Task 정보를 가져올 수 없습니다: "
                    f"{dag_id}/{dag_run_id}/{task_id}"
                ),
                "current_agent": self.agent_type.value,
            }
