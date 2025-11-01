"""
Session State Management for Streamlit
"""

import streamlit as st
from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)


def init_session_state():
    """
    Initialize Streamlit session state with default values
    """
    if "initialized" not in st.session_state:
        reset_session_state()
        st.session_state.initialized = True


def reset_session_state():
    """
    Reset session state to default values
    """
    st.session_state.monitoring_active = False
    st.session_state.messages = []
    st.session_state.current_session_id = None
    st.session_state.waiting_for_input = False
    st.session_state.current_question = None
    st.session_state.workflow_complete = False
    st.session_state.dag_id = None
    st.session_state.dag_run_id = None
    st.session_state.task_id = None
    st.session_state.session_workspaces = {}
    st.session_state.active_sessions = []
    st.session_state.display_messages = []

    from app.components.chat import get_all_sessions

    try:
        workspaces, messages = get_all_sessions()
        st.session_state.session_workspaces = workspaces
        st.session_state.active_sessions = list(workspaces.keys())
        st.session_state.display_messages = messages
    except Exception as e:
        logger.error(f"Failed to restore sessions: {e}")


def add_message(role: str, content: str):
    """
    Add a message to the chat history

    Args:
        role: Message role (e.g., "assistant", "user", "system")
        content: Message content
    """
    if "messages" not in st.session_state:
        st.session_state.messages = []

    st.session_state.messages.append({"role": role, "content": content})


def get_messages() -> List[Dict[str, Any]]:
    """
    Get all chat messages

    Returns:
        List of message dictionaries
    """
    if "messages" not in st.session_state:
        st.session_state.messages = []

    return st.session_state.messages


def clear_messages():
    """Clear all chat messages"""
    st.session_state.messages = []
