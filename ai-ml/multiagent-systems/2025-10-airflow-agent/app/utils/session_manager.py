"""
Session Management Utilities
세션 관리 및 데이터 추적 유틸리티
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional
import logging

logger = logging.getLogger(__name__)

# 세션 저장 디렉토리
SESSION_DIR = Path(__file__).parent.parent.parent / "sessions"
SESSION_DIR.mkdir(parents=True, exist_ok=True)


class SessionManager:
    """세션 생명주기 관리"""

    def __init__(self, storage_dir: Path = SESSION_DIR):
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def save_session(self, session_id: str, workspace: Dict[str, Any]) -> str:
        """
        세션을 파일로 저장

        Args:
            session_id: 세션 ID
            workspace: 세션 데이터

        Returns:
            저장된 파일 경로
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"session_{session_id[:8]}_{timestamp}.json"
        filepath = self.storage_dir / filename

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "session_id": session_id,
                        "saved_at": datetime.now().isoformat(),
                        "workspace": workspace,
                    },
                    f,
                    ensure_ascii=False,
                    indent=2,
                )

            logger.info(f"Session saved: {filepath}")
            return str(filepath)
        except Exception as e:
            logger.error(f"Failed to save session: {e}")
            raise

    def load_session(self, filepath: str) -> Dict[str, Any]:
        """
        저장된 세션 로드

        Args:
            filepath: 세션 파일 경로

        Returns:
            세션 데이터
        """
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

            logger.info(f"Session loaded: {filepath}")
            return data
        except Exception as e:
            logger.error(f"Failed to load session: {e}")
            raise

    def cleanup_old_sessions(self, days: int = 7) -> int:
        """
        오래된 세션 파일 삭제

        Args:
            days: 유지 기간 (일)

        Returns:
            삭제된 파일 수
        """
        cutoff_time = datetime.now() - timedelta(days=days)
        deleted_count = 0

        for filepath in self.storage_dir.glob("session_*.json"):
            if datetime.fromtimestamp(filepath.stat().st_mtime) < cutoff_time:
                try:
                    filepath.unlink()
                    deleted_count += 1
                    logger.info(f"Deleted old session: {filepath.name}")
                except Exception as e:
                    logger.error(f"Failed to delete {filepath}: {e}")

        return deleted_count

    def get_session_summary(self, workspace: Dict[str, Any]) -> Dict[str, Any]:
        """
        세션 요약 정보 생성

        Args:
            workspace: 세션 데이터

        Returns:
            요약 정보
        """
        messages = workspace.get("messages", [])

        agent_counts = {}
        for msg in messages:
            agent = msg.get("agent", "UNKNOWN")
            agent_counts[agent] = agent_counts.get(agent, 0) + 1

        return {
            "status": workspace.get("status", "unknown"),
            "created_at": workspace.get("created_at"),
            "message_count": len(messages),
            "agent_breakdown": agent_counts,
            "dag_id": workspace.get("dag_id"),
            "dag_run_id": workspace.get("dag_run_id"),
            "task_id": workspace.get("task_id"),
        }

    def export_session_as_markdown(
        self, session_id: str, workspace: Dict[str, Any]
    ) -> str:
        """
        세션을 마크다운 형식으로 내보내기

        Args:
            session_id: 세션 ID
            workspace: 세션 데이터

        Returns:
            마크다운 텍스트
        """
        md_content = f"""# Airflow 모니터링 세션 리포트

## 세션 정보
- **Session ID**: {session_id}
- **상태**: {workspace.get('status', 'unknown')}
- **생성 시간**: {workspace.get('created_at')}
- **메시지 수**: {len(workspace.get('messages', []))}

## DAG 정보
- **DAG ID**: {workspace.get('dag_id', 'N/A')}
- **Run ID**: {workspace.get('dag_run_id', 'N/A')}
- **Task ID**: {workspace.get('task_id', 'N/A')}

## 실행 히스토리

"""

        for idx, msg in enumerate(workspace.get("messages", []), 1):
            agent = msg.get("agent", "SYSTEM")
            message = msg.get("message", "")
            timestamp = msg.get("timestamp", "")

            emoji_map = {
                "MONITOR": "🔍",
                "ANALYZER": "🔬",
                "INTERACTION": "💬",
                "ACTION": "⚡",
                "SYSTEM": "🤖",
            }
            emoji = emoji_map.get(agent, "📌")

            md_content += f"### {idx}. {emoji} {agent}\n"
            md_content += f"**시간**: {timestamp}\n\n"
            md_content += f"{message}\n\n"

        return md_content

    def get_sessions_stats(
        self, workspaces: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        모든 세션의 통계 정보

        Args:
            workspaces: 모든 세션 데이터

        Returns:
            통계 정보
        """
        total_messages = sum(len(ws.get("messages", [])) for ws in workspaces.values())
        total_sessions = len(workspaces)

        active_sessions = sum(
            1 for ws in workspaces.values() if ws.get("status") == "active"
        )
        completed_sessions = sum(
            1 for ws in workspaces.values() if ws.get("status") == "completed"
        )

        agent_totals = {}
        for workspace in workspaces.values():
            for msg in workspace.get("messages", []):
                agent = msg.get("agent", "UNKNOWN")
                agent_totals[agent] = agent_totals.get(agent, 0) + 1

        return {
            "total_sessions": total_sessions,
            "active_sessions": active_sessions,
            "completed_sessions": completed_sessions,
            "total_messages": total_messages,
            "avg_messages_per_session": (
                total_messages / total_sessions if total_sessions > 0 else 0
            ),
            "agent_distribution": agent_totals,
        }


class SessionValidator:
    """세션 데이터 검증"""

    @staticmethod
    def validate_workspace(workspace: Dict[str, Any]) -> tuple[bool, List[str]]:
        """
        워크스페이스 데이터 검증

        Args:
            workspace: 워크스페이스 데이터

        Returns:
            (유효성, 에러 메시지 리스트)
        """
        errors = []

        # 필수 필드 확인
        required_fields = ["messages", "status", "created_at"]
        for field in required_fields:
            if field not in workspace:
                errors.append(f"Missing required field: {field}")

        # 메시지 형식 확인
        if "messages" in workspace:
            if not isinstance(workspace["messages"], list):
                errors.append("'messages' must be a list")
            else:
                for idx, msg in enumerate(workspace["messages"]):
                    if not isinstance(msg, dict):
                        errors.append(f"Message {idx} is not a dict")
                    else:
                        msg_fields = ["type", "agent", "message", "timestamp"]
                        for field in msg_fields:
                            if field not in msg:
                                errors.append(f"Message {idx} missing field: {field}")

        # 상태 확인
        valid_statuses = ["active", "completed", "failed", "paused"]
        if "status" in workspace and workspace["status"] not in valid_statuses:
            errors.append(f"Invalid status: {workspace['status']}")

        return len(errors) == 0, errors


class SessionAnalyzer:
    """세션 분석"""

    @staticmethod
    def get_timeline(workspace: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        메시지 타임라인 생성

        Args:
            workspace: 워크스페이스 데이터

        Returns:
            타임라인 데이터
        """
        timeline = []

        for msg in workspace.get("messages", []):
            timeline.append(
                {
                    "timestamp": msg.get("timestamp"),
                    "agent": msg.get("agent"),
                    "type": msg.get("type"),
                    "message_length": len(msg.get("message", "")),
                }
            )

        return timeline

    @staticmethod
    def get_agent_sequence(workspace: Dict[str, Any]) -> List[str]:
        """
        에이전트 실행 순서

        Args:
            workspace: 워크스페이스 데이터

        Returns:
            에이전트 순서
        """
        sequence = []
        for msg in workspace.get("messages", []):
            agent = msg.get("agent")
            if agent and (not sequence or sequence[-1] != agent):
                sequence.append(agent)

        return sequence

    @staticmethod
    def calculate_duration(workspace: Dict[str, Any]) -> Optional[float]:
        """
        세션 실행 시간 계산 (초)

        Args:
            workspace: 워크스페이스 데이터

        Returns:
            실행 시간 (초)
        """
        messages = workspace.get("messages", [])
        if len(messages) < 2:
            return None

        try:
            start_time = datetime.fromisoformat(messages[0]["timestamp"])
            end_time = datetime.fromisoformat(messages[-1]["timestamp"])
            return (end_time - start_time).total_seconds()
        except (ValueError, KeyError):
            return None


# 사용 예시
if __name__ == "__main__":
    # 세션 매니저 초기화
    manager = SessionManager()

    # 예제 워크스페이스
    example_workspace = {
        "messages": [
            {
                "type": "agent_update",
                "agent": "MONITOR",
                "message": "Airflow 모니터링 중...",
                "timestamp": datetime.now().isoformat(),
            },
            {
                "type": "agent_update",
                "agent": "ANALYZER",
                "message": "분석 완료",
                "timestamp": datetime.now().isoformat(),
            },
        ],
        "status": "completed",
        "created_at": datetime.now().isoformat(),
        "dag_id": "example_dag",
        "dag_run_id": "run_123",
        "task_id": "task_001",
    }

    # 검증
    validator = SessionValidator()
    is_valid, errors = validator.validate_workspace(example_workspace)
    print(f"Valid: {is_valid}, Errors: {errors}")

    # 분석
    analyzer = SessionAnalyzer()
    sequence = analyzer.get_agent_sequence(example_workspace)
    print(f"Agent sequence: {sequence}")

    # 요약
    summary = manager.get_session_summary(example_workspace)
    print(f"Summary: {summary}")
