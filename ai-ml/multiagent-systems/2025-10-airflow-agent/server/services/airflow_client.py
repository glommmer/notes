"""
Airflow REST API Client
Handles all interactions with Apache Airflow REST API v2
"""

import time
import httpx
import requests
from typing import List, Dict, Any, Optional
from datetime import datetime
import logging
from server.config import settings

logger = logging.getLogger(__name__)


class AirflowAPIError(Exception):
    """Custom exception for Airflow API errors"""

    pass


class AirflowClient:
    """
    Client for interacting with Apache Airflow REST API
    Based on Airflow REST API Reference v2
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        timeout: float = 30.0,
    ):
        """
        Initialize Airflow API client

        Args:
            base_url: Airflow webserver(api-server) URL
            username: Basic auth username
            password: Basic auth password
            timeout: Request timeout in seconds
        """
        self.base_url = (base_url or settings.AIRFLOW_HOST).rstrip("/")
        self.username = username or settings.AIRFLOW_USERNAME
        self.password = password or settings.AIRFLOW_PASSWORD
        self.timeout = timeout

        token = auth_manager.get_valid_token()
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }

        def log_request(request):
            print(f"➡️ Request: {request.method} {request.url}")

        def log_response(response):
            print(f"⬅️ Response: {response.status_code} from {response.url}")

        # Create httpx client with basic auth
        self.client = httpx.Client(
            # auth=(self.username, self.password),
            headers=self.headers,
            timeout=self.timeout,
            follow_redirects=True,
            event_hooks={
                "request": [log_request],
                "response": [log_response],
            },
        )

    def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Make HTTP request to Airflow API

        Args:
            method: HTTP method (GET, POST, PATCH, DELETE)
            endpoint: API endpoint path
            params: Query parameters
            json_data: JSON request body

        Returns:
            Response JSON data

        Raises:
            AirflowAPIError: If request fails
        """
        url = f"{self.base_url}/api/v2{endpoint}"

        try:
            logger.debug(f"Making {method} request to {url}")
            response = self.client.request(
                method=method, url=url, params=params, json=json_data
            )
            response.raise_for_status()

            if response.status_code == 204:  # No content
                return {}

            return response.json()

        except httpx.HTTPStatusError as e:
            error_msg = f"HTTP {e.response.status_code}: {e.response.text}"
            logger.error(f"Airflow API error: {error_msg}")
            raise AirflowAPIError(error_msg)
        except Exception as e:
            logger.error(f"Request failed: {str(e)}")
            raise AirflowAPIError(f"Request failed: {str(e)}")

    def get_failed_dag_runs(
        self, dag_id: Optional[str] = None, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get all failed DAG runs

        Args:
            dag_id: Specific DAG ID or None for all DAGs
            limit: Maximum number of results

        Returns:
            List of failed DAG run dictionaries
        """
        endpoint = f"/dags/{dag_id or '~'}/dagRuns"
        params = {"state": ["failed"], "limit": limit, "order_by": "-start_date"}

        result = self._make_request("GET", endpoint, params=params)
        dag_runs = result.get("dag_runs", [])

        logger.info(f"Found {len(dag_runs)} failed DAG runs")
        return dag_runs

    def get_dag_run(
        self, dag_id: str, dag_run_id: str, limit: int = 10, start_date_gte: str = None
    ) -> Dict[str, Any]:
        """
        Get specific DAG run details

        Args:
            dag_id: DAG identifier
            dag_run_id: DAG run identifier

        Returns:
            DAG run details
        """

        endpoint = f"/dags/{dag_id}/dagRuns/{dag_run_id}"
        params = {"limit": limit}

        if start_date_gte:
            params["start_date"] = start_date_gte

        return self._make_request("GET", endpoint, params=params)

    def get_dag_runs(
        self,
        dag_id: str = None,
        state: str = None,
        start_date_gte: str = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Get DAG runs

        Args:
            dag_id: DAG ID (use "~" for all DAGs) [web:37]
            state: Filter by state (e.g., "failed", "success")
            start_date_gte: Filter by start date (ISO format)
            limit: Max number of results

        Returns:
            List of DAG run information
        """
        try:
            # dag_id가 "~"이면 모든 DAG 조회
            if dag_id == "~":
                endpoint = f"/dags/~/dagRuns"
                logger.info("Fetching DAG runs for all DAGs (wildcard ~)")
            elif dag_id:
                endpoint = f"/dags/{dag_id}/dagRuns"
            else:
                endpoint = "/dags/~/dagRuns"  # Default to all DAGs

            params = {
                "limit": limit,
                "order_by": "-start_date",
            }

            if state:
                params["state"] = state

            if start_date_gte:
                # ISO 8601 형식으로 변환 (YYYY-MM-DD → YYYY-MM-DDTHH:MM:SSZ)
                from datetime import datetime

                try:
                    # 입력이 YYYY-MM-DD 형식인지 확인
                    if len(start_date_gte) == 10 and start_date_gte.count("-") == 2:
                        # YYYY-MM-DD → YYYY-MM-DDTHH:MM:SSZ
                        dt = datetime.fromisoformat(start_date_gte)
                        start_date_iso = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                    elif "T" in start_date_gte:
                        # 이미 ISO 형식이면 Z 추가 (없는 경우)
                        start_date_iso = (
                            start_date_gte
                            if start_date_gte.endswith("Z")
                            else f"{start_date_gte}Z"
                        )
                    else:
                        start_date_iso = start_date_gte

                    params["start_date_gte"] = start_date_iso
                    logger.info(f"Using start_date_gte: {start_date_iso}")

                except ValueError:
                    logger.warning(
                        f"Invalid date format: {start_date_gte}, using as-is"
                    )
                    params["start_date_gte"] = start_date_gte

            response = self._make_request("GET", endpoint, params=params)

            dag_runs = response.get("dag_runs", [])
            logger.info(f"Found {len(dag_runs)} DAG runs")

            return dag_runs

        except Exception as e:
            logger.error(f"Failed to get DAG runs: {str(e)}")
            raise

    def get_failed_task_instances(
        self, dag_id: str, dag_run_id: str
    ) -> List[Dict[str, Any]]:
        """
        Get all failed task instances for a DAG run

        Args:
            dag_id: DAG identifier
            dag_run_id: DAG run identifier

        Returns:
            List of failed task instance dictionaries
        """
        endpoint = f"/dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances"
        params = {"state": ["failed"], "limit": 100}

        result = self._make_request("GET", endpoint, params=params)
        task_instances = result.get("task_instances", [])

        logger.info(
            f"Found {len(task_instances)} failed tasks in "
            f"DAG {dag_id}, run {dag_run_id}"
        )
        return task_instances

    def get_task_instance(
        self, dag_id: str, dag_run_id: str, task_id: str
    ) -> Dict[str, Any]:
        """
        Get specific task instance details

        Args:
            dag_id: DAG identifier
            dag_run_id: DAG run identifier
            task_id: Task identifier

        Returns:
            Task instance details
        """
        endpoint = f"/dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances/{task_id}"
        return self._make_request("GET", endpoint)

    def get_task_instances(self, dag_id: str, dag_run_id: str) -> List[Dict[str, Any]]:
        """
        Get specific task instance details

        Args:
            dag_id: DAG identifier
            dag_run_id: DAG run identifier

        Returns:
            Task instance details
        """
        endpoint = f"/dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances"
        result = self._make_request("GET", endpoint)
        return result.get("task_instances", [])

    def get_task_log(
        self,
        dag_id: str,
        dag_run_id: str,
        task_id: str,
        try_number: int = 1,
        full_content: bool = True,
    ) -> str:
        """
        Get task execution logs

        Args:
            dag_id: DAG identifier
            dag_run_id: DAG run identifier
            task_id: Task identifier
            try_number: Task attempt number (default: 1)
            full_content: Whether to return full log content

        Returns:
            Task log content as string
        """
        endpoint = (
            f"/dags/{dag_id}/dagRuns/{dag_run_id}/"
            f"taskInstances/{task_id}/logs/{try_number}"
        )
        params = {"full_content": str(full_content).lower()}

        result = self._make_request("GET", endpoint, params=params)
        log_content = result.get("content", "")

        # Truncate if too long
        max_length = settings.MAX_LOG_LENGTH
        if len(log_content) > max_length:
            log_content = log_content[-max_length:]
            log_content = f"[...truncated...]\n{log_content}"

        logger.info(
            f"Retrieved log for task {task_id} "
            f"(try {try_number}): {len(log_content)} characters"
        )
        return log_content

    def get_dag_source(self, dag_id: str) -> str:
        """
        Get DAG source code

        Args:
            dag_id: DAG ID

        Returns:
            DAG source code as string
        """
        endpoint = f"/dagSources/{dag_id}"

        result = self._make_request("GET", endpoint)
        source_code = result.get("content", "")

        logger.info(f"Retrieved DAG source: {len(source_code)} characters")
        return source_code

    def get_dag_details(self, dag_id: str) -> Dict[str, Any]:
        """
        Get DAG details including file token for source code

        Args:
            dag_id: DAG identifier

        Returns:
            DAG details dictionary
        """
        endpoint = f"/dags/{dag_id}/details"
        return self._make_request("GET", endpoint)

    def clear_task_instance(
        self,
        dag_id: str,
        task_ids: List[str],
        dry_run: bool = False,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        only_failed: bool = True,
        only_running: bool = False,
        # include_subdags: bool = False,
        # include_parentdag: bool = False,
        reset_dag_runs: bool = True,
        dag_run_id: Optional[str] = None,
        include_upstream: bool = False,
        include_downstream: bool = False,
        include_future: bool = False,
        include_past: bool = False,
    ) -> Dict[str, Any]:
        """
        Clear task instances (for re-running)

        Args:
            dag_id: DAG identifier
            task_ids: List of task IDs to clear
            dry_run: If True, only simulate the clear
            start_date: Start date filter (ISO format)
            end_date: End date filter (ISO format)
            only_failed: Only clear failed tasks
            only_running: Only clear running tasks
            reset_dag_runs: Reset DAG runs
            dag_run_id: Specific DAG run ID to clear (optional)
            include_upstream: Include upstream tasks
            include_downstream: Include downstream tasks
            include_future: Include future task instances
            include_past: Include past task instances

        Returns:
            Result of clear operation
        """
        endpoint = f"/dags/{dag_id}/clearTaskInstances"

        json_data = {
            "dry_run": dry_run,
            "only_failed": only_failed,
            "only_running": only_running,
            "reset_dag_runs": reset_dag_runs,
            "task_ids": task_ids,
            "include_upstream": include_upstream,
            "include_downstream": include_downstream,
            "include_future": include_future,
            "include_past": include_past,
        }

        if start_date:
            json_data["start_date"] = start_date
        if end_date:
            json_data["end_date"] = end_date
        if dag_run_id:
            json_data["dag_run_id"] = dag_run_id

        result = self._make_request("POST", endpoint, json_data=json_data)

        logger.info(
            f"Cleared task instances for DAG {dag_id}, "
            f"tasks: {task_ids}, dry_run: {dry_run}"
        )
        return result

    def get_health(self) -> Dict[str, Any]:
        """
        Check Airflow health status

        Returns:
            Health status dictionary
        """
        endpoint = "/health"
        return self._make_request("GET", endpoint)

    def close(self):
        """Close the HTTP client"""
        self.client.close()

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()


class AirflowAuthManager:
    """
    Airflow API 인증을 위한 JWT(Json Web Token) 관리자

    - Airflow REST API 호출 시 필요한 JWT의 생성, 저장, 자동 갱신 담당
    - 토큰 만료 5분 전에 자동으로 갱신하여 API 호출의 연속성 보장
    """

    def __init__(self, base_url, username, password):
        self.base_url = base_url
        self.username = username
        self.password = password
        self._token = None
        self._token_expiry = 0

    def get_jwt_token(self):
        token_url = f"{self.base_url}/auth/token"
        payload = {"username": self.username, "password": self.password}
        response = requests.post(token_url, json=payload)
        access_token = response.json().get("access_token", None)
        if not access_token:
            print(
                f"## Failed to create token: {response.status_code} - {response.text}"
            )
            return None
        else:
            return access_token

    def get_valid_token(self):
        """JWT 토큰을 가져오거나 갱신"""
        current_time = time.time()

        # 토큰이 없거나 만료 5분 전이면 갱신
        if not self._token or current_time >= (self._token_expiry - 300):
            self._token = self.get_jwt_token()
            if self._token:
                # JWT 토큰의 기본 만료 시간은 24시간 (86400초)
                self._token_expiry = current_time + 86400
            else:
                raise Exception("## Failed to create JWT token")

        return self._token


auth_manager = AirflowAuthManager(
    settings.AIRFLOW_HOST,
    settings.AIRFLOW_USERNAME,
    settings.AIRFLOW_PASSWORD,
)
