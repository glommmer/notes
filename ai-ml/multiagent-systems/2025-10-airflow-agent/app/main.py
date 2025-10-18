"""
Streamlit Main Application
Interactive UI for Airflow Monitoring Agent
"""

import os
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import streamlit as st
from dotenv import load_dotenv

# Now import from app modules
from app.utils.state_manager import init_session_state
from app.components.chat import render_chat_interface, render_sidebar_controls

# Load environment variables
load_dotenv()


def main():
    """Main application entry point"""

    # Set page configuration
    st.set_page_config(
        page_title="Airflow 모니터링 에이전트",
        page_icon="🤖",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # Initialize session state
    init_session_state()

    # Render sidebar controls
    render_sidebar_controls()

    # Render main chat interface
    render_chat_interface()

    # Footer
    with st.sidebar:
        st.divider()
        st.caption("Airflow Monitoring Agent v1.0.0")
        st.caption("Powered by LangGraph & OpenAI")


if __name__ == "__main__":
    main()
