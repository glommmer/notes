"""
Action Agent - Executes actions on Airflow based on user decision
"""

import logging
from typing import Dict, Any
from server.workflow.state import AgentState, AgentType
from server.services.airflow_client import AirflowClient, AirflowAPIError

logger = logging.getLogger(__name__)


class ActionAgent:
    """
    Agent responsible for executing actions

    This agent:
    1. Takes approved actions (e.g., clear task)
    2. Calls Airflow API to perform the action
    3. Reports results back to the user
    """

    def __init__(self, airflow_client: AirflowClient):
        """
        Initialize action agent

        Args:
            airflow_client: Configured Airflow API client
        """
        self.client = airflow_client
        self.agent_type = AgentType.ACTION

    def __call__(self, state: AgentState) -> Dict[str, Any]:
        """
        Execute action based on user decision

        Args:
            state: Current workflow state

        Returns:
            Updated state with action results
        """
        logger.info("⚡ ActionAgent: Executing action...")

        final_action = state.get("final_action")

        if not final_action:
            logger.error("No action specified")
            return {
                "action_result": "실행할 액션이 지정되지 않았습니다.",
                "is_resolved": False,
                "current_agent": self.agent_type.value,
            }

        # Route to appropriate action handler
        if final_action == "CLEAR_TASK":
            return self._clear_task(state)

        elif final_action == "SKIP":
            return self._skip_action(state)

        elif final_action == "SHOW_REPORT":
            return self._show_report(state)

        else:
            logger.warning(f"Unknown action: {final_action}")
            return {
                "action_result": f"알 수 없는 액션: {final_action}",
                "is_resolved": False,
                "current_agent": self.agent_type.value,
            }

    def _clear_task(self, state: AgentState) -> Dict[str, Any]:
        """
        Clear task instance to trigger retry

        Args:
            state: Current state with task identifiers

        Returns:
            Updated state with action result
        """
        dag_id = state.get("dag_id")
        task_id = state.get("task_id")

        if not dag_id or not task_id:
            return {
                "action_result": "Task 정보가 부족하여 재실행할 수 없습니다.",
                "is_resolved": False,
                "current_agent": self.agent_type.value,
            }

        logger.info(f"Clearing task: {dag_id}/{task_id}")

        try:
            # First do a dry run to check what would be cleared
            dry_run_result = self.client.clear_task_instance(
                dag_id=dag_id, task_ids=[task_id], dry_run=True, only_failed=True
            )

            tasks_to_clear = dry_run_result.get("task_instances", [])
            logger.info(f"Dry run: {len(tasks_to_clear)} tasks would be cleared")

            if not tasks_to_clear:
                return {
                    "action_result": (
                        "⚠️  Clear할 Task가 없습니다. "
                        "Task가 이미 재시도 중이거나 상태가 변경되었을 수 있습니다."
                    ),
                    "is_resolved": True,
                    "current_agent": self.agent_type.value,
                }

            # Actually clear the task
            clear_result = self.client.clear_task_instance(
                dag_id=dag_id,
                task_ids=[task_id],
                dry_run=False,
                only_failed=True,
                reset_dag_runs=True,
            )

            cleared_tasks = clear_result.get("task_instances", [])

            result_message = f"""
## ✅ Task 재실행 완료

**DAG**: {dag_id}  
**Task**: {task_id}  
**Clear된 Task 수**: {len(cleared_tasks)}

Task가 Clear되어 Airflow Scheduler가 곧 재실행을 시도합니다.
DAG 실행 상태는 Airflow UI에서 확인하실 수 있습니다.

### Clear된 Task 목록:
"""

            for task in cleared_tasks[:5]:  # Show first 5
                result_message += (
                    f"- {task.get('task_id')} " f"(Run: {task.get('dag_run_id')})\n"
                )

            if len(cleared_tasks) > 5:
                result_message += f"... 외 {len(cleared_tasks) - 5}개\n"

            logger.info("Task cleared successfully")

            return {
                "action_result": result_message,
                "is_resolved": True,
                "current_agent": self.agent_type.value,
            }

        except AirflowAPIError as e:
            error_message = f"""
## ❌ Task 재실행 실패

Airflow API 호출 중 오류가 발생했습니다:
```
{str(e)}
```

다음을 확인해주세요:
- Airflow 연결 설정이 올바른지
- 해당 DAG/Task가 존재하는지
- 권한이 충분한지
"""
            logger.error(f"Failed to clear task: {e}")

            return {
                "action_result": error_message,
                "is_resolved": False,
                "current_agent": self.agent_type.value,
            }

    def _skip_action(self, state: AgentState) -> Dict[str, Any]:
        """
        Skip automatic action - manual handling required

        Args:
            state: Current state

        Returns:
            Updated state
        """
        dag_id = state.get("dag_id", "알 수 없음")
        task_id = state.get("task_id", "알 수 없음")

        message = f"""
## ⏭️  수동 처리 모드

**DAG**: {dag_id}  
**Task**: {task_id}

자동 재실행을 건너뛰었습니다.
다음 단계를 직접 수행해주세요:

1. 코드 또는 설정 수정
2. Airflow UI에서 Task 상태 확인
3. 필요한 경우 수동으로 Clear 실행

분석 보고서를 참고하여 문제를 해결해주세요.
"""

        logger.info("Skipping automatic action - manual handling")

        return {
            "action_result": message,
            "is_resolved": True,
            "current_agent": self.agent_type.value,
        }

    def _show_report(self, state: AgentState) -> Dict[str, Any]:
        """
        Show full analysis report

        Args:
            state: Current state

        Returns:
            Updated state with full report
        """
        analysis_report = state.get("analysis_report", "분석 보고서가 없습니다.")

        message = f"""
## 📄 전체 분석 보고서

{analysis_report}

---

위 분석을 참고하여 다음 액션을 결정해주세요:
- Task 재실행을 원하시면 '재실행' 또는 '1'을 입력하세요
- 수동 처리를 원하시면 '수동' 또는 '2'를 입력하세요
"""

        logger.info("Showing full analysis report")

        return {
            "action_result": message,
            "requires_user_input": True,  # Ask again after showing report
            "user_question": "어떤 액션을 수행하시겠습니까?",
            "is_resolved": False,
            "current_agent": self.agent_type.value,
        }
