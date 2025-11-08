"""
Workflow State Definition - Shared state across all agents
"""

from typing import TypedDict, Optional, List, Dict, Any, Literal
from enum import Enum


class AgentType(str, Enum):
    """
    Agent type identifiers

    *Enum 사용 시 장점
    - 컴파일 타임에 오류 발견
      <예시 1> agent = AgentType.MONITRO → AttributeError 발생
      <예시 2> agent = "MONITRO_AGENT" → 문법 상 오류 없으므로 버그 찾기 힘듦
    - 유지보수 간편 → Enum 정의만 수정하면 모든 참조 업데이트
    - 타입 체크(정적 분석)
      <예시 1> def set_agent(agent: AgentType): set_agent("WRONG") → 에러 발생
      <예시 2> def set_agent(agent: str): set_agent("WRONG") → 에러 없음

    **Magic String
    - 코드에 하드코딩된 의미 있는 문자열 상수
      > 코드를 읽는 사람이 그 값의 출처나 의미를 즉시 알 수 없음
      > 오타가 있어도 컴파일/정적 분석 단계에서 잡기 힘듦
      > 동일한 문자열을 여러 부분에서 중복 사용 → 변경 시 누락 위험

    ***Enum을 str와 함께 상속하는 이유
    - JSON/API 직렬화 자동 처리
      <예시> json.dumps({"agent": AgentType.ACTION}) → {"agent": "ACTION_AGENT"}
    - 문자열 메서드 사용 가능 / 문자열 비교 가능
      <예시 1> AgentType.ACTION.lower() + "_TEST" → "action_agent_TEST"
      <예시 2> AgentType.ACTION.startswith("A") → True
      <예시 3> if AgentType.ACTION == "ACTION_AGENT": print(True) → True
    """

    MONITOR = "MONITOR_AGENT"
    ANALYZER = "ANALYZER_AGENT"
    INTERACTION = "INTERACTION_AGENT"
    ACTION = "ACTION_AGENT"


class AgentState(TypedDict):
    """
    Global state shared across all agents in the workflow

    This state is passed through the entire LangGraph workflow
    and updated by each agent node.

    LangGraph 멀티 에어진트 워크플로우에서 모든 에이전트가 공유하는 전역 상태 저장소
    여러 에이전트가 순차적으로 작업하면서 정보를 읽고, 분석하고, 업데이트하는 공유 공간

    *TypedDict
    - 타입 힌트 전용 도구 → 정의되지 않은 형태로 사용 시 경고 발생
    - 런타임에서는 일반 딕셔너리로 동작
    """

    # Airflow identifiers
    dag_id: Optional[str]
    dag_run_id: Optional[str]
    task_id: Optional[str]
    try_number: Optional[int]
    target_date: Optional[str]

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
        target_date=None,
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


if __name__ == "__main__":
    # 1. 에이전트 타입 지정
    current_agent = AgentType.MONITOR
    print(current_agent, type(current_agent))

    # 2. 타입 체크와 비교
    if current_agent == AgentType.MONITOR:
        print("Monitoring system...")

    # 3. 이름과 값 접근
    print(current_agent.name)  # "MONITOR"
    print(current_agent.value)  # "MONITOR_AGENT"

    # 4. 문자열로 직접 사용 (str 상속 덕분)
    def process_agent(agent_type: AgentType):
        log_message = f"Processing {agent_type}"  # 자동 문자열 변환
        print(log_message)

    process_agent(current_agent)

    # 5. JSON 직렬화 (str 상속 덕분)
    import json

    config = {"agent": AgentType.ANALYZER}
    json_data = json.dumps(config, default=str)  # 에러 없이 처리
    print(json_data)

    # 6. 상태 초기화
    initialized_state = create_initial_state()
    print(initialized_state)
