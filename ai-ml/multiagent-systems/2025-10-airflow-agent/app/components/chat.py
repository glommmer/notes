"""
Chat Interface Component - Improved Layout
Handles streaming updates from server with new layout design
"""

import json
import os
import streamlit as st
import requests
import logging
import asyncio
import uuid
from datetime import datetime
from pathlib import Path
from sseclient import SSEClient
from typing import Optional, Dict, Any
from app.utils.state_manager import add_message, get_messages
from app.utils.session_manager import SessionManager
from websockets import connect


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
logger.info("Streamlit application started - Improved Layout")
logger.info("=" * 80)

# Get API base URL from environment
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

# Get SessionManager() object
session_manager = SessionManager()


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


def get_all_sessions():
    """SESSION_DIR의 모든 session_*.json 파일 로드"""
    all_sessions = {}
    all_display_messages = []

    for session_file in session_manager.storage_dir.glob("session_*.json"):
        try:
            with open(session_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                session_id = data.get("session_id")
                workspace = data.get("workspace", {})

                if session_id:
                    all_sessions[session_id] = workspace

                    # workspace["messages"]를 display_messages로 변환
                    for msg in workspace.get("messages", []):
                        display_msg = {
                            "type": msg.get("type", "agent_update"),
                            "agent": msg.get("agent", "SYSTEM"),
                            "message": msg.get("message", ""),
                            "data": msg.get("data"),
                            "session_id": session_id,
                        }
                        all_display_messages.append(display_msg)
        except Exception as e:
            logger.error(f"Failed to load: {e}")

    return all_sessions, all_display_messages


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
        error_msg = f"Request failed: {str(e)}"
        logger.error(error_msg, exc_info=True)
        logger.error(f"Request URL: {url}")
        logger.error(f"Request payload: {payload}")
        yield {"type": "error", "message": error_msg}
    except Exception as e:
        error_msg = f"Streaming error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        logger.error(f"Exception type: {type(e)}")
        yield {"type": "error", "message": error_msg}


def init_session_state():
    """Initialize session state with default values"""
    if "initialized" not in st.session_state:
        st.session_state.initialized = True
        st.session_state.monitoring_active = False
        st.session_state.messages = []
        st.session_state.current_session_id = None
        st.session_state.waiting_for_input = False
        st.session_state.current_question = None
        st.session_state.workflow_complete = False
        st.session_state.dag_id = None
        st.session_state.dag_run_id = None
        st.session_state.task_id = None

        # Session 별 작업 공간 저장
        st.session_state.session_workspaces = {}
        st.session_state.active_sessions = []
        st.session_state.display_messages = []


def get_session_workspace(session_id: str) -> Dict[str, Any]:
    """세션별 작업 공간 조회 또는 생성"""
    if session_id not in st.session_state.session_workspaces:
        st.session_state.session_workspaces[session_id] = {
            "messages": [],
            "status": "active",
            "created_at": datetime.now().isoformat(),
            "dag_id": None,
            "dag_run_id": None,
            "task_id": None,
        }
        if session_id not in st.session_state.active_sessions:
            st.session_state.active_sessions.append(session_id)

    return st.session_state.session_workspaces[session_id]


def render_agent_message(
    agent: str, message: str, data: dict = None, container=None, is_user_request=False
):
    """
    Render an agent message in the chat interface

    Args:
        agent: Agent name
        message: Message text
        data: Optional additional data
    """
    if is_user_request:
        with st.container(border=True):
            st.markdown(f"### 👤 **사용자 요청**")
            st.markdown(f"> {message}")
            st.divider()
        return

    # Map agent to avatar emoji
    avatar_map = {
        "MONITOR": "🔍",
        "ANALYZER": "🔬",
        "INTERACTION": "💬",
        "ACTION": "⚡",
        "SYSTEM": "🤖",
    }

    avatar = avatar_map.get(agent, "🤖")

    if container is None:
        container = st.container()

    with container:
        with st.chat_message("assistant", avatar=avatar):
            st.markdown(f"**{agent}**: {message}")

            if data:
                # Display relevant data
                if agent == "MONITOR":
                    if data.get("dag_id"):
                        st.info(f"🔍 DAG: {data['dag_id']}")
                    if data.get("task_id"):
                        st.info(f"📋 Task: {data.get('task_id', 'N/A')}")
                    if data.get("error_message"):
                        st.warning(data["error_message"])

                elif agent == "ANALYZER":
                    if data.get("root_cause"):
                        st.error(f"📌 Root Cause: {data['root_cause']}")
                    if data.get("analysis_report"):
                        with st.expander("📊 Analysis Report"):
                            st.markdown(data["analysis_report"][:500])

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


def process_workflow_event(event: dict, session_id: str, container=None):
    """Process a workflow event from the server"""

    event_type = event.get("type")

    if event_type == "agent_update":
        agent = event.get("agent", "SYSTEM")
        message = event.get("message", "")
        data = event.get("data")

        # Store DAG identifiers
        if data:
            if data.get("dag_id"):
                st.session_state.dag_id = data["dag_id"]
            if data.get("dag_run_id"):
                st.session_state.dag_run_id = data["dag_run_id"]
            if data.get("task_id"):
                st.session_state.task_id = data["task_id"]

        # session_state에 메시지 저장
        if "display_messages" not in st.session_state:
            st.session_state.display_messages = []

        st.session_state.display_messages.append(
            {
                "agent": agent,
                "message": message,
                "data": data,
                "session_id": session_id,
            }
        )

        # Render message
        render_agent_message(agent, message, data, container)

        # Add to history
        add_message("assistant", f"{agent}: {message}")

    elif event_type == "complete":
        message = event.get("message", "✅ 워크플로우 완료")
        with container or st.container():
            st.success(message)
        add_message("assistant", message)
        st.session_state.workflow_complete = True

    elif event_type == "error":
        message = event.get("message", "❌ 오류 발생")
        with container or st.container():
            st.error(message)
        add_message("assistant", f"Error: {message}")


def start_monitoring_workflow(initial_message: str, session_id: str):
    """Start a new monitoring workflow"""

    st.session_state.current_session_id = session_id
    st.session_state.monitoring_active = True

    # Get or create session workspace
    workspace = get_session_workspace(session_id)
    session_manager.save_session(session_id, workspace)

    # Show processing message
    with st.spinner("🔍 Airflow 워크플로우 모니터링 중..."):
        # Stream workflow updates
        for event in stream_workflow_updates(
            user_input=initial_message, session_id=session_id
        ):
            process_workflow_event(event, session_id, container=None)

            # Update session workspace
            workspace["messages"].append(
                {
                    "type": event.get("type"),
                    "agent": event.get("agent"),
                    "message": event.get("message"),
                    "data": event.get("data"),
                    "timestamp": datetime.now().isoformat(),
                }
            )

    st.session_state.monitoring_active = False
    st.session_state.workflow_complete = True

    session_manager.save_session(session_id, workspace)


def render_sidebar_with_sessions():
    """Render improved sidebar with message input and session management"""

    with st.sidebar:
        # 헤더
        st.header("⚙️ Airflow 모니터링")

        # ═══════════════════════════════════════════════════════════
        # 1. 메시지 입력 칸 (좌측 사이드바 최상단)
        # ═══════════════════════════════════════════════════════════
        st.subheader("📝 명령어 입력")

        user_input = st.chat_input(
            "예: DAG 상태 확인, 실패한 작업 분석...", key="sidebar_message_input"
        )

        # ═══════════════════════════════════════════════════════════
        # 2. 나누기 선
        # ═══════════════════════════════════════════════════════════
        st.divider()

        # ═══════════════════════════════════════════════════════════
        # 3. 세션 ID별 독립된 작업 공간
        # ═══════════════════════════════════════════════════════════
        st.subheader("📊 활성 세션")

        # 활성 세션 표시
        if st.session_state.active_sessions:
            for idx, session_id in enumerate(st.session_state.active_sessions):
                workspace = get_session_workspace(session_id)

                # Session 표시
                col1, col2, col3 = st.columns([3, 1, 1])

                with col1:
                    # 클릭 가능한 세션 선택
                    if st.button(
                        f"🔹 Session {idx + 1}\n{session_id[:8]}...",
                        key=f"select_session_{session_id}",
                        use_container_width=True,
                    ):
                        st.session_state.current_session_id = session_id
                        st.rerun()

                with col2:
                    st.caption(f"{len(workspace['messages'])} 메시지")

                with col3:
                    if st.button("✕", key=f"close_session_{session_id}"):
                        st.session_state.active_sessions.remove(session_id)
                        if st.session_state.current_session_id == session_id:
                            st.session_state.current_session_id = None
                        del st.session_state.session_workspaces[session_id]

                        # display_messages에서 해당 세션 메시지 삭제
                        if "display_messages" in st.session_state:
                            st.session_state.display_messages = [
                                msg
                                for msg in st.session_state.display_messages
                                if msg.get("session_id") != session_id
                            ]

                        sessions_dir = session_manager.storage_dir
                        for session_file in sessions_dir.glob(
                            f"session_{session_id[:8]}*.json"
                        ):
                            try:
                                session_file.unlink()  # 파일 삭제
                            except Exception as e:
                                logger.error(f"Failed to delete: {e}")

                        st.rerun()

                # 세션별 상태 표시
                with st.expander(f"상세 정보 - {session_id[:12]}...", expanded=False):
                    st.caption(f"상태: {workspace['status']}")
                    st.caption(f"생성: {workspace['created_at']}")
                    if workspace["dag_id"]:
                        st.caption(f"DAG: {workspace['dag_id']}")
                    if workspace["dag_run_id"]:
                        st.caption(f"Run ID: {workspace['dag_run_id']}")
                    st.caption(f"메시지: {len(workspace['messages'])}")

                st.divider()
        else:
            st.info("✨ 활성 세션이 없습니다.")

        # ═══════════════════════════════════════════════════════════
        # 4. 새로운 세션 시작 버튼
        # ═══════════════════════════════════════════════════════════
        if st.button("➕ 새 세션 시작", use_container_width=True):
            new_session_id = str(uuid.uuid4())
            st.session_state.current_session_id = new_session_id
            get_session_workspace(new_session_id)
            st.rerun()

        # ═══════════════════════════════════════════════════════════
        # 5. 하단 정보
        # ═══════════════════════════════════════════════════════════
        st.divider()
        st.caption(f"📍 Sessions: {len(st.session_state.active_sessions)}")
        st.caption("🔗 Airflow Monitoring Agent v2.0")
        st.caption("💡 Powered by LangGraph + OpenAI")

    return user_input


def render_chat_interface():
    """Render the main chat interface with improved layout"""

    # Title
    st.title("🚀 Airflow 모니터링 에이전트")
    st.markdown("Apache Airflow 워크플로우 모니터링 및 자동 분석 시스템")

    # ═══════════════════════════════════════════════════════════
    # 좌측 사이드바: 메시지 입력 + 세션 관리
    # ═══════════════════════════════════════════════════════════
    user_input = render_sidebar_with_sessions()

    # ═══════════════════════════════════════════════════════════
    # 우측 메인 프레임: 결과 출력
    # ═══════════════════════════════════════════════════════════
    st.subheader("📋 실시간 결과")

    # 현재 세션 정보 표시
    if st.session_state.current_session_id:
        workspace = get_session_workspace(st.session_state.current_session_id)
        st.caption(f"활성 세션: {st.session_state.current_session_id[:16]}...")
    else:
        st.info("👈 좌측 세션에서 세션을 선택하거나 새로 시작하세요.")

    st.divider()

    # ═══════════════════════════════════════════════════════════
    # 결과 컨테이너 (자동 스크롤 설정)
    # ═══════════════════════════════════════════════════════════
    # results_container = st.container()

    if "display_messages" in st.session_state:
        current_messages = [
            msg
            for msg in st.session_state.display_messages
            if msg.get("session_id") == st.session_state.current_session_id
        ]

        for idx, msg in enumerate(current_messages):
            msg_type = msg.get("type", "agent_update")
            agent = msg.get("agent")
            message = msg.get("message")
            data = msg.get("data")

            if msg_type == "user_request":
                render_agent_message(agent, message, data, is_user_request=True)
                with st.container():
                    st.caption(
                        f"📊 요청 #{len([m for m in st.session_state.display_messages[:idx + 1] if m.get('type') == 'user_request'])}"
                    )
            else:
                render_agent_message(agent, message, data)

            if idx < len(current_messages) - 1:
                next_msg = current_messages[idx + 1]
                if next_msg.get("type") == "user_request":
                    st.divider()

    # 메시지 입력 처리
    if user_input:
        # # 사용자 메시지 표시
        # with results_container:
        #     with st.chat_message("user", avatar="👤"):
        #         st.markdown(user_input)

        # 1단계: 세션 없으면 먼저 생성
        if not st.session_state.current_session_id:
            new_session_id = str(uuid.uuid4())
            st.session_state.current_session_id = new_session_id
            get_session_workspace(new_session_id)

            # 사이드바에도 표시되도록 추가
            if new_session_id not in st.session_state.active_sessions:
                st.session_state.active_sessions.append(new_session_id)

            workspace = get_session_workspace(new_session_id)
            session_manager.save_session(new_session_id, workspace)

        # 그 후 사용자 요청 저장
        if "display_messages" not in st.session_state:
            st.session_state.display_messages = []

        st.session_state.display_messages.append(
            {
                "type": "user_request",
                "agent": "USER",
                "message": user_input,
                "data": None,
                "session_id": st.session_state.current_session_id,
            }
        )

        add_message("user", user_input)

        # 워크플로우 시작
        start_monitoring_workflow(
            user_input,
            st.session_state.current_session_id,
        )

        # 자동 스크롤 (최신 결과로 이동)
        # st.rerun()

    # # 이전 메시지 표시 (현재 세션의 메시지만)
    # if st.session_state.current_session_id:
    #     workspace = get_session_workspace(st.session_state.current_session_id)
    #
    #     if workspace["messages"]:
    #         with results_container:
    #             st.caption(f"📝 총 {len(workspace['messages'])} 메시지")
    #             st.divider()
    #
    #             # 메시지를 위에서 아래로 표시 (최신 메시지가 아래)
    #             for idx, msg in enumerate(workspace["messages"]):
    #                 with st.container(border=True):
    #                     col1, col2 = st.columns([0.8, 0.2])
    #
    #                     with col1:
    #                         agent = msg.get("agent", "SYSTEM")
    #                         avatar_map = {
    #                             "MONITOR": "🔍",
    #                             "ANALYZER": "🔬",
    #                             "INTERACTION": "💬",
    #                             "ACTION": "⚡",
    #                             "SYSTEM": "🤖",
    #                         }
    #                         avatar = avatar_map.get(agent, "🤖")
    #
    #                         st.markdown(f"**{avatar} {agent}**: {msg.get('message', '')}")
    #
    #                     with col2:
    #                         time_str = msg.get("timestamp", "")
    #                         if time_str:
    #                             time_obj = datetime.fromisoformat(time_str)
    #                             st.caption(time_obj.strftime("%H:%M:%S"))
    #     else:
    #         with results_container:
    #             st.info("💡 메시지를 입력하면 여기에 결과가 표시됩니다.")


# Main execution
if __name__ == "__main__":
    render_chat_interface()
