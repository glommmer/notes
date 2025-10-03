import os
import time
import requests
import typing as t
from functools import wraps
from collections import defaultdict
from typing import Literal
from typing_extensions import TypedDict
from dotenv import load_dotenv
from langchain_openai import AzureChatOpenAI
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from langgraph.types import Command
from langgraph.prebuilt import create_react_agent
from langgraph.graph import StateGraph, START, END, MessagesState
from langgraph.checkpoint.memory import MemorySaver


# API 키 등 환경설정
load_dotenv()
# AOAI_ENDPOINT = os.getenv("AOAI_ENDPOINT")
# AOAI_API_KEY = os.getenv("AOAI_API_KEY")
# AOAI_DEPLOY_GPT4O = os.getenv("AOAI_DEPLOY_GPT4O")
# AOAI_DEPLOY_GPT4O_MINI = os.getenv("AOAI_DEPLOY_GPT4O_MINI")
# AOAI_DEPLOY_EMBED_3_LARGE = os.getenv("AOAI_DEPLOY_EMBED_3_LARGE")
# AOAI_DEPLOY_EMBED_3_SMALL = os.getenv("AOAI_DEPLOY_EMBED_3_SMALL")
# AOAI_DEPLOY_EMBED_ADA = os.getenv("AOAI_DEPLOY_EMBED_ADA")
API_ENDPOINT = os.getenv("API_ENDPOINT")
API_SECRET = os.getenv("API_SECRET")
API_VERSION = os.getenv("API_VERSION")
AIRFLOW_URL = os.getenv("AIRFLOW_URL")
AIRFLOW_USERNAME = os.getenv("AIRFLOW_USERNAME")
AIRFLOW_PASSWORD = os.getenv("AIRFLOW_PASSWORD")

# llm 객체 생성
# llm = AzureChatOpenAI(
#     azure_endpoint=AOAI_ENDPOINT,
#     azure_deployment=AOAI_DEPLOY_GPT4O,
#     api_version="2024-10-21",
#     api_key=AOAI_API_KEY
# )
llm = ChatOpenAI(model="ax4", base_url=API_ENDPOINT, api_key=API_SECRET)


class AirflowAuthManager:
    def __init__(self, airflow_url, username, password):
        self.airflow_url = airflow_url
        self.username = username
        self.password = password
        self._token = None
        self._token_expiry = 0

    def get_jwt_token(self):
        token_url = f"{self.airflow_url}/auth/token"
        payload = {"username": self.username, "password": self.password}
        response = requests.post(token_url, json=payload)
        access_token = response.json().get("access_token", None)
        if not access_token:
            print(f"토큰 생성 실패: {response.status_code} - {response.text}")
            return None
        else:
            return access_token

    def get_valid_token(self):
        """JWT 토큰을 가져오거나 갱신합니다."""
        current_time = time.time()

        # 토큰이 없거나 만료 5분 전이면 갱신
        if not self._token or current_time >= (self._token_expiry - 300):
            self._token = self.get_jwt_token()
            if self._token:
                # JWT 토큰의 기본 만료 시간은 24시간 (86400초)
                self._token_expiry = current_time + 86400
            else:
                raise Exception("JWT 토큰 생성에 실패했습니다.")

        return self._token


def get_task_instances_in_group(
    airflow_base_url: str,
    dag_id: str,
    dag_run_id: str,
    task_group_id: str,
) -> t.List[t.Dict]:
    """[Helper] 특정 Task Group 내의 모든 Task Instance를 가져옵니다."""
    instances_in_group = []
    endpoint = (
        f"{airflow_base_url}/{API_VERSION}/dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances"
    )
    offset = 0
    limit = 100
    while True:
        # JWT 토큰 사용
        token = auth_manager.get_valid_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        params = {"limit": limit, "offset": offset}
        try:
            response = requests.get(endpoint, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()
            task_instances = data.get("task_instances", [])
            if not task_instances:
                break
            # 클라이언트 측에서 Task Group에 속한 Task만 필터링
            for ti in task_instances:
                if f"{task_group_id}." in ti.get("task_id", ""):
                    instances_in_group.append(ti)
            offset += len(task_instances)
        except requests.exceptions.RequestException as e:
            print(f"Error fetching tasks for group '{task_group_id}': {e}")
            raise
    return instances_in_group


def find_failed_groups_and_their_tasks(
    task_id_contains: str,
    logical_date_gte: t.Optional[str] = None,
    logical_date_lte: t.Optional[str] = None,
) -> t.Dict[str, t.List[t.Dict]]:
    """
    실패한 Task가 포함된 Task Group을 찾고, 해당 그룹 내의 모든 Task Instance 목록을 반환합니다.

    Args:
        task_id_contains (str): 검색할 Task ID에 포함된 문자열
        logical_date_gte (t.Optional[str]): 조회 시작 논리적 날짜 (ISO 8601 형식)
        logical_date_lte (t.Optional[str]): 조회 종료 논리적 날짜 (ISO 8601 형식)

    Returns:
        t.Dict[str, t.List[t.Dict]]: Task Group 식별자를 Key로,
                                     해당 그룹 내 Task Instance 리스트를 Value로 갖는 딕셔너리.
    """
    airflow_base_url = AIRFLOW_URL
    # 1단계: 실패한 Task가 속한 Task Group 식별
    print("--- 1단계: 실패 Task가 포함된 Task Group 식별 중 ---")
    failed_task_groups = set()
    find_endpoint = f"{airflow_base_url}/{API_VERSION}/dags/~/dagRuns/~/taskInstances"
    params = {"state": ["failed"]}
    if logical_date_gte:
        params["logical_date_gte"] = logical_date_gte
    if logical_date_lte:
        params["logical_date_lte"] = logical_date_lte
    offset = 0
    limit = 100
    while True:
        # JWT 토큰 사용
        token = auth_manager.get_valid_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        params["offset"] = offset
        response = requests.get(find_endpoint, params=params, headers=headers)
        response.raise_for_status()
        data = response.json()
        task_instances = data.get("task_instances", [])
        if not task_instances:
            break
        for ti in task_instances:
            task_id = ti.get("task_id")
            if task_id and task_id_contains in task_id:
                last_dot_index = task_id.rfind(".")
                if last_dot_index != -1:
                    task_group_id = task_id[:last_dot_index]
                    failed_task_groups.add(
                        (ti.get("dag_id"), ti.get("dag_run_id"), task_group_id)
                    )
        offset += len(task_instances)
        if offset >= data.get("total_entries", 0):
            break
    if not failed_task_groups:
        print("✔️ 조건에 맞는 실패 Task Group을 찾지 못했습니다.")
        return {}
    print(f"✔️ 총 {len(failed_task_groups)}개의 고유한 Task Group을 식별했습니다.")
    # 2단계: 식별된 각 Task Group에 대해 모든 Task Instance 조회
    print("\n--- 2단계: 식별된 Group 내 모든 Task Instance 조회 중 ---")
    final_results = defaultdict(list)
    for dag_id, dag_run_id, task_group_id in failed_task_groups:
        print(f" -> '{task_group_id}' 그룹의 Task들을 가져오는 중...")
        instances = get_task_instances_in_group(
            airflow_base_url, dag_id, dag_run_id, task_group_id
        )
        group_key = f"{dag_id}::{dag_run_id}::{task_group_id}"
        final_results[group_key] = instances
    return dict(final_results)


def clear_specific_task_instances(
    dag_id: str,
    dag_run_id: str,
    task_ids: t.List[str],
    dry_run: bool = False,
) -> t.Dict:
    """
    특정 DAG Run에 속한 지정된 Task Instance 목록을 Clear합니다.

    Args:
        dag_id (str): 대상 DAG의 ID
        dag_run_id (str): 대상 DAG Run의 ID
        task_ids (t.List[str]): Clear할 Task들의 ID 리스트
        dry_run (bool): True로 설정하면 실제로 실행하지 않고 결과만 시뮬레이션합니다.

    Returns:
        t.Dict: Clear 작업 결과 (Clear된 Task Instance 정보 포함)
    """
    airflow_base_url = AIRFLOW_URL
    endpoint = f"{airflow_base_url}/{API_VERSION}/dags/{dag_id}/clearTaskInstances"
    payload = {
        "dag_run_id": dag_run_id,
        "task_ids": task_ids,
        "dry_run": dry_run,
        "only_failed": False,
    }
    print(
        f"🔄 DAG '{dag_id}'의 Run '{dag_run_id}'에 속한 Task {len(task_ids)}개를 Clear하는 중..."
    )
    if dry_run:
        print(" (Dry Run 모드: 실제로 실행되지 않습니다)")
    try:
        # JWT 토큰 사용
        token = auth_manager.get_valid_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        response = requests.post(endpoint, json=payload, headers=headers)
        response.raise_for_status()
        result_data = response.json()
        return result_data
    except requests.exceptions.RequestException as e:
        print(f"❌ Clear 작업 중 오류 발생: {e.response.text if e.response else e}")
        raise


# 전역 인스턴스 생성
auth_manager = AirflowAuthManager(AIRFLOW_URL, AIRFLOW_USERNAME, AIRFLOW_PASSWORD)
checkpointer = MemorySaver()
# members = ["airflow", "sftp", "ftp", "eai", ...]
members = ["airflow"]
options = members + ["FINISH"]

# Supervisor 프롬프트
system_prompt = (
    "You are a supervisor tasked with managing a conversation between the"
    f" following workers: {members}. Given the following user request,"
    " respond with the worker to act next. Each worker will perform a"
    " task and respond with their results and status. When finished,"
    " respond with FINISH."
)


class Router(TypedDict):
    """Worker to route to next. If no workers needed, route to FINISH."""

    # 'Router' 라는 이름의 데이터 구조 정의 -> 'next' 라는 객체를 가지고 있어야 함
    # Literal 타입은 변수가 가질 수 있는 값을 미리 정해진 정확한 상수 값들로 제한
    next: Literal[*options]


class State(MessagesState):
    # 다음 업무를 수행할 Agent가 누구인지 설정하기 위해 next가 추가됨
    next: str


def supervisor_node(state: State) -> Command[Literal[*members, "__end__"]]:
    # Return 값이 State고 정해진 edge로 가는 것이 아닌 Command가 반환됨
    messages = [
        {"role": "system", "content": system_prompt},
    ] + state["messages"]
    response = llm.with_structured_output(Router).invoke(messages)
    goto = response["next"]
    if goto == "FINISH":
        goto = END
    return Command(goto=goto, update={"next": goto})


def find_failed_groups_and_their_tasks_tool(
    task_id_contains: str,
    logical_date_gte: t.Optional[str] = None,
    logical_date_lte: t.Optional[str] = None,
) -> t.Dict[str, t.List[t.Dict]]:
    """Agent에서 사용할 도구 - JWT 토큰 자동 처리"""
    return find_failed_groups_and_their_tasks(
        task_id_contains=task_id_contains,
        logical_date_gte=logical_date_gte,
        logical_date_lte=logical_date_lte,
    )


def clear_specific_task_instances_tool(
    dag_id: str,
    dag_run_id: str,
    task_ids: t.List[str],
    dry_run: bool = False,
) -> t.Dict:
    """Agent에서 사용할 도구 - JWT 토큰 자동 처리"""
    return clear_specific_task_instances(
        dag_id=dag_id,
        dag_run_id=dag_run_id,
        task_ids=task_ids,
        dry_run=dry_run,
    )


airflow_agent = create_react_agent(
    llm,
    tools=[find_failed_groups_and_their_tasks_tool, clear_specific_task_instances_tool],
    prompt="""
    # Airflow 실패 처리 에이전트 프롬프트

    ## 역할 및 목표

    당신은 전문 Airflow 어시스턴트 에이전트입니다. 당신의 주요 목표는 사용자가 사전 정의된 도구(tool)를 사용하여 Apache Airflow 환경의 실패한 Task Instance를 식별하고 해결하도록 돕는 것입니다.

    당신은 먼저 문제를 진단(실패 탐색)하고, 사용자의 **명시적인 확인**을 받은 후에 해결책(실패 Task clear)을 실행해야 합니다.

    ***

    ## 사용 가능한 도구 (Available Tools)

    당신은 아래 두 가지 도구만 사용할 수 있습니다.

    ### 1. `find_failed_groups_and_their_tasks_tool`

    -   **설명**: Task ID에 특정 키워드를 포함하고 'failed' 상태인 Task Instance를 찾습니다. 이 도구는 실패한 Task가 속한 Task Group을 식별하고, 해당 DAG Run의 해당 Task Group 내에 있는 **모든** Task Instance(성공, 실패 등 모든 상태 포함)의 목록을 반환합니다.
    -   **파라미터**:
        -   `task_id_contains` (str): 검색할 Task ID에 포함된 키워드 문자열.
        -   `logical_date_gte` (str, 선택 사항): 조회 시작 시간 (ISO 8601 형식, 예: `2025-10-02T00:00:00Z`).
        -   `logical_date_lte` (str, 선택 사항): 조회 종료 시간 (ISO 8601 형식, 예: `2025-10-02T23:59:59Z`).

    ### 2. `clear_specific_task_instances_tool`

    -   **설명**: 특정 DAG Run 내에서 지정된 Task Instance 목록의 상태를 'clear'합니다. 이 작업은 Task를 재실행하도록 만들 수 있는 **실행 작업**이므로, 반드시 사용자의 확인을 받은 후에만 사용해야 합니다.
    -   **파라미터**:
        -   `dag_id` (str): 대상 DAG의 ID.
        -   `dag_run_id` (str): 대상 DAG Run의 ID.
        -   `task_ids` (List[str]): Clear할 Task들의 ID 목록.

    ***

    ## 작업 흐름 및 지시사항

    당신은 다음의 작업 흐름을 반드시 따라야 합니다.

    1.  **요청 파악**: 사용자의 요청을 주의 깊게 듣고 "찾아줘", "검색해줘"와 같은 탐색 요청인지 파악합니다.
    2.  **실패 탐색**: 사용자가 실패 조사를 요청하면, `find_failed_groups_and_their_tasks_tool` 도구를 사용합니다. 사용자가 제공하는 키워드나 날짜 범위를 파라미터로 정확히 전달해야 합니다.
    3.  **결과 요약**: 탐색 결과를 사용자에게 명확하게 요약하여 보고합니다. 어떤 Task Group에서 몇 개의 Task가 발견되었고, 그중 실패한 Task는 무엇인지 등을 간결하게 설명해야 합니다.
    4.  **실행 확인 (매우 중요)**: Task를 clear하기 전, **반드시** 사용자에게 명시적인 실행 허가를 받아야 합니다. 예를 들어, **"위에서 찾은 Task들을 clear 할까요?"** 와 같이 명확하게 질문해야 합니다.
    5.  **작업 실행**: 사용자가 "네", "실행하세요", "clear 해주세요" 등으로 긍정적으로 답변하면, `clear_specific_task_instances_tool` 도구를 호출합니다. 이때, 이전 `find` 단계에서 얻은 `dag_id`, `dag_run_id`, `task_ids` 정보를 정확하게 파라미터로 사용해야 합니다.
    6.  **최종 보고**: Clear 작업의 결과를 사용자에게 보고하고 대화를 마무리합니다.

    ***

    ## 제약 조건

    -   주어진 두 가지 도구 외에 다른 기능이나 정보를 아는 것처럼 행동하지 마세요.
    -   사용자의 요청이 모호할 경우, 추측하지 말고 되물어서 명확히 하세요.
    -   **절대로 사용자의 허가 없이 `clear_specific_task_instances_tool` 도구를 호출하지 마세요.**

    ***

    ## 대화 예시

    **User**:
    어제 실패한 태스크 중에 'user_processing' 이라는 키워드가 들어간 애들 좀 찾아줘.

    **Agent (Thought)**:
    사용자가 '어제'라는 시간 범위와 'user_processing'이라는 키워드로 실패한 태스크를 찾아달라고 요청했다. `find_failed_groups_and_their_tasks_tool` 도구를 사용해야겠다. `logical_date`는 어제 날짜로 설정한다.
    > Tool Call: `find_failed_groups_and_their_tasks_tool(task_id_contains='user_processing', logical_date_gte='2025-10-02T00:00:00Z', logical_date_lte='2025-10-02T23:59:59Z')`

    **Agent (Response)**:
    네, 어제 날짜로 'user_processing'을 포함하는 실패 Task를 찾았습니다.
    `user_processing_group` Task Group에서 총 5개의 Task가 발견되었으며, 그중 `user_processing_group.transform` Task가 'failed' 상태입니다. 전체 목록은 다음과 같습니다.
    -   `user_processing_group.extract` (state: success)
    -   `user_processing_group.transform` (state: failed)
    -   `user_processing_group.load_summary` (state: upstream_failed)
    -   `user_processing_group.load_details` (state: upstream_failed)
    -   `user_processing_group.validate` (state: upstream_failed)

    이 Task들을 clear 할까요?

    **User**:
    네, clear 해주세요.

    **Agent (Thought)**:
    사용자가 clear를 확인했다. 이전 단계에서 얻은 정보를 바탕으로 `clear_specific_task_instances_tool` 도구를 호출한다.
    > Tool Call: `clear_specific_task_instances_tool(dag_id='user_pipeline', dag_run_id='scheduled__2025-10-02T...', task_ids=['user_processing_group.extract', 'user_processing_group.transform', ...])`

    **Agent (Response)**:
    네, 요청하신 `user_processing_group`에 속한 5개 Task의 상태를 clear 했습니다. 스케줄러에 의해 곧 재실행될 것입니다.
    """,
)


def airflow_node(state: State) -> Command[Literal["supervisor"]]:
    result = airflow_agent.invoke(state)
    return Command(
        update={
            "messages": [
                HumanMessage(
                    content=result["messages"][-1].content,
                    name="airflow",
                ),
            ],
        },
        goto="supervisor",  # 업무 수행 후, goto를 슈퍼바이저로 설정해 보고할 수 있도록
    )


builder = StateGraph(State)
builder.add_edge(START, "supervisor")
builder.add_node("supervisor", supervisor_node)
builder.add_node("airflow", airflow_node)
# builder.add_node("sftp", airflow_node)
# builder.add_node("ftp", airflow_node)
# builder.add_node("eai", airflow_node)
graph = builder.compile(checkpointer=checkpointer)
config = {"configurable": {"thread_id": "123456"}, "recursion_limit": 10}

for s in graph.stream(
    {
        "messages": [
            (
                "user",
                "'task_2_fails'가 들어간 airflow 작업이 실패했으면 묻지 말고 재수행해줘, 시작시간은 '2025-10-01T00:00:00Z'이고 종료시간은 '2025-10-01T23:59:59Z'야",
            )
        ]
    },
    config=config,
    subgraphs=True,
):
    print(s)
    print("----")
