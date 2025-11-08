"""
Langfuse Configuration for LLM Observability
"""

from langfuse.langchain import CallbackHandler
from langfuse import Langfuse, get_client
from server.config import settings
import uuid
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def initialize_langfuse() -> Optional[Langfuse]:
    """
    Initialize Langfuse client at startup (singleton pattern)

    Returns:
        Langfuse client instance or None if initialization fails
    """
    try:
        # ✅ 환경 변수 또는 생성자로 초기화
        langfuse = Langfuse(
            public_key=settings.LANGFUSE_PUBLIC_KEY,
            secret_key=settings.LANGFUSE_SECRET_KEY,
            host=settings.LANGFUSE_HOST,
        )
        logger.info("✅ Langfuse client initialized successfully")
        return langfuse
    except Exception as e:
        logger.error(f"❌ Failed to initialize Langfuse client: {e}", exc_info=True)
        return None


def get_langfuse_handler(
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    tags: Optional[list] = None,
) -> Optional[CallbackHandler]:
    """
    Create Langfuse CallbackHandler for LangChain tracing

    The CallbackHandler automatically uses environment variables:
    - LANGFUSE_PUBLIC_KEY
    - LANGFUSE_SECRET_KEY
    - LANGFUSE_BASE_URL

    Args:
        session_id: Optional session identifier
        user_id: Optional user identifier
        tags: Optional list of tags

    Returns:
        CallbackHandler instance or None if creation fails
    """
    try:
        # ✅ CallbackHandler는 환경 변수에서 자동으로 credentials를 읽음
        # 추가 파라미터 없이 초기화 가능
        langfuse_handler = CallbackHandler()

        logger.info(f"✅ Langfuse CallbackHandler created successfully")

        if session_id or user_id or tags:
            logger.info(f"Session: {session_id}, User: {user_id}, Tags: {tags}")

        return langfuse_handler

    except Exception as e:
        logger.error(f"❌ Failed to create Langfuse handler: {e}", exc_info=True)
        return None


def get_langfuse_config(
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    tags: Optional[list] = None,
) -> dict:
    """
    Create LangChain config with Langfuse tracing

    Args:
        session_id: Session identifier
        user_id: User identifier
        tags: List of tags

    Returns:
        Config dictionary for LangChain with Langfuse callbacks
    """
    try:
        handler = get_langfuse_handler(session_id, user_id, tags)

        if handler is None:
            logger.warning("⚠️ Langfuse handler not available - using fallback config")
            return {"run_name": "airflow_monitoring_agent"}

        # metadata를 통해 trace 속성 설정
        metadata = {}
        if user_id:
            metadata["langfuse_user_id"] = user_id
        if session_id:
            metadata["langfuse_session_id"] = session_id
        if tags:
            metadata["langfuse_tags"] = tags

        config = {
            "callbacks": [handler],
            "run_name": "airflow_monitoring_agent",
        }

        if metadata:
            config["metadata"] = metadata

        logger.info(f"✅ Langfuse config created with metadata: {metadata}")

        return config

    except Exception as e:
        logger.error(f"❌ Failed to create Langfuse config: {e}", exc_info=True)
        return {"run_name": "airflow_monitoring_agent"}


def flush_langfuse():
    """Flush all pending Langfuse events (for short-lived apps)"""
    try:
        client = get_client()
        if client:
            client.flush()
            logger.info("✅ Langfuse events flushed")
    except Exception as e:
        logger.error(f"❌ Failed to flush Langfuse: {e}")


def shutdown_langfuse():
    """Shutdown Langfuse client (for short-lived apps)"""
    try:
        client = get_client()
        if client:
            client.shutdown()
            logger.info("✅ Langfuse client shut down")
    except Exception as e:
        logger.error(f"❌ Failed to shutdown Langfuse: {e}")
