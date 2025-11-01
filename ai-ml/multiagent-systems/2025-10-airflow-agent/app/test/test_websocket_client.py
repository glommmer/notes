# app/test/test_websocket_client.py (최종 수정)

import asyncio
import json
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
    stream=sys.stdout,
    force=True
)
logger = logging.getLogger(__name__)


async def main():
    from websockets import connect
    from websockets.client import ClientConnection

    uri = "ws://127.0.0.1:8000/ws/agent"

    logger.info("🔌 Connecting...")

    # ✅ keepalive_ping을 None으로 설정 (타임아웃 제거)
    async with connect(
            uri,
            ping_interval=None,  # ← 핵심!
            ping_timeout=None,  # ← 핵심!
    ) as ws:
        logger.info("✅ Connected")

        # 시작 메시지
        start_msg = {"type": "start", "dag_id": "failed_dag"}
        logger.info(f"📤 Sending: {start_msg}")
        await ws.send(json.dumps(start_msg))

        msg_count = 0

        # ✅ 메시지 수신 루프 (타임아웃 없음)
        try:
            while msg_count < 100:
                msg_count += 1

                # ✅ 타임아웃을 최소한으로 설정 (메시지 없을 때만)
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=60)
                except asyncio.TimeoutError:
                    logger.warning(f"⏱️ No message for 60s (msg #{msg_count})")
                    continue

                data = json.loads(msg)
                msg_type = data.get("type")

                logger.info(f"📩 [{msg_count}] {msg_type}")

                if msg_type == "requires_input":
                    logger.info(f"   Q: {data.get('question', '?')}")

                    response = {"type": "user_input", "input": "clear"}
                    logger.info(f"📤 Sending: user_input")
                    await ws.send(json.dumps(response))

                elif msg_type == "complete":
                    logger.info("✅ Workflow complete!")
                    break

                elif msg_type == "error":
                    logger.error(f"❌ {data.get('message')}")
                    break

        except KeyboardInterrupt:
            logger.info("🛑 Interrupted")
        except Exception as e:
            logger.error(f"❌ Error: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())
