"""
Langfuse Configuration for LLM Observability
"""

from langfuse.callback import CallbackHandler
from server.config import settings
import uuid
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def create_langfuse_handler(
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    trace_name: Optional[str] = None,
) -> Optional[CallbackHandler]:
    """
    Create a Langfuse callback handler for tracing LLM interactions

    Args:
        session_id: Optional session identifier
        user_id: Optional user identifier
        trace_name: Optional name for the trace

    Returns:
        CallbackHandler instance configured with project settings, or None if failed
    """
    try:
        if session_id is None:
            session_id = str(uuid.uuid4())

        handler = CallbackHandler(
            public_key=settings.LANGFUSE_PUBLIC_KEY,
            secret_key=settings.LANGFUSE_SECRET_KEY,
            host=settings.LANGFUSE_HOST,
            session_id=session_id,
            user_id=user_id,
            trace_name=trace_name or "airflow_monitoring_workflow",
        )

        logger.info(f"Langfuse handler created successfully for session: {session_id}")
        return handler

    except Exception as e:
        logger.warning(f"Failed to create Langfuse handler: {str(e)}")
        logger.warning("Continuing without Langfuse tracing...")
        return None


def get_langfuse_config(session_id: Optional[str] = None) -> dict:
    """
    Get configuration dict for LangChain callbacks

    Args:
        session_id: Optional session identifier

    Returns:
        Configuration dictionary with Langfuse handler if available
    """
    handler = create_langfuse_handler(session_id=session_id)

    if handler:
        return {"callbacks": [handler], "run_name": "airflow_monitoring_agent"}
    else:
        return {"callbacks": [], "run_name": "airflow_monitoring_agent"}
