"""
Agent Router - API endpoints for workflow execution
"""

import json
import asyncio
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from server.workflow.graph import create_monitoring_graph
from server.workflow.state import create_initial_state, AgentState
from server.langfuse_config import get_langfuse_config
import uuid
import traceback

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/agent",
    tags=["agent"],
    responses={404: {"description": "Not found"}},
)


class MonitoringRequest(BaseModel):
    """Request model for monitoring workflow"""

    dag_id: Optional[str] = None
    dag_run_id: Optional[str] = None
    task_id: Optional[str] = None
    user_input: Optional[str] = None
    session_id: Optional[str] = None


class MonitoringResponse(BaseModel):
    """Response model for monitoring workflow"""

    status: str
    message: str
    data: Optional[dict] = None


async def simple_event_generator(app, initial_state: AgentState, config: dict):
    """
    Simplified event generator using stream mode

    Args:
        app: Compiled LangGraph application
        initial_state: Initial workflow state
        config: LangChain config with callbacks

    Yields:
        SSE formatted messages
    """
    try:
        logger.info("Starting workflow streaming...")

        # Send initial event
        initial_event = {"type": "start", "message": "🚀 워크플로우 시작..."}
        yield f"data: {json.dumps(initial_event, ensure_ascii=False)}\n\n"
        await asyncio.sleep(0.1)

        # Track which nodes we've seen
        seen_nodes = set()

        # Use simpler stream mode - synchronous iteration
        try:
            for output in app.stream(
                initial_state,
                config={
                    **config,
                    "recursion_limit": 100,
                },
                stream_mode="updates",
            ):
                if not output:
                    continue

                logger.info(f"Stream output: {list(output.keys())}")

                # Output is a dict with node names as keys
                for node_name, node_output in output.items():
                    if node_name in seen_nodes:
                        continue

                    seen_nodes.add(node_name)

                    logger.info(f"Processing node: {node_name}")

                    # Extract relevant information
                    current_agent = node_output.get("current_agent", node_name)

                    # Create event based on agent type
                    if "monitor" in node_name.lower():
                        event_data = {
                            "type": "agent_update",
                            "agent": "MONITOR",
                            "message": "🔍 Airflow 모니터링 중...",
                            "data": {
                                "dag_id": node_output.get("dag_id"),
                                "task_id": node_output.get("task_id"),
                                "error_message": node_output.get("error_message"),
                            },
                        }

                    elif "analyzer" in node_name.lower():
                        event_data = {
                            "type": "agent_update",
                            "agent": "ANALYZER",
                            "message": "🔬 오류 분석 중...",
                            "data": {
                                "analysis_report": node_output.get(
                                    "analysis_report", ""
                                )[
                                    :500
                                ],  # Truncate
                                "root_cause": node_output.get("root_cause"),
                            },
                        }

                    elif "interaction" in node_name.lower():
                        event_data = {
                            "type": "agent_update",
                            "agent": "INTERACTION",
                            "message": "💬 사용자 응답 대기 중...",
                            "data": {
                                "user_question": node_output.get("user_question"),
                                "requires_user_input": node_output.get(
                                    "requires_user_input"
                                ),
                            },
                        }

                    elif "action" in node_name.lower():
                        event_data = {
                            "type": "agent_update",
                            "agent": "ACTION",
                            "message": "⚡ 액션 실행 중...",
                            "data": {
                                "final_action": node_output.get("final_action"),
                                "action_result": node_output.get("action_result"),
                                "is_resolved": node_output.get("is_resolved"),
                            },
                        }

                    else:
                        continue

                    yield f"data: {json.dumps(event_data, ensure_ascii=False)}\n\n"
                    await asyncio.sleep(0.05)

        except Exception as stream_error:
            logger.error(f"Stream iteration error: {str(stream_error)}", exc_info=True)
            error_event = {
                "type": "error",
                "message": f"스트림 처리 오류: {str(stream_error)}",
            }
            yield f"data: {json.dumps(error_event, ensure_ascii=False)}\n\n"

        # Send completion
        completion_event = {"type": "complete", "message": "✅ 워크플로우 완료"}
        yield f"data: {json.dumps(completion_event, ensure_ascii=False)}\n\n"

        logger.info("Streaming completed successfully")

    except Exception as e:
        logger.error(f"Generator error: {str(e)}", exc_info=True)
        error_event = {
            "type": "error",
            "message": f"❌ 오류 발생: {str(e)}",
            "details": traceback.format_exc(),
        }
        yield f"data: {json.dumps(error_event, ensure_ascii=False)}\n\n"


@router.post("/invoke", response_model=MonitoringResponse)
async def invoke_monitoring_workflow(request: MonitoringRequest):
    """
    Invoke monitoring workflow synchronously

    This endpoint runs the full workflow and returns the final result.
    Use /stream for real-time updates.

    Args:
        request: Monitoring request parameters

    Returns:
        Final workflow result
    """
    try:
        from langfuse import get_client
        from langfuse.langchain import CallbackHandler

        logger.info(f"Invoking workflow with request: {request}")

        # Generate session ID if not provided
        session_id = request.session_id or str(uuid.uuid4())

        # Get Langfuse client
        langfuse = get_client()

        # Create a trace context
        with langfuse.start_as_current_span(
            name="airflow-monitoring-workflow", trace_context={"trace_id": session_id}
        ) as span:
            # Update trace attributes
            span.update_trace(
                session_id=session_id,
                user_id="airflow-monitor",
                input={"dag_id": request.dag_id, "user_input": request.user_input},
            )

            # Create handler (automatically inherits trace context)
            langfuse_handler = CallbackHandler()

            # Create initial state
            initial_state = create_initial_state(
                dag_id=request.dag_id,
                dag_run_id=request.dag_run_id,
                task_id=request.task_id,
                session_id=session_id,
            )

            if request.user_input:
                initial_state["user_input"] = request.user_input

            # Create workflow graph
            app = create_monitoring_graph(session_id)

            # Execute workflow
            result = app.invoke(
                initial_state,
                config={"callbacks": [langfuse_handler], "recursion_limit": 100},
            )

            # Update trace output
            span.update_trace(
                output={
                    "is_resolved": result.get("is_resolved"),
                    "final_action": result.get("final_action"),
                }
            )

            return MonitoringResponse(**result)

    except Exception as e:
        logger.error(f"Workflow invocation error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Workflow execution failed: {str(e)}\n{traceback.format_exc()}",
        )


@router.post("/stream")
async def stream_monitoring_workflow(request: MonitoringRequest):
    """
    Stream monitoring workflow execution

    This endpoint streams real-time updates as Server-Sent Events (SSE).
    Client should handle SSE format.

    Args:
        request: Monitoring request parameters

    Returns:
        StreamingResponse with SSE
    """
    try:
        logger.info(f"Starting workflow stream for request: {request.model_dump()}")

        # Generate session ID if not provided
        session_id = request.session_id or str(uuid.uuid4())

        # 1. 기존 세션 상태 로드 시도
        existing_state = load_session_state(session_id)

        if existing_state and request.user_input:
            # 기존 세션에 user_input 추가
            logger.info(f"Continuing existing session {session_id}")
            existing_state["user_input"] = request.user_input
            existing_state["requires_user_input"] = False
            initial_state = existing_state
        else:
            # Create initial state
            initial_state = create_initial_state(
                dag_id=request.dag_id,
                dag_run_id=request.dag_run_id,
                task_id=request.task_id,
                session_id=session_id,
            )

            if request.user_input:
                initial_state["user_input"] = request.user_input

            logger.info(
                f"Initial state created: dag_id={initial_state.get('dag_id')}, session_id={session_id}"
            )

        # Create workflow graph
        try:
            app = create_monitoring_graph(session_id)
            logger.info("Workflow graph created successfully")
        except Exception as graph_error:
            logger.error(f"Graph creation error: {str(graph_error)}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Failed to create workflow graph: {str(graph_error)}",
            )

        # Create Langfuse handler
        try:
            config = get_langfuse_config(
                session_id=session_id,
                user_id="airflow-monitor",
                tags=["airflow", "monitoring"],
            )
            logger.info("Langfuse config created successfully")
        except Exception as config_error:
            logger.warning(f"Config creation failed: {str(config_error)}")
            # Fallback: 빈 config 사용
            config = {"run_name": "airflow_monitoring_agent"}

        # Return streaming response
        return StreamingResponse(
            state_aware_event_generator(app, initial_state, config, session_id),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Streaming setup error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start streaming: {str(e)}\n{traceback.format_exc()}",
        )


@router.get("/health")
async def health_check():
    """
    Health check endpoint

    Returns:
        Health status
    """
    try:
        # Try to create a workflow graph to verify everything is working
        test_graph = create_monitoring_graph("health_check")

        try:
            config = get_langfuse_config(session_id="health_check")
            langfuse_status = "ok" if config.get("callbacks") else "fallback"
        except Exception as e:
            logger.warning(f"Langfuse health check failed: {e}")
            langfuse_status = "failed"

        return {
            "status": "healthy",
            "service": "airflow-monitoring-agent",
            "graph_status": "ok",
            "langfuse_status": langfuse_status,
        }
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return {
            "status": "degraded",
            "service": "airflow-monitoring-agent",
            "error": str(e),
        }


# ✅ 세션 상태 관리 함수 추가
from pathlib import Path
import json

SESSION_STORE = Path(__file__).parent.parent.parent / "sessions"
SESSION_STORE.mkdir(exist_ok=True)


def save_session_state(session_id: str, state: dict):
    """Save session state to file"""
    filepath = SESSION_STORE / f"state_{session_id}.json"
    try:
        with open(filepath, "w") as f:
            json.dump(state, f, default=str)
        logger.info(f"Saved session state: {session_id}")
    except Exception as e:
        logger.error(f"Failed to save session state: {e}")


def load_session_state(session_id: str) -> dict:
    """Load session state from file"""
    filepath = SESSION_STORE / f"state_{session_id}.json"
    try:
        if filepath.exists():
            with open(filepath, "r") as f:
                state = json.load(f)
            logger.info(f"Loaded session state: {session_id}")
            return state
    except Exception as e:
        logger.error(f"Failed to load session state: {e}")
    return None


async def state_aware_event_generator(
    app, initial_state: AgentState, config: dict, session_id: str
):
    """Event generator with state persistence"""
    try:
        logger.info("Starting workflow streaming with state awareness...")

        # Send initial event
        initial_event = {"type": "start", "message": "🚀 워크플로우 시작..."}
        yield f"data: {json.dumps(initial_event, ensure_ascii=False)}\n\n"
        await asyncio.sleep(0.1)

        seen_nodes = set()
        current_state = initial_state

        # # user_input이 있고 이미 분석이 완료된 상태라면 interaction부터 시작
        # if current_state.get("user_input") and current_state.get("analysis_report"):
        #     logger.info("Resuming from interaction node")

        # interaction 노드부터 실행
        for output in app.stream(
            current_state,
            config={**config, "recursion_limit": 100},
            stream_mode="updates",
        ):
            if not output:
                continue

            for node_name, node_output in output.items():
                if node_name in seen_nodes:
                    continue

                seen_nodes.add(node_name)
                current_state.update(node_output)

                # Send event
                event_data = create_event_data(node_name, node_output)
                yield f"data: {json.dumps(event_data, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0.05)

                # ✅ 상태 저장
                save_session_state(session_id, current_state)

        # else:
        #     # 처음부터 실행
        #     for output in app.stream(
        #         current_state,
        #         config={**config, "recursion_limit": 100},
        #         stream_mode="updates",
        #     ):
        #         if not output:
        #             continue
        #
        #         for node_name, node_output in output.items():
        #             if node_name in seen_nodes:
        #                 continue
        #
        #             seen_nodes.add(node_name)
        #             current_state.update(node_output)
        #
        #             event_data = create_event_data(node_name, node_output)
        #             yield f"data: {json.dumps(event_data, ensure_ascii=False)}\n\n"
        #             await asyncio.sleep(0.05)
        #
        #             save_session_state(session_id, current_state)

        # Send completion
        completion_event = {"type": "complete", "message": "✅ 워크플로우 완료"}
        yield f"data: {json.dumps(completion_event, ensure_ascii=False)}\n\n"

        logger.info("Streaming completed successfully")

    except Exception as e:
        logger.error(f"Generator error: {str(e)}", exc_info=True)
        error_event = {"type": "error", "message": f"❌ 오류 발생: {str(e)}"}
        yield f"data: {json.dumps(error_event, ensure_ascii=False)}\n\n"


def create_event_data(node_name: str, node_output: dict) -> dict:
    """Create event data from node output"""
    if "monitor" in node_name.lower():
        return {
            "type": "agent_update",
            "agent": "MONITOR",
            "message": "🔍 Airflow 모니터링 중...",
            "data": {
                "dag_id": node_output.get("dag_id"),
                "task_id": node_output.get("task_id"),
                "error_message": node_output.get("error_message"),
            },
        }
    elif "analyzer" in node_name.lower():
        return {
            "type": "agent_update",
            "agent": "ANALYZER",
            "message": "🔬 오류 분석 중...",
            "data": {
                "analysis_report": node_output.get("analysis_report", "")[:500],
                "root_cause": node_output.get("root_cause"),
            },
        }
    elif "interaction" in node_name.lower():
        return {
            "type": "agent_update",
            "agent": "INTERACTION",
            "message": "💬 사용자 응답 처리 중...",
            "data": {
                "user_question": node_output.get("user_question"),
                "final_action": node_output.get("final_action"),
            },
        }
    elif "action" in node_name.lower():
        return {
            "type": "agent_update",
            "agent": "ACTION",
            "message": "⚡ 액션 실행 중...",
            "data": {
                "final_action": node_output.get("final_action"),
                "action_result": node_output.get("action_result"),
                "is_resolved": node_output.get("is_resolved"),
            },
        }
    else:
        return {"type": "agent_update", "agent": "SYSTEM", "message": "처리 중..."}
