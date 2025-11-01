"""
User Interaction Agent - Communicates with user and gets feedback
"""

import logging
from typing import Dict, Any
from langchain_openai import ChatOpenAI, AzureChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from server.workflow.state import AgentState, AgentType
from server.config import settings

logger = logging.getLogger(__name__)


class UserInteractionAgent:
    """
    Agent responsible for user communication

    This agent:
    1. Presents analysis results to the user
    2. Asks clarifying questions
    3. Gets user approval for actions
    4. Handles user feedback
    """

    def __init__(self):
        """Initialize interaction agent"""
        self.agent_type = AgentType.INTERACTION

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
        Generate user interaction message

        Args:
            state: Current workflow state

        Returns:
            Updated state with user question
        """
        logger.info("💬 UserInteractionAgent: Preparing user interaction...")

        # Check if we already have user input
        # 사용자 입력이 이미 있으면 바로 처리
        if state.get("user_input"):
            logger.info("User input already provided, processing...")
            return self._process_user_input(state)

        if state.get("requires_user_input") and state.get("user_question"):
            logger.info("Already waiting for user input - no change")
            return {
                "current_agent": self.agent_type.value,  # 다른 필드 반환 안 함 (상태 유지)
            }

        # Generate question for user
        # 첫 번째 질문 생성
        question = self._generate_user_question(state)

        # if not state.get("requires_user_input"):
        #     return {
        #         "user_question": question,
        #         "requires_user_input": True,  # ← 처음만!
        #         "current_agent": self.agent_type.value,
        #     }

        return {
            "user_question": question,
            "requires_user_input": True,
            "current_agent": self.agent_type.value,
        }

    def _generate_user_question(self, state: AgentState) -> str:
        """
        Generate user-friendly question based on analysis

        Args:
            state: Current workflow state

        Returns:
            User question string
        """
        dag_id = state.get("dag_id", "알 수 없음")
        task_id = state.get("task_id", "알 수 없음")
        dag_run_id = state.get("dag_run_id", "알 수 없음")

        analysis_report = state.get("analysis_report", "")
        root_cause = state.get("root_cause", "분석 중...")
        suggested_solution = state.get("suggested_solution", "")

        # Use LLM to create user-friendly summary
        try:
            prompt = ChatPromptTemplate.from_messages(
                [
                    (
                        "system",
                        """당신은 친절한 Airflow 모니터링 어시스턴트입니다.
사용자에게 오류 상황을 설명하고, 해결 방법을 제안하며, 
다음 액션에 대한 승인을 요청하는 메시지를 작성하세요.

메시지는 다음을 포함해야 합니다:
1. 오류 상황 요약 (간단명료하게)
2. 근본 원인 설명
3. 제안하는 해결 방법
4. 사용자 액션 옵션 (재실행, 수동 처리 등)

친절하고 전문적인 톤으로 작성하되, 기술적 세부사항은 
이해하기 쉽게 설명하세요.
""",
                    ),
                    (
                        "human",
                        """다음 정보를 바탕으로 사용자에게 보낼 메시지를 작성해주세요:

DAG: {dag_id}
Task: {task_id}
Run: {dag_run_id}

근본 원인: {root_cause}

분석 보고서:
{analysis_report}

사용자가 선택할 수 있는 옵션을 명확히 제시하고,
각 옵션의 의미를 설명해주세요.
""",
                    ),
                ]
            )

            chain = prompt | self.llm

            response = chain.invoke(
                {
                    "dag_id": dag_id,
                    "task_id": task_id,
                    "dag_run_id": dag_run_id,
                    "root_cause": root_cause,
                    "analysis_report": analysis_report[:1000],  # Limit length
                }
            )

            message = response.content

        except Exception as e:
            logger.error(f"Error generating user message: {e}")
            # Fallback to simple message
            message = f"""
## 🚨 Airflow Task 실패 감지

**DAG**: {dag_id}  
**Task**: {task_id}  
**Run ID**: {dag_run_id}

### 📊 분석 결과
{root_cause}

### 💡 제안 사항
{suggested_solution}

"""

        # Add action options
        message += """

---

### 🔧 다음 액션을 선택해주세요:

1. **재실행 (Clear & Retry)**: Task를 Clear하여 자동으로 재실행합니다.
2. **수동 처리**: 코드나 설정을 수정한 후 직접 처리하겠습니다.
3. **분석 보고서 확인**: 전체 분석 보고서를 먼저 확인하겠습니다.

어떤 액션을 수행할까요?
"""

        return message

    def _process_user_input(self, state: AgentState) -> Dict[str, Any]:
        """
        Process user input and determine next action

        Args:
            state: State with user input

        Returns:
            Updated state with action decision
        """
        user_input = state.get("user_input", "").strip().lower()

        logger.info(f"Processing user input: {user_input}")

        # Parse user decision
        if any(
            keyword in user_input
            for keyword in ["재실행", "clear", "retry", "다시", "1"]
        ):
            final_action = "CLEAR_TASK"
            action_message = "✅ Task를 Clear하여 재실행하겠습니다."

        elif any(
            keyword in user_input
            for keyword in ["수동", "manual", "직접", "2", "건너뛰", "skip"]
        ):
            final_action = "SKIP"
            action_message = "⏭️  수동 처리를 위해 건너뜁니다."

        elif any(
            keyword in user_input
            for keyword in ["보고서", "분석", "report", "3", "확인"]
        ):
            final_action = "SHOW_REPORT"
            action_message = "📄 전체 분석 보고서를 표시합니다."

        else:
            # Default: treat as request for more info
            final_action = "SHOW_REPORT"
            action_message = "📄 입력을 이해하지 못했습니다. 전체 보고서를 표시합니다."

        return {
            "final_action": final_action,
            "action_result": action_message,
            "requires_user_input": False,
            "current_agent": self.agent_type.value,
        }
