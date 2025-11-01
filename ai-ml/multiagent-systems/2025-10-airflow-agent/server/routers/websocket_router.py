"""
WebSocket Router - Real-time bidirectional agent communication
"""

import json
import logging
import asyncio
import uuid
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)
ws_router = APIRouter(prefix="/ws", tags=["websocket"])


@ws_router.websocket("/agent")
async def websocket_agent_endpoint(websocket: WebSocket):
    """WebSocket endpoint for workflow execution"""

    await websocket.accept()
    logger.info("✅ WebSocket: Connection accepted")

    try:
        # 초기 메시지 수신
        logger.info("⏳ WebSocket: Waiting for initial message...")
        initial_msg = await websocket.receive_json()
        logger.info(f"📩 WebSocket: Received: {initial_msg}")

        if initial_msg.get("type") != "start":
            await websocket.send_json({"type": "error", "message": "First message must be 'start'"})
            return

        session_id = initial_msg.get("session_id") or str(uuid.uuid4())
        logger.info(f"🔑 Session ID: {session_id}")

        # import (여기서 해야 circular import 방지)
        try:
            logger.info("📦 Importing workflow modules...")
            from server.workflow.state import create_initial_state
            from server.workflow.graph import create_monitoring_graph
            from server.langfuse_config import get_langfuse_config
            logger.info("✅ Imports successful")
        except Exception as e:
            logger.error(f"❌ Import error: {e}", exc_info=True)
            await websocket.send_json({"type": "error", "message": f"Import failed: {e}"})
            return

        # 초기 상태
        try:
            logger.info("🔧 Creating initial state...")
            state = create_initial_state(
                dag_id=initial_msg.get("dag_id"),
                dag_run_id=initial_msg.get("dag_run_id"),
                task_id=initial_msg.get("task_id"),
                session_id=session_id,
            )
            state["max_iterations"] = 5
            state["iteration_count"] = 0
            logger.info(f"✅ Initial state created")
        except Exception as e:
            logger.error(f"❌ State creation error: {e}", exc_info=True)
            await websocket.send_json({"type": "error", "message": f"State creation failed: {e}"})
            return

        # 워크플로우 생성
        try:
            logger.info("🔧 Creating workflow graph...")
            app = create_monitoring_graph(session_id)
            logger.info("✅ Workflow graph created")
        except Exception as e:
            logger.error(f"❌ Graph creation error: {e}", exc_info=True)
            await websocket.send_json({"type": "error", "message": f"Graph creation failed: {e}"})
            return

        # Langfuse config
        try:
            logger.info("🔧 Creating Langfuse config...")
            config = get_langfuse_config(session_id=session_id)
            logger.info("✅ Langfuse config created")
        except Exception as e:
            logger.error(f"❌ Config creation error: {e}", exc_info=True)
            await websocket.send_json({"type": "error", "message": f"Config creation failed: {e}"})
            return

        # 시작 메시지 전송
        logger.info("📤 Sending start message...")
        await websocket.send_json({
            "type": "start",
            "message": "🚀 워크플로우 시작",
            "session_id": session_id
        })
        logger.info("✅ Start message sent")

        # 워크플로우 실행
        logger.info(f"🔄 Starting workflow loop")

        iteration = 0
        max_iter = 5

        while iteration < max_iter:
            iteration += 1
            state["iteration_count"] = iteration
            logger.info(f"\n{'=' * 50}")
            logger.info(f"🔁 Iteration {iteration}/{max_iter}")
            logger.info(f"{'=' * 50}")

            # 종료 체크
            if state.get("is_resolved"):
                logger.info("✅ Issue resolved - ending")
                break

            # 사용자 입력 필요?
            if state.get("requires_user_input") and not state.get("user_input"):
                logger.info("⏳ Waiting for user input...")

                await websocket.send_json({
                    "type": "requires_input",
                    "question": state.get("user_question", "Select action:"),
                    "session_id": session_id
                })
                logger.info("📤 Sent: requires_input")

                try:
                    user_msg = await asyncio.wait_for(websocket.receive_json(), timeout=120)
                    logger.info(f"📩 Received user input: {user_msg}")

                    if user_msg.get("type") == "user_input":
                        state["user_input"] = user_msg.get("input")
                        state["requires_user_input"] = False
                        logger.info(f"✅ User input set: {state['user_input']}")

                except asyncio.TimeoutError:
                    # logger.warning("⏱️ User input timeout - using default")
                    # state["user_input"] = "skip"
                    # state["requires_user_input"] = False
                    logger.warning("⏱️ User input timeout - ending workflow")
                    break

                # continue

            # 워크플로우 실행
            logger.info("🔄 Executing stream...")

            try:
                step_count = 0
                has_progress = False  # 진행 상태 추적

                for output in app.stream(
                        state,
                        config={**config, "recursion_limit": 50},
                        stream_mode="updates"
                ):
                    if not output:
                        continue

                    has_progress = True

                    for node_name, node_output in output.items():
                        step_count += 1
                        logger.info(f"  📤 Node {step_count}: {node_name}")

                        state.update(node_output)

                        await websocket.send_json({
                            "type": "agent_update",
                            "agent": node_name.upper(),
                            "data": {k: v for k, v in node_output.items() if k not in ['current_agent']}
                        })

                # if step_count == 0:
                #     logger.warning("⚠️ No progress - breaking")
                #     break

                # 진행이 없으면 종료
                if not has_progress:
                    logger.warning("⚠️ No progress - breaking")
                    break

                # requires_user_input가 True이면 다음 반복에서 입력 대기
                if state.get("requires_user_input"):
                    continue

                # 워크플로우가 종료되었으면 break
                if state.get("is_resolved") or state.get("final_action"):
                    break

            except Exception as e:
                logger.error(f"❌ Stream error: {e}", exc_info=True)
                await websocket.send_json({"type": "error", "message": f"Stream error: {e}"})
                break

        # 완료
        logger.info("\n🏁 Workflow ended")
        await websocket.send_json({
            "type": "complete",
            "message": "✅ 완료",
        })

    except WebSocketDisconnect:
        logger.info("🔌 Client disconnected")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except:
            pass
    finally:
        try:
            await websocket.close()
        except:
            pass
        logger.info("🔌 Connection closed")
