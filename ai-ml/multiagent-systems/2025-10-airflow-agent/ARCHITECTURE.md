# Architecture Documentation

## System Overview

Airflow Monitoring Agent는 4개의 특화된 에이전트로 구성된 멀티에이전트 시스템입니다. LangGraph를 사용하여 에이전트 간 워크플로우를 오케스트레이션하고, Langfuse로 전체 과정을 추적합니다.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                     Streamlit UI (Client)                    │
│                         Port 8501                             │
└───────────────────────────┬─────────────────────────────────┘
                            │ SSE (Server-Sent Events)
                            │ HTTP POST /api/v1/agent/stream
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI Server (Backend)                  │
│                         Port 8000                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │           LangGraph Workflow Orchestrator           │   │
│  │                                                       │   │
│  │  ┌──────────────────────────────────────────────┐  │   │
│  │  │  1. AirflowMonitorAgent                      │  │   │
│  │  │     - Detect failed DAG runs                 │  │   │
│  │  │     - Identify failed tasks                  │  │   │
│  │  └──────────────┬───────────────────────────────┘  │   │
│  │                 │                                    │   │
│  │  ┌──────────────▼───────────────────────────────┐  │   │
│  │  │  2. ErrorAnalyzerAgent                       │  │   │
│  │  │     - Get task logs                          │  │   │
│  │  │     - Get DAG source                         │  │   │
│  │  │     - Search internet (DuckDuckGo)          │  │   │
│  │  │     - Analyze with LLM (GPT-4)              │  │   │
│  │  └──────────────┬───────────────────────────────┘  │   │
│  │                 │                                    │   │
│  │  ┌──────────────▼───────────────────────────────┐  │   │
│  │  │  3. UserInteractionAgent                     │  │   │
│  │  │     - Present analysis to user               │  │   │
│  │  │     - Generate user-friendly questions       │  │   │
│  │  │     - Process user feedback                  │  │   │
│  │  └──────────────┬───────────────────────────────┘  │   │
│  │                 │                                    │   │
│  │  ┌──────────────▼───────────────────────────────┐  │   │
│  │  │  4. ActionAgent                              │  │   │
│  │  │     - Execute approved action                │  │   │
│  │  │     - Clear task instance (retry)            │  │   │
│  │  │     - Report results                         │  │   │
│  │  └──────────────────────────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────┘   │
└───────────────────┬────────────────┬────────────────────────┘
                    │                │
         ┌──────────▼─────┐  ┌──────▼──────────┐
         │  Apache Airflow │  │   Langfuse      │
         │   REST API v2   │  │  (Observability)│
         │   Port 8080     │  │                 │
         └─────────────────┘  └─────────────────┘
```

## Component Details

### 1. Frontend (Streamlit)

**Location**: `app/`

**Responsibilities**:
- User interface rendering
- Real-time event streaming display
- User input collection
- Session state management

**Key Files**:
- `app/main.py`: Application entry point
- `app/components/chat.py`: Chat interface and SSE client
- `app/utils/state_manager.py`: Session state management

**Communication**:
- Connects to FastAPI via HTTP
- Receives real-time updates via SSE
- Sends user input via POST requests

### 2. Backend (FastAPI)

**Location**: `server/`

**Responsibilities**:
- API endpoint management
- Workflow orchestration
- Agent coordination
- Event streaming to clients

**Key Files**:
- `server/main.py`: FastAPI application
- `server/routers/agent_router.py`: API endpoints
- `server/config.py`: Configuration management
- `server/langfuse_config.py`: Observability setup

**Endpoints**:
- `POST /api/v1/agent/invoke`: Synchronous workflow execution
- `POST /api/v1/agent/stream`: Streaming workflow execution (SSE)
- `GET /api/v1/agent/health`: Health check

### 3. Multi-Agent System (LangGraph)

**Location**: `server/workflow/` and `server/agents/`

**State Definition** (`server/workflow/state.py`):
```python
class AgentState(TypedDict):
    # Identifiers
    dag_id: Optional[str]
    dag_run_id: Optional[str]
    task_id: Optional[str]
    
    # Error information
    error_message: Optional[str]
    logs: Optional[str]
    
    # Analysis results
    analysis_report: Optional[str]
    root_cause: Optional[str]
    
    # User interaction
    user_input: Optional[str]
    user_question: Optional[str]
    
    # Action
    final_action: Optional[str]
    is_resolved: bool
```

**Agent Flow**:

```
START
  ↓
AirflowMonitorAgent
  ↓ (found error?)
  ├─ Yes → ErrorAnalyzerAgent
  └─ No → END
         ↓
    UserInteractionAgent
         ↓ (user input?)
         ├─ Waiting → UserInteractionAgent (loop)
         └─ Received → ActionAgent
                  ↓
                 END
```

### 4. Agent Implementations

#### AirflowMonitorAgent

**File**: `server/agents/airflow_monitor_agent.py`

**Purpose**: Entry point - detects failures

**Process**:
1. Call Airflow API: `GET /api/v2/dags/{dag_id}/dagRuns?state=failed`
2. Get most recent failed run
3. Call Airflow API: `GET /api/v2/dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances?state=failed`
4. Identify failed tasks
5. Update state with identifiers

**Output State**:
- `dag_id`
- `dag_run_id`
- `task_id`
- `try_number`
- `error_message`

#### ErrorAnalyzerAgent

**File**: `server/agents/error_analyzer_agent.py`

**Purpose**: Deep analysis using LLM and tools

**Tools Available**:
- `internet_search`: DuckDuckGo search for error messages

**Process**:
1. Get task logs via Airflow API
2. Get DAG source code via Airflow API
3. Create LangChain agent with tools
4. Invoke LLM with logs and source code
5. LLM may use tools to search for solutions
6. Generate comprehensive analysis report

**Output State**:
- `logs`
- `dag_source`
- `analysis_report`
- `root_cause`
- `suggested_solution`

#### UserInteractionAgent

**File**: `server/agents/user_interaction_agent.py`

**Purpose**: User communication and decision gathering

**Process**:
1. Check if user input already provided
2. If not, generate user-friendly question using LLM
3. Present analysis results
4. Offer action options:
   - Clear/Retry task
   - Manual handling
   - View full report
5. If input received, parse decision

**Output State**:
- `user_question`
- `requires_user_input`
- `final_action`

#### ActionAgent

**File**: `server/agents/action_agent.py`

**Purpose**: Execute approved actions

**Actions**:
- `CLEAR_TASK`: Clear task instance for retry
- `SKIP`: Skip automatic action
- `SHOW_REPORT`: Display full analysis

**Process** (for CLEAR_TASK):
1. Dry run: Check what would be cleared
2. Actual clear: Call Airflow API
3. Report results to user

**Output State**:
- `action_result`
- `is_resolved`

### 5. External Services

#### Airflow Client

**File**: `server/services/airflow_client.py`

**Purpose**: Unified interface to Airflow REST API

**Key Methods**:
```python
get_failed_dag_runs(dag_id, limit)
get_failed_task_instances(dag_id, dag_run_id)
get_task_log(dag_id, dag_run_id, task_id, try_number)
get_dag_source(file_token)
clear_task_instance(dag_id, task_ids, ...)
```

**Authentication**: HTTP Basic Auth

#### Langfuse Integration

**File**: `server/langfuse_config.py`

**Purpose**: LLM observability and tracing

**What's Tracked**:
- Each agent execution
- LLM calls and responses
- Tool invocations
- Workflow steps
- Execution times
- Costs

**Usage**:
```python
handler = create_langfuse_handler(session_id)
app.invoke(state, config={"callbacks": [handler]})
```

### 6. Tools

#### Internet Search Tool

**File**: `server/tools/search.py`

**Implementation**: DuckDuckGo Search API

**Purpose**: Search for error messages, stack traces, solutions

**Usage in Agent**:
```python
tools = [create_search_tool()]
agent = create_openai_tools_agent(llm, tools, prompt)
```

## Data Flow

### Typical Workflow Execution

1. **User Action**: User clicks "Start Monitoring" in UI

2. **Client → Server**: 
   ```
   POST /api/v1/agent/stream
   Body: {}
   ```

3. **Server Initializes**:
   - Creates LangGraph workflow
   - Initializes AgentState
   - Sets up Langfuse tracking

4. **Workflow Execution**:
   
   a. **Monitor Phase**:
   ```
   AirflowMonitorAgent
   ├─ GET /api/v2/dags/~/dagRuns?state=failed
   ├─ GET /api/v2/dags/{dag}/dagRuns/{run}/taskInstances?state=failed
   └─ Updates state with identifiers
   ```
   
   b. **Analysis Phase**:
   ```
   ErrorAnalyzerAgent
   ├─ GET /api/v2/dags/{dag}/dagRuns/{run}/taskInstances/{task}/logs/{try}
   ├─ GET /api/v2/dags/{dag}/details
   ├─ GET /api/v2/dagSources/{file_token}
   ├─ Creates analysis prompt with logs + source
   ├─ Invokes LLM (may trigger tool calls)
   │   └─ Tool: internet_search(error_message)
   └─ Generates analysis_report
   ```
   
   c. **Interaction Phase**:
   ```
   UserInteractionAgent
   ├─ Formats analysis for user
   ├─ Generates question with LLM
   ├─ Sets requires_user_input = True
   └─ Waits for user response
   ```

5. **Server → Client**: Stream events as SSE
   ```
   data: {"type": "agent_update", "agent": "MONITOR", ...}
   data: {"type": "agent_update", "agent": "ANALYZER", ...}
   data: {"type": "agent_update", "agent": "INTERACTION", ...}
   ```

6. **Client Renders**: Real-time updates in chat interface

7. **User Responds**: Types "재실행"

8. **Client → Server**: 
   ```
   POST /api/v1/agent/stream
   Body: {
     "dag_id": "...",
     "dag_run_id": "...",
     "task_id": "...",
     "user_input": "재실행",
     "session_id": "..."
   }
   ```

9. **Workflow Continues**:
   ```
   UserInteractionAgent
   ├─ Processes user_input
   └─ Sets final_action = "CLEAR_TASK"
   
   ActionAgent
   ├─ POST /api/v2/dags/{dag}/clearTaskInstances (dry_run=true)
   ├─ POST /api/v2/dags/{dag}/clearTaskInstances (dry_run=false)
   ├─ Sets is_resolved = True
   └─ Returns action_result
   ```

10. **Server → Client**: Final events
    ```
    data: {"type": "agent_update", "agent": "ACTION", ...}
    data: {"type": "complete", ...}
    ```

11. **Workflow Ends**: Langfuse trace completed

## State Management

### Server-Side State (LangGraph)

- **Persistence**: In-memory during workflow execution
- **Scope**: Single workflow run
- **Sharing**: All agents access same state dict
- **Updates**: Each agent returns partial state updates

### Client-Side State (Streamlit)

- **Persistence**: Session-based (browser session)
- **Scope**: User session
- **Key Variables**:
  - `monitoring_active`: Boolean
  - `messages`: List of chat messages
  - `current_session_id`: UUID for tracking
  - `waiting_for_input`: Boolean flag
  - `workflow_complete`: Boolean flag

## Error Handling

### Client-Side

```python
try:
    # Stream workflow
except requests.RequestException as e:
    yield {"type": "error", "message": f"Connection error: {e}"}
except Exception as e:
    yield {"type": "error", "message": f"Unexpected error: {e}"}
```

### Server-Side

```python
try:
    # Execute agent
except AirflowAPIError as e:
    return {"error_message": f"Airflow API error: {e}"}
except Exception as e:
    return {"error_message": f"Unexpected error: {e}"}
```

### Graceful Degradation

- If Airflow API fails → Show user-friendly error
- If LLM fails → Use fallback message
- If search fails → Continue without search results
- If Langfuse fails → Continue without tracking

## Security Considerations

### Authentication

- **Airflow**: HTTP Basic Auth (username/password)
- **OpenAI**: API Key in headers
- **Langfuse**: Public/Secret key pair

### Data Protection

- Sensitive data (API keys) in environment variables
- Logs may contain task execution details
- Consider data retention policies

### Network Security

- Use HTTPS in production
- Restrict CORS origins
- Implement rate limiting
- Add authentication middleware to API

## Performance Optimization

### Caching

- LLM responses could be cached for identical queries
- Airflow API responses cached briefly
- Search results cached per session

### Streaming

- SSE for real-time updates reduces polling
- Chunked responses improve perceived performance

### Async Operations

- FastAPI async handlers
- Concurrent API calls where possible

## Scalability

### Horizontal Scaling

- Stateless FastAPI servers
- Load balancer in front
- Session affinity for SSE connections

### Vertical Scaling

- Increase worker threads
- Optimize LLM batch sizes
- Connection pooling for Airflow API

## Monitoring & Observability

### Application Metrics

- Request count, latency (FastAPI)
- Workflow success/failure rate
- Agent execution times

### LLM Metrics (via Langfuse)

- Token usage per workflow
- Cost per execution
- Tool invocation frequency
- Error rates

### Infrastructure Metrics

- CPU, memory usage
- Network I/O
- API rate limits

## Future Enhancements

1. **Multi-DAG Monitoring**: Monitor multiple DAGs simultaneously
2. **Scheduled Monitoring**: Periodic automatic checks
3. **Alert Integration**: Slack/Email notifications
4. **Historical Analysis**: Track recurring failures
5. **Auto-remediation**: Automatic fixes for known issues
6. **Custom Tools**: Pluggable tool system
7. **Multi-tenant**: Support multiple Airflow instances
8. **Advanced Analytics**: Failure pattern detection

---

This architecture provides a solid foundation for production deployment while maintaining flexibility for future enhancements.
