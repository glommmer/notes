"""
Airflow Monitoring Agent - Detects failed tasks and retrieves logs.
"""

import logging
from typing import Dict, Any
from server.workflow.state import AgentState
from server.services.airflow_client import AirflowClient

logger = logging.getLogger(__name__)


class AirflowMonitorAgent:
    """Agent responsible for monitoring Airflow DAGs and detecting failures."""

    def __init__(self):
        """Initialize the monitoring agent."""
        self.client = AirflowClient()
        logger.info("AirflowMonitorAgent initialized")

    def process(self, state: AgentState) -> Dict[str, Any]:
        """
        Process the monitoring task.

        Args:
            state: Current agent state

        Returns:
            Updated state with monitoring results
        """
        try:
            logger.info("Starting Airflow monitoring...")

            # Check if specific DAG context is provided
            dag_id = state.get("dag_id")

            if dag_id:
                result = self._monitor_specific_dag(dag_id, state)
            else:
                result = self._monitor_all_dags()

            # Update state
            updates = {
                "monitoring_result": result,
                "failed_tasks": result.get("failed_tasks", []),
                "next_agent": "error_analyzer" if result.get("failed_tasks") else "end",
                "workflow_complete": not bool(result.get("failed_tasks")),
            }

            if not result.get("failed_tasks"):
                updates["final_response"] = (
                    "모든 DAG가 정상적으로 실행되고 있습니다. 실패한 작업이 없습니다."
                )

            logger.info(
                f"Monitoring completed. Found {len(result.get('failed_tasks', []))} failed tasks"
            )
            return updates

        except Exception as e:
            logger.error(f"Error in monitoring agent: {str(e)}", exc_info=True)
            return {
                "error": f"Monitoring failed: {str(e)}",
                "final_response": f"Airflow 모니터링 중 오류가 발생했습니다: {str(e)}",
                "workflow_complete": True,
                "next_agent": "end",
            }

    def _monitor_specific_dag(self, dag_id: str, state: AgentState) -> Dict[str, Any]:
        """Monitor a specific DAG."""
        logger.info(f"Monitoring specific DAG: {dag_id}")

        try:
            # Get DAG runs
            dag_runs = self.client.get_dag_runs(dag_id, limit=10)

            failed_tasks = []
            task_id = state.get("task_id")
            run_id = state.get("run_id")

            for run in dag_runs:
                current_run_id = run.get("dag_run_id")

                # If specific run_id is provided, only check that run
                if run_id and current_run_id != run_id:
                    continue

                # Get task instances for this run
                task_instances = self.client.get_task_instances(dag_id, current_run_id)

                for task in task_instances:
                    # If specific task_id is provided, only check that task
                    if task_id and task.get("task_id") != task_id:
                        continue

                    if task.get("state") == "failed":
                        # Get task logs
                        logs = self.client.get_task_logs(
                            dag_id,
                            current_run_id,
                            task.get("task_id"),
                            task.get("try_number", 1),
                        )

                        failed_tasks.append(
                            {
                                "dag_id": dag_id,
                                "run_id": current_run_id,
                                "task_id": task.get("task_id"),
                                "state": task.get("state"),
                                "start_date": task.get("start_date"),
                                "end_date": task.get("end_date"),
                                "logs": logs,
                            }
                        )

            return {
                "dag_id": dag_id,
                "total_runs_checked": len(dag_runs),
                "failed_tasks": failed_tasks,
            }

        except Exception as e:
            logger.error(f"Error monitoring DAG {dag_id}: {str(e)}")
            raise

    def _monitor_all_dags(self) -> Dict[str, Any]:
        """Monitor all DAGs for failures."""
        logger.info("Monitoring all DAGs...")

        try:
            # Get all DAGs
            dags = self.client.get_dags()

            failed_tasks = []

            for dag in dags[:5]:  # Limit to 5 DAGs for performance
                dag_id = dag.get("dag_id")

                # Get recent dag runs
                dag_runs = self.client.get_dag_runs(dag_id, limit=3)

                for run in dag_runs:
                    if run.get("state") == "failed":
                        run_id = run.get("dag_run_id")

                        # Get failed task instances
                        task_instances = self.client.get_task_instances(dag_id, run_id)

                        for task in task_instances:
                            if task.get("state") == "failed":
                                logs = self.client.get_task_logs(
                                    dag_id,
                                    run_id,
                                    task.get("task_id"),
                                    task.get("try_number", 1),
                                )

                                failed_tasks.append(
                                    {
                                        "dag_id": dag_id,
                                        "run_id": run_id,
                                        "task_id": task.get("task_id"),
                                        "state": task.get("state"),
                                        "start_date": task.get("start_date"),
                                        "end_date": task.get("end_date"),
                                        "logs": logs,
                                    }
                                )

            return {"total_dags_checked": len(dags[:5]), "failed_tasks": failed_tasks}

        except Exception as e:
            logger.error(f"Error monitoring all DAGs: {str(e)}")
            raise
