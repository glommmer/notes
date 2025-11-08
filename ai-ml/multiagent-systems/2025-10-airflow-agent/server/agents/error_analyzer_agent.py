"""
Error Analyzer Agent - Analyzes errors and searches for solutions
"""

import logging
from typing import Dict, Any
from langchain_openai import ChatOpenAI, AzureChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain.agents import create_openai_tools_agent, AgentExecutor
from server.workflow.state import AgentState, AgentType
from server.services.airflow_client import AirflowClient, AirflowAPIError
from server.tools.search import create_search_tool
from server.config import settings

logger = logging.getLogger(__name__)


class ErrorAnalyzerAgent:
    """
    Agent responsible for analyzing errors and finding solutions

    This agent:
    1. Retrieves task logs from Airflow
    2. Retrieves DAG source code if needed
    3. Uses LLM with tools to analyze the error
    4. Searches internet for solutions
    5. Generates analysis report with root cause and solutions
    """

    def __init__(self, airflow_client: AirflowClient):
        """
        Initialize analyzer agent

        Args:
            airflow_client: Configured Airflow API client
        """
        self.client = airflow_client
        self.agent_type = AgentType.ANALYZER

        try:
            # Initialize LLM
            self.llm = ChatOpenAI(
                model=settings.OPENAI_MODEL,
                temperature=settings.OPENAI_TEMPERATURE,
                api_key=settings.OPENAI_API_KEY,
                base_url=settings.OPENAI_BASE_URL,
            )

            # self.llm = AzureChatOpenAI(
            #     openai_api_key=settings.AZURE_OPENAI_API_KEY,
            #     azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
            #     azure_deployment=settings.AZURE_OPENAI_DEPLOYMENT,
            #     api_version=settings.AZURE_OPENAI_API_VERSION,
            #     temperature=0.7,
            #     # streaming=True,  # 스트리밍 활성화
            # )

            # Setup tools
            self.tools = [create_search_tool()]

            # Create analysis agent
            self.analysis_agent = self._create_analysis_agent()

            logger.info("ErrorAnalyzerAgent initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize ErrorAnalyzerAgent: {str(e)}")
            raise

    def _create_analysis_agent(self) -> AgentExecutor:
        """
        Create LangChain agent with tools for analysis

        Returns:
            AgentExecutor instance
        """
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    """당신은 Apache Airflow 전문가입니다.

당신의 임무는 실패한 Airflow Task의 로그와 소스코드를 분석하여:
1. 오류의 근본 원인(root cause)을 파악하고
2. 구체적인 해결 방법을 제시하는 것입니다.

사용 가능한 도구:
- internet_search: 에러 메시지, 스택 트레이스, 라이브러리 관련 정보를 검색

분석 시 고려사항:
- Python 스택 트레이스에서 실제 에러 원인 파악
- 라이브러리 버전 호환성 문제
- 설정 오류 (connection, variable 등)
- 데이터 품질 문제
- 리소스 부족 (메모리, 디스크 등)

반드시 다음 형식으로 답변하세요:

## 🔍 오류 분석

### 근본 원인 (Root Cause)
[오류의 근본 원인을 명확하게 설명]

### 오류 발생 위치
[어느 코드/라인에서 발생했는지]

### 오류 유형
[에러의 카테고리: Python Exception, Database Error, Network Error 등]

## 💡 해결 방안

### 권장 해결 방법
1. [구체적인 해결 단계]
2. [필요한 경우 코드 수정 예시]
3. [설정 변경 방법]

### 예방 조치
- [재발 방지를 위한 제안]

## 🔧 제안 액션
- [ ] Task 재실행 (Clear)
- [ ] 코드 수정 필요
- [ ] 설정 변경 필요
- [ ] 인프라 점검 필요
""",
                ),
                ("human", "{input}"),
                ("placeholder", "{agent_scratchpad}"),
            ]
        )

        agent = create_openai_tools_agent(self.llm, self.tools, prompt)

        return AgentExecutor(
            agent=agent,
            tools=self.tools,
            verbose=True,
            max_iterations=3,  # Reduced to prevent timeout
            handle_parsing_errors=True,
            return_intermediate_steps=False,  # Simplify output
        )

    def __call__(self, state: AgentState) -> Dict[str, Any]:
        """
        Execute error analysis

        Args:
            state: Current workflow state

        Returns:
            Updated state with analysis results
        """
        logger.info("🔬 ErrorAnalyzerAgent: Starting analysis...")

        dag_id = state.get("dag_id")
        dag_run_id = state.get("dag_run_id")
        task_id = state.get("task_id")
        try_number = state.get("try_number", 1)

        if not all([dag_id, dag_run_id, task_id]):
            logger.error("Missing required identifiers")
            return {
                "analysis_report": "오류 분석 실패: 필수 정보 누락 (DAG ID, Run ID, Task ID)",
                "current_agent": self.agent_type.value,
            }

        try:
            # Step 1: Get task logs
            logger.info("Retrieving task logs...")
            try:
                logs = self.client.get_task_log(dag_id, dag_run_id, task_id, try_number)
                logger.info(f"Retrieved {len(logs)} characters of logs")
            except AirflowAPIError as e:
                logger.error(f"Failed to get task logs: {e}")
                logs = f"로그를 가져올 수 없습니다: {str(e)}"

            # Step 2: Get DAG source code
            logger.info("Retrieving DAG source code...")
            dag_source = None
            try:
                dag_details = self.client.get_dag_details(dag_id)
                file_token = dag_details.get("file_token")
                if file_token:
                    dag_source = self.client.get_dag_source(dag_id)
                    logger.info(
                        f"Retrieved {len(dag_source)} characters of source code"
                    )
                else:
                    dag_source = "소스 코드의 file_token을 찾을 수 없습니다."
            except AirflowAPIError as e:
                logger.warning(f"Could not retrieve DAG source: {e}")
                dag_source = f"소스 코드를 가져올 수 없습니다: {str(e)}"

            # Step 3: Prepare analysis input
            analysis_input = self._prepare_analysis_input(
                dag_id, task_id, logs, dag_source
            )

            # Step 4: Run LLM analysis with tools
            logger.info("Running LLM analysis...")
            try:
                result = self.analysis_agent.invoke({"input": analysis_input})
                analysis_report = result.get("output", "분석 실패")
                logger.info("LLM analysis completed successfully")
            except Exception as llm_error:
                logger.error(f"LLM analysis failed: {str(llm_error)}")
                # Fallback: Create basic analysis without LLM
                analysis_report = self._create_fallback_analysis(logs)

            # Extract root cause and solution from report
            root_cause, solution = self._extract_key_info(analysis_report)

            logger.info("Analysis completed successfully")

            return {
                "logs": logs[:2000],  # Truncate for state
                "dag_source": dag_source[:2000] if dag_source else None,  # Truncate
                "analysis_report": analysis_report,
                "root_cause": root_cause,
                "suggested_solution": solution,
                "current_agent": self.agent_type.value,
            }

        except Exception as e:
            logger.error(f"Analysis error: {str(e)}", exc_info=True)
            return {
                "analysis_report": f"오류 분석 중 문제 발생: {str(e)}",
                "root_cause": "분석 실패",
                "suggested_solution": "수동으로 로그를 확인해주세요",
                "current_agent": self.agent_type.value,
            }

    def _prepare_analysis_input(
        self, dag_id: str, task_id: str, logs: str, dag_source: str
    ) -> str:
        """
        Prepare input for analysis agent

        Args:
            dag_id: DAG identifier
            task_id: Task identifier
            logs: Task execution logs
            dag_source: DAG source code

        Returns:
            Formatted input string
        """
        # Truncate logs and source for LLM context
        log_sample = logs[-3000:] if len(logs) > 3000 else logs
        source_sample = (
            dag_source[:2000] if dag_source and len(dag_source) > 2000 else dag_source
        )

        input_text = f"""다음 Airflow Task의 실패 원인을 분석해주세요.

## Task 정보
- DAG ID: {dag_id}
- Task ID: {task_id}

## 실행 로그 (마지막 부분)
```
{log_sample}
```

## DAG 소스 코드 (일부)
```python
{source_sample if source_sample else '소스 코드를 사용할 수 없습니다.'}
```

위 정보를 바탕으로 오류를 분석하고, 필요한 경우 인터넷 검색을 통해 
관련 정보를 찾아 종합적인 분석 보고서를 작성해주세요.
"""
        return input_text

    def _create_fallback_analysis(self, logs: str) -> str:
        """
        Create fallback analysis when LLM fails

        Args:
            logs: Task logs

        Returns:
            Basic analysis report
        """
        return f"""## 🔍 오류 분석 (자동 생성)

### 로그 정보
```
{logs[-1000:]}
```

### 권장 사항
1. 위 로그를 검토하여 에러 메시지를 확인하세요
2. Airflow UI에서 전체 로그를 확인하세요
3. 에러 메시지를 검색하여 해결 방법을 찾아보세요

### 제안 액션
- [ ] Task 재실행 시도
- [ ] 수동으로 로그 분석
"""

    def _extract_key_info(self, report: str) -> tuple[str, str]:
        """
        Extract root cause and solution from analysis report

        Args:
            report: Analysis report text

        Returns:
            Tuple of (root_cause, suggested_solution)
        """
        # Simple extraction - look for sections
        root_cause = "분석 보고서 참조"
        solution = "분석 보고서 참조"

        lines = report.split("\n")
        in_root_cause = False
        in_solution = False
        root_lines = []
        solution_lines = []

        for line in lines:
            if "근본 원인" in line or "Root Cause" in line:
                in_root_cause = True
                in_solution = False
                continue
            elif "해결 방안" in line or "해결 방법" in line:
                in_solution = True
                in_root_cause = False
                continue
            elif line.startswith("##"):
                in_root_cause = False
                in_solution = False
                continue

            if in_root_cause and line.strip() and not line.startswith("#"):
                root_lines.append(line.strip())
            elif in_solution and line.strip() and not line.startswith("#"):
                solution_lines.append(line.strip())

        if root_lines:
            root_cause = " ".join(root_lines[:2])[:200]  # Truncate
        if solution_lines:
            solution = " ".join(solution_lines[:3])[:300]  # Truncate

        return root_cause, solution
