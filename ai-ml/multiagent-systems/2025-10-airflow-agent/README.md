# Airflow Monitoring Agent

프로덕션 레벨의 AI 기반 멀티에이전트 시스템으로 Apache Airflow를 모니터링하고, 오류를 자동으로 진단하며, 사용자와 상호작용하여 문제를 해결합니다.

## 🌟 주요 기능

- **자동 모니터링**: 실패한 DAG Run과 Task를 자동으로 감지
- **지능형 분석**: LLM을 활용한 오류 근본 원인 분석
- **인터넷 검색**: 에러 메시지를 검색하여 해결 방법 탐색
- **사용자 상호작용**: Streamlit을 통한 직관적인 대화형 인터페이스
- **자동 복구**: 사용자 승인 후 실패한 Task 자동 재실행
- **완벽한 추적**: Langfuse를 통한 전체 워크플로우 관찰성

## 🏗️ 아키텍처

### Multi-Agent System (LangGraph)

1. **AirflowMonitorAgent** (🔍)
   - Airflow REST API를 통해 실패한 DAG/Task 감지
   - 기본 오류 정보 수집

2. **ErrorAnalyzerAgent** (🔬)
   - Task 로그 및 DAG 소스 코드 분석
   - 인터넷 검색을 통한 해결책 탐색
   - LLM 기반 종합 분석 보고서 생성

3. **UserInteractionAgent** (💬)
   - 분석 결과를 사용자 친화적으로 제시
   - 다음 액션에 대한 사용자 승인 요청
   - 사용자 피드백 처리

4. **ActionAgent** (⚡)
   - 승인된 액션 실행 (Task Clear/Retry)
   - Airflow API를 통한 실제 조치 수행
   - 실행 결과 보고

### Technology Stack

**Backend (FastAPI)**
- FastAPI: 고성능 비동기 API 서버
- LangChain/LangGraph: 멀티에이전트 오케스트레이션
- Langfuse: LLM 관찰성 및 추적
- httpx: Airflow REST API 클라이언트

**Frontend (Streamlit)**
- Streamlit: 인터랙티브 웹 UI
- Server-Sent Events (SSE): 실시간 스트리밍

**Tools & Integrations**
- DuckDuckGo Search: 인터넷 검색
- Apache Airflow REST API v2
- OpenAI GPT-4: LLM 추론

## 📁 프로젝트 구조

```
airflow_monitoring_agent/
├── server/                     # FastAPI 백엔드
│   ├── agents/                # 각 에이전트 구현
│   │   ├── airflow_monitor_agent.py
│   │   ├── error_analyzer_agent.py
│   │   ├── user_interaction_agent.py
│   │   └── action_agent.py
│   ├── services/              # 외부 서비스 클라이언트
│   │   └── airflow_client.py  # Airflow REST API 클라이언트
│   ├── tools/                 # 에이전트 도구
│   │   └── search.py          # 인터넷 검색 도구
│   ├── workflow/              # LangGraph 워크플로우
│   │   ├── state.py           # 상태 정의
│   │   └── graph.py           # 그래프 구성
│   ├── routers/               # API 엔드포인트
│   │   └── agent_router.py
│   ├── config.py              # 설정 관리
│   ├── langfuse_config.py     # Langfuse 설정
│   └── main.py                # FastAPI 앱 초기화
│
├── app/                       # Streamlit 프론트엔드
│   ├── components/
│   │   └── chat.py            # 채팅 UI 및 SSE 처리
│   ├── utils/
│   │   └── state_manager.py  # 세션 상태 관리
│   └── main.py                # Streamlit 앱 실행
│
├── .env                       # 환경 변수 (생성 필요)
├── requirements.txt           # Python 의존성
└── README.md                  # 본 문서
```

## 🚀 설치 및 실행

### 1. 환경 준비

```bash
# Python 3.9+ 필요
python --version

# 가상환경 생성 (권장)
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 의존성 설치
pip install -r requirements.txt
```

### 2. 환경 변수 설정

`.env` 파일을 프로젝트 루트에 생성하고 다음 내용을 채웁니다:

```bash
# Airflow Configuration
AIRFLOW_HOST=http://localhost:8080
AIRFLOW_USERNAME=admin
AIRFLOW_PASSWORD=admin

# OpenAI Configuration
OPENAI_API_KEY=sk-your-openai-api-key-here

# Langfuse Configuration
LANGFUSE_PUBLIC_KEY=pk-lf-your-public-key
LANGFUSE_SECRET_KEY=sk-lf-your-secret-key
LANGFUSE_HOST=https://cloud.langfuse.com

# FastAPI Server Configuration
API_BASE_URL=http://localhost:8000
SERVER_HOST=0.0.0.0
SERVER_PORT=8000

# Streamlit Configuration
STREAMLIT_SERVER_PORT=8501
```

### 3. 서버 실행

**터미널 1 - FastAPI 서버:**

```bash
# 개발 모드 (자동 재시작)
python -m server.main

# 또는 uvicorn 직접 사용
uvicorn server.main:app --reload --host 0.0.0.0 --port 8000
```

서버가 시작되면: http://localhost:8000/docs 에서 API 문서 확인 가능

**터미널 2 - Streamlit 클라이언트:**

```bash
streamlit run app/main.py --server.port 8501
```

클라이언트가 시작되면: http://localhost:8501 에서 UI 접속

## 📖 사용 방법

### 기본 사용

1. Streamlit UI에 접속 (http://localhost:8501)
2. 채팅 입력창에 "모니터링 시작" 또는 아무 메시지나 입력
3. 시스템이 자동으로:
   - 실패한 DAG/Task 감지
   - 오류 분석 수행
   - 해결 방법 제시
   - 액션 승인 요청
4. 제시된 옵션 중 선택:
   - "재실행" 또는 "1": Task를 Clear하여 자동 재실행
   - "수동" 또는 "2": 수동 처리를 위해 건너뛰기
   - "보고서" 또는 "3": 전체 분석 보고서 확인

### 특정 Task 분석

사이드바의 "고급 옵션"을 사용하여 특정 DAG/Task를 직접 분석할 수 있습니다:

1. 사이드바 열기
2. "고급 옵션" 확장
3. DAG ID, DAG Run ID, Task ID 입력
4. "특정 Task 분석" 버튼 클릭

### API 직접 사용

FastAPI 서버를 직접 호출할 수도 있습니다:

```bash
# Health check
curl http://localhost:8000/api/v1/agent/health

# 워크플로우 실행 (동기)
curl -X POST http://localhost:8000/api/v1/agent/invoke \
  -H "Content-Type: application/json" \
  -d '{
    "dag_id": "example_dag",
    "dag_run_id": "manual__2024-01-01T00:00:00",
    "task_id": "failed_task"
  }'

# 워크플로우 스트리밍 (SSE)
curl -X POST http://localhost:8000/api/v1/agent/stream \
  -H "Content-Type: application/json" \
  -d '{}'
```

## 🔧 설정 옵션

### Airflow 연결

`server/config.py`에서 다음 설정을 수정할 수 있습니다:

- `AIRFLOW_HOST`: Airflow 웹서버 URL
- `AIRFLOW_USERNAME`: 기본 인증 사용자명
- `AIRFLOW_PASSWORD`: 기본 인증 비밀번호

### LLM 모델

`server/config.py`에서:

- `OPENAI_MODEL`: 사용할 OpenAI 모델 (기본: gpt-4o)
- `OPENAI_TEMPERATURE`: 생성 온도 (기본: 0.7)

### 모니터링 설정

- `MONITORING_INTERVAL`: 모니터링 주기 (초)
- `MAX_LOG_LENGTH`: 로그 최대 길이 (문자)

## 🧪 테스트

### 단위 테스트

```bash
# pytest 설치
pip install pytest pytest-asyncio pytest-cov

# 테스트 실행
pytest tests/ -v

# 커버리지 포함
pytest tests/ --cov=server --cov-report=html
```

### 통합 테스트

실제 Airflow 인스턴스가 필요합니다:

```bash
# Airflow 시작 (Docker Compose 권장)
docker-compose up -d

# 통합 테스트 실행
pytest tests/integration/ -v
```

## 📊 모니터링 및 디버깅

### Langfuse 대시보드

1. https://cloud.langfuse.com 접속
2. 프로젝트 생성 및 API 키 획득
3. `.env`에 키 설정
4. 워크플로우 실행 후 대시보드에서 추적 확인:
   - 각 에이전트 실행 시간
   - LLM 호출 내역
   - 도구 사용 로그
   - 전체 워크플로우 시각화

### 로그 확인

서버 로그는 콘솔에 출력됩니다:

```bash
# 로그 레벨 변경
export DEBUG=true
python -m server.main
```

### API 문서

FastAPI 자동 생성 문서:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 🐛 트러블슈팅

### Airflow 연결 실패

```
AirflowAPIError: HTTP 401: Unauthorized
```

**해결**: `.env`의 Airflow 인증 정보 확인

### OpenAI API 오류

```
OpenAI API error: Invalid API key
```

**해결**: `.env`의 `OPENAI_API_KEY` 확인

### 스트리밍 끊김

**해결**:
- 네트워크 안정성 확인
- 방화벽 설정 확인
- 프록시 설정 확인

### Langfuse 연결 실패

**해결**:
- Langfuse 키 유효성 확인
- 네트워크 연결 확인
- Self-hosted 사용 시 `LANGFUSE_HOST` 확인

## 🔐 보안 고려사항

### 프로덕션 배포 시

1. **환경 변수**: `.env` 파일을 절대 커밋하지 마세요
2. **CORS**: `server/main.py`의 CORS 설정을 실제 도메인으로 제한
3. **인증**: FastAPI에 인증 미들웨어 추가 권장
4. **HTTPS**: 프로덕션에서는 HTTPS 사용 필수
5. **API 키**: 비밀 관리 시스템 사용 (AWS Secrets Manager 등)

## 🚀 프로덕션 배포

### Docker 사용

```dockerfile
# Dockerfile 예시
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 서버 실행
CMD ["uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Docker Compose

```yaml
version: '3.8'

services:
  api:
    build: .
    ports:
      - "8000:8000"
    env_file:
      - .env
    restart: unless-stopped

  ui:
    build: .
    command: streamlit run app/main.py --server.port 8501
    ports:
      - "8501:8501"
    env_file:
      - .env
    depends_on:
      - api
    restart: unless-stopped
```

### Kubernetes

Helm 차트 또는 매니페스트 파일 작성 권장

## 📝 라이선스

이 프로젝트는 상용 사용 가능한 완전한 프로덕션 레벨 코드입니다.

## 🤝 기여

버그 리포트, 기능 제안, Pull Request 환영합니다!

## 📧 지원

문제가 있거나 질문이 있으면 이슈를 생성해주세요.

---

**Built with** ❤️ **using LangGraph, FastAPI, and Streamlit**
