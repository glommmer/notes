"""
Chat Interface Component - Handles streaming updates from server
"""

import json
import os
import streamlit as st
import requests
import logging
from datetime import datetime
from pathlib import Path
from sseclient import SSEClient
from typing import Optional
from app.utils.state_manager import add_message, get_messages


LOG_DIR = Path(__file__).parent.parent.parent / "logs" / "streamlit"
LOG_DIR.mkdir(parents=True, exist_ok=True)


def setup_file_logger():
    """파일 로거 설정"""
    logger = logging.getLogger("streamlit_debug")
    logger.setLevel(logging.DEBUG)

    # 기존 핸들러 제거 (중복 방지)
    if logger.handlers:
        logger.handlers.clear()

    # 파일 핸들러 추가 (날짜별 로그 파일)
    log_filename = LOG_DIR / f"debug_{datetime.now().strftime('%Y%m%d')}.log"
    file_handler = logging.FileHandler(log_filename, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)

    # 포맷 설정
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


# 로거 초기화
logger = setup_file_logger()
logger.info("=" * 80)
logger.info("Streamlit application started")
logger.info("=" * 80)

# Get API base URL from environment
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")


class CustomSSEClient:
    """
    Custom SSE client for requests.Response objects

    FastAPI에서 보낸 Server-Sent Events(SSE)를 파싱하는 클라이언트
    - FastAPI 서버 (SSE 스트림 전송)
      → requests.Response (HTTP 응답 스트림)
      → CustomSSEClient (SSE 형식 파싱)

    *SSE 포맷 예시
    - data: {"type": "start", "message": "🚀 워크플로우 시작..."}
    - data: {"type": "agent_update", "agent": "MONITOR", "message": "🔍 Airflow 모니터링 중..."}
    """

    def __init__(self, response):
        self.response = response  # HTTP 응답 객체 (requests.Reponse)
        self.logger = logging.getLogger("streamlit_debug")

    def events(self):
        """Generator that yields SSE events"""
        buffer = ""  # 버퍼: 읽은 데이터 임시 저장
        event_data = {}  # 현재 파싱 중인 이벤트 정보

        for chunk in self.response.iter_content(chunk_size=None, decode_unicode=True):
            if not chunk:
                continue

            buffer += chunk

            while "\n" in buffer:
                # buffer의 첫 번째 줄을 추출하고 나머지는 buffer에 유지
                line, buffer = buffer.split("\n", 1)
                line = line.rstrip()

                if not line:
                    # 빈 줄은 이벤트 종료 신호
                    if event_data.get("data"):
                        yield type("Event", (), event_data)()
                    event_data = {}
                    continue

                # <예시> 'data: {"type": "start"}' → '{"type": "start"}'
                if line.startswith("data:"):
                    event_data["data"] = event_data.get("data", "") + line[5:].lstrip()
                # <예시> "event: new_message" → "new_message"
                elif line.startswith("event:"):
                    event_data["event"] = line[6:].lstrip()
                # <예시> "id: 1234" → "12345"
                elif line.startswith("id:"):
                    event_data["id"] = line[3:].lstrip()
                # <예시> "retry: 5000" → 5000
                elif line.startswith("retry:"):
                    event_data["retry"] = int(line[6:].lstrip())


def stream_workflow_updates(
    dag_id: Optional[str] = None,
    dag_run_id: Optional[str] = None,
    task_id: Optional[str] = None,
    user_input: Optional[str] = None,
    session_id: Optional[str] = None,
):
    """
    Stream workflow updates from FastAPI server

    Args:
        dag_id: Optional DAG identifier
        dag_run_id: Optional DAG run identifier
        task_id: Optional task identifier
        user_input: Optional user input
        session_id: Optional session identifier

    Yields:
        Event dictionaries from server
    """
    url = f"{API_BASE_URL}/api/v1/agent/stream"

    payload = {
        "dag_id": dag_id,
        "dag_run_id": dag_run_id,
        "task_id": task_id,
        "user_input": user_input,
        "session_id": session_id,
    }

    # Remove None values
    payload = {k: v for k, v in payload.items() if v is not None}

    logger.info("=" * 60)
    logger.info("Starting workflow update stream")
    logger.info(f"URL: {url}")
    logger.info(f"Payload: {json.dumps(payload, indent=2, ensure_ascii=False)}")
    logger.info("=" * 60)

    try:
        response = requests.post(
            url, json=payload, stream=True, headers={"Accept": "text/event-stream"}
        )

        logger.info(f"Response type: {type(response)}")
        logger.info(f"Response class: {response.__class__.__name__}")
        logger.info(f"Status code: {response.status_code}")
        logger.info(f"Response headers: {dict(response.headers)}")
        logger.info(f"Response encoding: {response.encoding}")

        if response.status_code != 200:
            yield {
                "type": "error",
                "message": f"서버 오류: HTTP {response.status_code}",
            }
            return

        # Parse SSE stream
        logger.info("Initializing SSEClient...")
        try:
            client = CustomSSEClient(response)
            logger.info(f"SSEClient created successfully: {type(client)}")
        except Exception as sse_error:
            logger.error(f"Failed to create SSEClient: {sse_error}", exc_info=True)
            yield {
                "type": "error",
                "message": f"SSE 클라이언트 초기화 실패: {str(sse_error)}",
            }
            return

        event_count = 0
        logger.info("Starting event iteration...")

        for event in client.events():
            event_count += 1
            logger.info(f"Event #{event_count} received")
            logger.debug(f"Event type: {type(event)}")
            logger.debug(f"Event attributes: {dir(event)}")

            if event.data:
                logger.debug(f"Event data (raw): {event.data[:500]}...")  # 처음 500자만

                try:
                    data = json.loads(event.data)
                    logger.info(
                        f"Event data (parsed): {json.dumps(data, indent=2, ensure_ascii=False)}"
                    )
                    yield data
                except json.JSONDecodeError as json_error:
                    logger.error(f"JSON parse error: {json_error}")
                    logger.error(f"Raw data: {event.data}")
                    continue
            else:
                logger.warning(f"Event #{event_count} has no data")

        logger.info(f"Stream completed. Total events: {event_count}")

    except requests.RequestException as e:
        error_msg = f"연결 오류: {str(e)}"
        logger.error(error_msg, exc_info=True)
        logger.error(f"Request URL: {url}")
        logger.error(f"Request payload: {payload}")
        yield {"type": "error", "message": f"연결 오류: {str(e)}"}
    except Exception as e:
        error_msg = f"예상치 못한 오류: {str(e)}"
        logger.error(error_msg, exc_info=True)
        logger.error(f"Exception type: {type(e)}")
        yield {"type": "error", "message": f"예상치 못한 오류: {str(e)}"}

        import traceback

        logger.error(f"Full traceback:\n{traceback.format_exc()}")

        yield {"type": "error", "message": error_msg}


def render_agent_message(
    agent: str, message: str, data: dict = None, in_sidebar: bool = False
):
    """
    Render an agent message in the chat interface

    Args:
        agent: Agent name
        message: Message text
        data: Optional additional data
    """
    # Map agent to avatar emoji
    avatar_map = {
        "MONITOR": "🔍",
        "ANALYZER": "🔬",
        "INTERACTION": "💬",
        "ACTION": "⚡",
    }

    avatar = avatar_map.get(agent, "🤖")

    with st.chat_message("assistant", avatar=avatar):
        st.markdown(f"**{agent}**: {message}")

        if data:
            # Display relevant data
            if agent == "MONITOR":
                if data.get("dag_id"):
                    st.info(
                        f"📊 DAG: `{data['dag_id']}`\n\n"
                        f"🔧 Task: `{data.get('task_id', 'N/A')}`"
                    )
                if data.get("error_message"):
                    st.warning(data["error_message"])

            elif agent == "ANALYZER":
                if data.get("root_cause"):
                    st.error(f"**근본 원인**: {data['root_cause']}")

                if data.get("analysis_report"):
                    if in_sidebar:
                        st.markdown("**📄 전체 분석 보고서**")
                        st.markdown(data["analysis_report"])
                    else:
                        with st.expander("📄 전체 분석 보고서 보기"):
                            st.markdown(data["analysis_report"])

            elif agent == "INTERACTION":
                if data.get("user_question"):
                    st.info(data["user_question"])
                    st.session_state.waiting_for_input = True
                    st.session_state.current_question = data["user_question"]

            elif agent == "ACTION":
                if data.get("action_result"):
                    st.success(data["action_result"])

                if data.get("is_resolved"):
                    st.balloons()
                    st.session_state.workflow_complete = True


def render_chat_interface():
    """
    Render the main chat interface
    """
    st.title("🤖 Airflow 모니터링 에이전트")

    st.markdown(
        """
    이 에이전트는 Apache Airflow의 실패한 작업을 자동으로 감지하고 분석하여
    해결 방법을 제안합니다.
    """
    )

    # Display chat messages
    messages = get_messages()
    for message in messages:
        role = message["role"]
        content = message["content"]

        if role == "user":
            with st.chat_message("user", avatar="👤"):
                st.markdown(content)
        else:
            with st.chat_message("assistant", avatar="🤖"):
                st.markdown(content)

    # Input section
    with st.container():
        col1, col2 = st.columns([3, 1])

        with col1:
            # Show different input based on state
            if st.session_state.get("waiting_for_input"):
                user_input = st.chat_input(
                    "답변을 입력하세요 (예: 재실행, 수동, 보고서)..."
                )
            else:
                user_input = st.chat_input(
                    "모니터링을 시작하려면 메시지를 입력하세요..."
                )

        with col2:
            if st.button("🔄 새로 시작", use_container_width=True):
                from app.utils.state_manager import reset_session_state

                reset_session_state()
                st.rerun()

    # Handle user input
    if user_input:
        # Add user message to chat
        add_message("user", user_input)

        with st.chat_message("user", avatar="👤"):
            st.markdown(user_input)

        # Process based on current state
        if st.session_state.get("waiting_for_input"):
            # Send user input to workflow
            process_user_response(user_input)
        else:
            # Start new monitoring workflow
            start_monitoring_workflow(user_input)


def start_monitoring_workflow(initial_message: str):
    """
    Start a new monitoring workflow

    Args:
        initial_message: Initial user message
    """
    import uuid

    # Generate session ID
    session_id = str(uuid.uuid4())
    st.session_state.current_session_id = session_id
    st.session_state.monitoring_active = True

    # Show processing message
    with st.spinner("🔍 Airflow 모니터링 시작..."):
        # Stream workflow updates
        for event in stream_workflow_updates(session_id=session_id):
            process_workflow_event(event)

    st.session_state.monitoring_active = False


def process_user_response(user_input: str):
    """
    Process user response and continue workflow

    Args:
        user_input: User's input text
    """
    session_id = st.session_state.get("current_session_id")
    dag_id = st.session_state.get("dag_id")
    dag_run_id = st.session_state.get("dag_run_id")
    task_id = st.session_state.get("task_id")

    st.session_state.waiting_for_input = False

    with st.spinner("⚡ 액션 처리 중..."):
        # Stream workflow updates with user input
        for event in stream_workflow_updates(
            dag_id=dag_id,
            dag_run_id=dag_run_id,
            task_id=task_id,
            user_input=user_input,
            session_id=session_id,
        ):
            process_workflow_event(event)


def process_workflow_event(event: dict, in_sidebar: bool = False):
    """
    Process a workflow event from the server

    Args:
        event: Event dictionary
    """
    event_type = event.get("type")

    if event_type == "agent_update":
        agent = event.get("agent", "SYSTEM")
        message = event.get("message", "")
        data = event.get("data", {})

        # Store DAG identifiers
        if data.get("dag_id"):
            st.session_state.dag_id = data["dag_id"]
        if data.get("dag_run_id"):
            st.session_state.dag_run_id = data["dag_run_id"]
        if data.get("task_id"):
            st.session_state.task_id = data["task_id"]

        # Render message
        render_agent_message(agent, message, data, in_sidebar=in_sidebar)

        # Add to history
        add_message("assistant", f"**{agent}**: {message}")

    elif event_type == "complete":
        message = event.get("message", "완료")
        st.success(message)
        add_message("assistant", message)
        st.session_state.workflow_complete = True

    elif event_type == "error":
        message = event.get("message", "오류 발생")
        st.error(message)
        add_message("assistant", f"❌ {message}")


def render_sidebar_controls():
    """
    Render sidebar with advanced controls
    """
    with st.sidebar:
        st.header("⚙️ 설정")

        with st.expander("고급 옵션"):
            st.text_input(
                "특정 DAG ID",
                key="sidebar_dag_id",
                help="특정 DAG를 모니터링하려면 입력하세요",
            )

            st.text_input(
                "특정 DAG Run ID",
                key="sidebar_dag_run_id",
                help="특정 DAG Run을 분석하려면 입력하세요",
            )

            st.text_input(
                "특정 Task ID",
                key="sidebar_task_id",
                help="특정 Task를 분석하려면 입력하세요",
            )

            if st.button("특정 Task 분석", use_container_width=True):
                dag_id = st.session_state.get("sidebar_dag_id")
                dag_run_id = st.session_state.get("sidebar_dag_run_id")
                task_id = st.session_state.get("sidebar_task_id")

                if dag_id and dag_run_id and task_id:
                    analyze_specific_task(dag_id, dag_run_id, task_id)
                else:
                    st.error("모든 필드를 입력해주세요")

        st.divider()

        st.header("📊 상태")
        if st.session_state.get("monitoring_active"):
            st.info("🟢 모니터링 활성화")
        else:
            st.info("⚪ 대기 중")

        if st.session_state.get("current_session_id"):
            st.caption(f"Session: {st.session_state.current_session_id[:8]}...")


def analyze_specific_task(dag_id: str, dag_run_id: str, task_id: str):
    """
    Analyze a specific task

    Args:
        dag_id: DAG identifier
        dag_run_id: DAG run identifier
        task_id: Task identifier
    """
    import uuid

    session_id = str(uuid.uuid4())
    st.session_state.current_session_id = session_id
    st.session_state.dag_id = dag_id
    st.session_state.dag_run_id = dag_run_id
    st.session_state.task_id = task_id

    add_message("user", f"특정 Task 분석 요청: {dag_id}/{dag_run_id}/{task_id}")

    with st.spinner("🔍 Task 분석 중..."):
        for event in stream_workflow_updates(
            dag_id=dag_id, dag_run_id=dag_run_id, task_id=task_id, session_id=session_id
        ):
            process_workflow_event(event, in_sidebar=True)
