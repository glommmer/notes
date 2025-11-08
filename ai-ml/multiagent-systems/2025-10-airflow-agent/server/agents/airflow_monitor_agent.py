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
            temperature=0.0,
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
            # user_input 먼저 확인 및 파싱
            user_input = state.get("user_input", "").strip()

            if user_input:
                logger.info(f"Parsing user input: {user_input}")
                parsed_request = self._parse_user_request(user_input)
                logger.info(f"Parsed request: {parsed_request}")

                # action이 "report"이면 dag_id가 null이어도 괜찮음
                action = parsed_request.get("action")

                if action == "report" and state.get("analysis_report"):
                    logger.info("User requesting report - skipping monitor")
                    return {
                        "current_agent": self.agent_type.value,
                    }

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

            # 이미 분석이 완료되었지만, 새로운 dag_id가 user_input에서 추출되었으면 새로 모니터링
            if state.get("analysis_report"):
                # 새로운 DAG 요청인지 확인
                previous_dag = state.get("previous_dag_id")  # 이전 분석한 DAG
                current_dag = state.get("dag_id")  # 현재 요청한 DAG

                # dag_id가 None이면 스킵 (보고서 요청 또는 잘못된 파싱)
                if not current_dag:
                    logger.info("⏭️ No specific DAG requested - skipping monitor")
                    return {
                        "current_agent": self.agent_type.value,
                    }

                # ~ (모든 DAG)는 매번 새로 조회해야 함
                if current_dag == "~":
                    logger.info(
                        "Wildcard DAG request (~) - proceeding to discover all failures"
                    )
                    state["analysis_report"] = None
                    state["root_cause"] = None
                elif previous_dag and current_dag and previous_dag == current_dag:
                    logger.info(
                        "⏭️ Analysis already done for same DAG - skipping monitor"
                    )
                    return {
                        "current_agent": self.agent_type.value,
                    }
                elif current_dag and current_dag != previous_dag:
                    logger.info(
                        f"New DAG requested ({current_dag}) - proceeding to monitor"
                    )
                    state["analysis_report"] = None
                    state["root_cause"] = None
                else:
                    logger.info("⏭️ Analysis already done - skipping monitor")
                    return {
                        "current_agent": self.agent_type.value,
                    }

            # dag_id가 "~"이면 실패한 모든 DAG 발견
            if state.get("dag_id") == "~":
                logger.info("Monitoring all DAGs (wildcard ~)")
                result = self._discover_failures(state)

                if result.get("dag_id"):
                    result["previous_dag_id"] = "~"  # 와일드카드 요청 기록

                return result

            # 특정 dag_id가 있으면 해당 DAG 모니터링
            if state.get("dag_id"):
                logger.info(f"Monitoring specific DAG: {state.get('dag_id')}")
                result = self._monitor_specific_dag(state.get("dag_id"), state)
                result["previous_dag_id"] = state.get("dag_id")
                return result

            # dag_id가 없으면 실패한 DAG 발견
            logger.info("No specific DAG requested - discovering failures")
            result = self._discover_failures(state)

            if result.get("dag_id"):
                result["previous_dag_id"] = result.get("dag_id")

            return result

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
- dag_id: The specific DAG identifier (e.g., "failed_dag", "success_dag")
  - If user says "모든" (all), "전체" (entire), set dag_id to "~" (Airflow wildcard)
  - If dag_id cannot be identified, set to null
  - If user is asking for report/보고서 without DAG name, set to null
- date: Date in YYYY-MM-DD format if mentioned (otherwise null)
- task_id: Task identifier if mentioned (otherwise null)
- action: What user wants (e.g., "check_status", "analyze", "clear", "report")

Examples:
- "failed_dag 분석" -> {{"dag_id": "failed_dag", "action": "analyze"}}
- "success_dag의 2025년 11월 7일 작업" -> {{"dag_id": "success_dag", "date": "2025-11-07"}}
- "모든 DAG 분석" -> {{"dag_id": "~", "action": "analyze"}}  # ~ for all DAGs
- "2025년 11월 6일 이후 모든 에러" -> {{"dag_id": "~", "date": "2025-11-06", "action": "analyze"}}
- "보고서로 보여줘" -> {{"dag_id": null, "action": "report"}}

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

            for run in dag_runs:  # Check last 3 runs
                run_id = run.get("dag_run_id")
                run_state = run.get("state")
                dag_id = run.get("dag_id") or dag_id

                logger.info(f"Checking run: {run_id}, state: {run_state}")

                task_instances = self.client.get_task_instances(dag_id, run_id)

                for task in task_instances:
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
        """Discover failed DAG runs"""
        logger.info("Discovering failed DAG runs...")

        try:
            from datetime import datetime, timedelta, UTC

            # target_date가 있으면 해당 날짜 이후, 없으면 최근 24시간
            target_date = state.get("target_date")

            if target_date:
                start_date_str = target_date
                logger.info(f"Searching for failures since: {target_date}")
            else:
                end_date = datetime.now(UTC)
                start_date = end_date - timedelta(hours=24)
                start_date_str = start_date.strftime("%Y-%m-%d")
                logger.info(f"Searching for failures in last 24 hours")

            # dag_id="~" 또는 None이면 모든 DAG 조회
            dag_id = state.get("dag_id")

            if dag_id == "~":
                # Get failed runs from all DAGs
                failed_runs = self.client.get_dag_runs(
                    dag_id="~",
                    state="failed",
                    start_date_gte=start_date_str,
                    limit=50,  # 더 많이 조회
                )
                logger.info(f"Found {len(failed_runs)} failed DAG runs across all DAGs")
            else:
                # Get failed runs from specific DAG
                failed_runs = self.client.get_dag_runs(
                    dag_id,
                    state="failed",
                    start_date_gte=start_date_str,
                    limit=10,
                )
                logger.info(f"Found {len(failed_runs)} failed runs for DAG {dag_id}")

            if not failed_runs:
                return {
                    "monitoring_result": f"✅ {start_date_str} 이후로 실패한 DAG가 없습니다.",
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
                "total_failed_runs": len(failed_runs),  # 전체 실패 수
                "monitoring_result": f"실패한 DAG 발견: {dag_id} (총 {len(failed_runs)}개 실패)",
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
