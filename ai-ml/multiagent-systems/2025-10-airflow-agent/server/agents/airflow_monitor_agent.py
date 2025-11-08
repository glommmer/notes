"""
Airflow Monitor Agent - Detects failed DAG runs and tasks
"""

import logging
from typing import Dict, Any
from langchain_openai import ChatOpenAI, AzureChatOpenAI
from server.workflow.state import AgentState, AgentType
from server.services.airflow_client import AirflowClient, AirflowAPIError
from server.config import settings

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

        # Initialize LLM for generating user-friendly messages
        self.llm = ChatOpenAI(
            model=settings.OPENAI_MODEL,
            temperature=0.5,
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL,
        )

        # self.llm = AzureChatOpenAI(
        #     openai_api_key=settings.AZURE_OPENAI_API_KEY,
        #     azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
        #     azure_deployment=settings.AZURE_OPENAI_DEPLOYMENT,
        #     api_version=settings.AZURE_OPENAI_API_VERSION,
        #     temperature=0.5,
        #     # streaming=True,  # 스트리밍 활성화
        # )

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
            # 1. user_input 분석 추가
            user_input = state.get("user_input", "").strip()

            # 2. user_input에서 DAG ID, 날짜 등 추출
            if user_input:
                # LLM을 사용하여 user_input 파싱
                logger.info(f"Parsing user input: {user_input}")
                parsed_request = self._parse_user_request(user_input)
                logger.info(f"Parsed request: {parsed_request}")

                # 파싱 결과를 state에 반영
                if parsed_request.get("dag_id"):
                    state["dag_id"] = parsed_request["dag_id"]
                    logger.info(
                        f"Set dag_id from user input: {parsed_request['dag_id']}"
                    )
                if parsed_request.get("date"):
                    state["target_date"] = parsed_request["date"]
                if parsed_request.get("task_id"):
                    state["task_id"] = parsed_request["task_id"]

            # 3. dag_id가 있으면 특정 DAG 모니터링 (실패 여부와 무관)
            if state.get("dag_id"):
                logger.info(f"Monitoring specific DAG: {state.get('dag_id')}")
                return self._monitor_specific_dag(state.get("dag_id"), state)

            # 4. dag_id가 없으면 실패한 DAG 발견
            logger.info("No specific DAG requested - discovering failures")
            return self._discover_failures(state)

        except Exception as e:
            logger.error(f"Monitoring error: {str(e)}", exc_info=True)
            return {
                "error_message": f"Monitoring failed: {str(e)}",
                "is_resolved": False,
                "current_agent": self.agent_type.value,
            }

    def _parse_user_request(self, user_input: str) -> Dict[str, Any]:
        """LLM을 사용하여 user_input에서 DAG ID, 날짜 등 추출"""
        prompt = f"""
        Extract structured information from this Airflow monitoring request:

        User Request: "{user_input}"
        
        Extract the following (return JSON only):
        - dag_id: The DAG identifier (e.g., "success_dag", "failed_dag")
        - date: Date in YYYY-MM-DD format if mentioned (e.g., "2025년 11월 7일" -> "2025-11-07")
        - task_id: Task identifier if mentioned
        - action: What user wants (e.g., "check_status", "analyze", "clear")
        
        Examples:
        - "success_dag 상태 확인" -> {{"dag_id": "success_dag", "action": "check_status"}}
        - "failed_dag의 2025년 11월 7일 작업" -> {{"dag_id": "failed_dag", "date": "2025-11-07"}}
        
        Return valid JSON only, no explanation.
        """

        try:
            response = self.llm.invoke(prompt)
            import json

            # Parse JSON from response
            content = response.content.strip()

            # Remove Markdown code blocks if present
            if content.startswith("```"):
                content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]

            parsed = json.loads(content.strip())
            logger.info(f"✅ Successfully parsed user input: {parsed}")
            return parsed
        except Exception as e:
            logger.error(f"Failed to parse user input: {e}")
            return {}

    def _monitor_specific_dag(self, dag_id: str, state: AgentState) -> Dict[str, Any]:
        """Monitor a specific DAG (all states, not just failures)"""
        logger.info(f"Monitoring specific DAG: {dag_id}")

        target_date = state.get("target_date")

        try:
            # Get recent DAG runs
            dag_runs = self.client.get_dag_runs(
                dag_id, limit=10, start_date_gte=target_date if target_date else None
            )

            if not dag_runs:
                return {
                    "dag_id": dag_id,
                    "monitoring_result": f"DAG '{dag_id}'에 대한 실행 기록이 없습니다.",
                    "is_resolved": True,
                    "next_agent": "end",
                    "current_agent": self.agent_type.value,
                }

            # Collect all task states
            all_tasks = []
            failed_tasks = []

            for run in dag_runs.get("dag_runs"):  # Check last 3 runs
                run_id = run.get("dag_run_id")
                run_state = run.get("state")

                logger.info(f"Checking run: {run_id}, state: {run_state}")

                task_instances = self.client.get_task_instances(dag_id, run_id)

                for task in task_instances.get("task_instances"):
                    task_state = task.get("state")
                    task_info = {
                        "dag_id": dag_id,
                        "run_id": run_id,
                        "task_id": task.get("task_id"),
                        "state": task_state,
                        "start_date": task.get("start_date"),
                        "end_date": task.get("end_date"),
                    }

                    all_tasks.append(task_info)

                    if task_state == "failed":
                        failed_tasks.append(task_info)

            # Generate summary message
            status_counts = {}
            for task in all_tasks:
                state = task["state"]
                status_counts[state] = status_counts.get(state, 0) + 1

            summary = f"DAG '{dag_id}' 상태:\n"
            summary += f"- 총 작업 수: {len(all_tasks)}\n"
            for state, count in sorted(status_counts.items()):
                emoji = (
                    "✅" if state == "success" else "❌" if state == "failed" else "⏳"
                )
                summary += f"- {emoji} {state}: {count}개\n"

            # If no failures, end workflow
            if not failed_tasks:
                return {
                    "dag_id": dag_id,
                    "total_tasks": len(all_tasks),
                    "failed_tasks": [],
                    "monitoring_result": summary + "\n✅ 모든 작업이 정상입니다.",
                    "is_resolved": True,
                    "next_agent": "end",
                    "current_agent": self.agent_type.value,
                }

            # If there are failures, proceed to analysis
            first_failed = failed_tasks[0]

            return {
                "dag_id": dag_id,
                "dag_run_id": first_failed["run_id"],
                "task_id": first_failed["task_id"],
                "failed_tasks": failed_tasks,
                "monitoring_result": summary
                + f"\n⚠️ {len(failed_tasks)}개 실패 작업 발견. 분석을 시작합니다.",
                "next_agent": "analyzer",
                "current_agent": self.agent_type.value,
            }

        except Exception as e:
            logger.error(f"Error monitoring DAG {dag_id}: {str(e)}", exc_info=True)
            return {
                "error_message": f"DAG '{dag_id}' 모니터링 실패: {str(e)}",
                "is_resolved": False,
                "next_agent": "end",
                "current_agent": self.agent_type.value,
            }

    def _discover_failures(self, state: AgentState) -> Dict[str, Any]:
        """Discover failed DAG runs (original logic)"""
        logger.info("Discovering failed DAG runs...")

        try:
            # Get failed DAG runs from last 24 hours
            from datetime import datetime, timedelta

            end_date = datetime.utcnow()
            start_date = end_date - timedelta(hours=24)

            failed_runs = self.client.get_dag_runs(
                state="failed", start_date_gte=start_date.isoformat(), limit=10
            )

            logger.info(f"Found {len(failed_runs)} failed DAG runs")

            if not failed_runs:
                return {
                    "monitoring_result": "✅ 지난 24시간 동안 실패한 DAG가 없습니다.",
                    "is_resolved": True,
                    "next_agent": "end",
                    "current_agent": self.agent_type.value,
                }

            # Get first failed run
            first_run = failed_runs[0]
            dag_id = first_run.get("dag_id")
            run_id = first_run.get("dag_run_id")

            logger.info(f"Found failed DAG run: {dag_id} / {run_id}")

            # Get failed tasks
            task_instances = self.client.get_task_instances(dag_id, run_id)
            failed_tasks = [t for t in task_instances if t.get("state") == "failed"]

            if not failed_tasks:
                # Skip to next failed run
                logger.warning(f"No failed tasks found in {dag_id}/{run_id}")
                return {
                    "monitoring_result": "실패한 작업을 찾을 수 없습니다.",
                    "is_resolved": True,
                    "next_agent": "end",
                    "current_agent": self.agent_type.value,
                }

            first_task = failed_tasks[0]

            logger.info(
                f"Found failed task: {first_task.get('task_id')} (try {first_task.get('try_number')})"
            )

            return {
                "dag_id": dag_id,
                "dag_run_id": run_id,
                "task_id": first_task.get("task_id"),
                "try_number": first_task.get("try_number", 1),
                "failed_tasks": failed_tasks,
                "monitoring_result": f"실패한 DAG 발견: {dag_id}",
                "next_agent": "analyzer",
                "current_agent": self.agent_type.value,
            }

        except Exception as e:
            logger.error(f"Error discovering failures: {str(e)}", exc_info=True)
            raise

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
