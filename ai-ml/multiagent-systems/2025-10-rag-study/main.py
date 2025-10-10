import os
import re
import json
import tqdm
import logging
import operator
from pathlib import Path
from datetime import datetime
from pydantic import BaseModel, Field
from typing import List, TypedDict, Annotated
from langchain.docstore.document import Document
from langchain.document_loaders import PDFPlumberLoader
from langchain.text_splitter import MarkdownHeaderTextSplitter
from langchain_openai import AzureOpenAIEmbeddings, AzureChatOpenAI
from langchain_community.vectorstores import FAISS
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langgraph.graph import StateGraph, START, END


# 환경 변수 설정
AOAI_ENDPOINT = os.getenv("AOAI_ENDPOINT")
AOAI_API_KEY = os.getenv("AOAI_API_KEY")
AOAI_DEPLOY_GPT4O = os.getenv("AOAI_DEPLOY_GPT4O")
AOAI_DEPLOY_GPT4O_MINI = os.getenv("AOAI_DEPLOY_GPT4O_MINI")
AOAI_DEPLOY_EMBED_3_LARGE = os.getenv("AOAI_DEPLOY_EMBED_3_LARGE")

# 로거 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("langgraph_execution.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("urllib3.connectionpool").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


# ===========================
# Enhanced Logging Wrapper
# ===========================

class DetailedLogger:
    """상세 로그를 기록하는 헬퍼 클래스"""

    @staticmethod
    def log_node_start(node_name: str, input_data: dict = None):
        """노드 시작 로그"""
        logger.info("=" * 80)
        logger.info(f"🚀 NODE START: {node_name}")
        logger.info(f"⏰ Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        if input_data:
            logger.info(f"📥 Input Keys: {list(input_data.keys())}")
        logger.info("=" * 80)

    @staticmethod
    def log_node_end(node_name: str, output_data: dict = None, duration: float = None):
        """노드 종료 로그"""
        logger.info(f"✅ NODE END: {node_name}")
        if duration:
            logger.info(f"⏱️  Duration: {duration:.2f}s")
        if output_data:
            logger.info(f"📤 Output Keys: {list(output_data.keys())}")
        logger.info("-" * 80 + "\n")

    @staticmethod
    def log_validation(node_name: str, validation_result: dict):
        """검증 결과 로그"""
        logger.info(f"🔍 VALIDATION RESULT [{node_name}]:")
        logger.info(
            f"  ✓ Supported by documents: {validation_result.get('is_supported')}"
        )
        logger.info(f"  ✓ Useful for question: {validation_result.get('is_useful')}")
        logger.info(
            f"  ✓ Needs refinement: {validation_result.get('needs_refinement')}"
        )

    @staticmethod
    def log_documents(node_name: str, total: int, filtered: int):
        """문서 필터링 로그"""
        logger.info(f"📄 DOCUMENT FILTERING [{node_name}]:")
        logger.info(f"  Total retrieved: {total}")
        logger.info(f"  After filtering: {filtered}")
        logger.info(f"  Filter rate: {(filtered / total * 100):.1f}%")

    @staticmethod
    def log_error(node_name: str, error: Exception):
        """에러 로그"""
        logger.error(f"❌ ERROR in {node_name}: {str(error)}")
        logger.exception(error)


# ===========================
# Custom Reducer for Dictionary Merge
# ===========================

def merge_dicts(existing: dict, updates: dict) -> dict:
    """병렬 노드에서 반환된 dictionary를 병합하는 reducer"""
    if existing is None:
        existing = {}
    merged = existing.copy()
    merged.update(updates)
    return merged


# ===========================
# 1. 문서 처리 및 벡터 저장소 생성
# ===========================

def process_pdf(file_path):
    """PDF 파일을 로드하고 법령 구조에 맞게 청크 분할"""
    loader = PDFPlumberLoader(file_path)
    documents = loader.load()

    file_name = os.path.basename(file_path)

    # 텍스트 패턴 변환 (마크다운 헤더로)
    for doc in documents:
        doc.metadata["file_name"] = file_name
        doc.page_content = re.sub(r"\n(제\d+편)", r"\n# \1", doc.page_content)
        doc.page_content = re.sub(r"\n(제\d+장)", r"\n## \1", doc.page_content)
        doc.page_content = re.sub(r"\n(제\d+절)", r"\n### \1", doc.page_content)
        doc.page_content = re.sub(r"\n(제\d+조)", r"\n#### \1", doc.page_content)

    full_text = "\n\n".join([doc.page_content for doc in documents])

    # 마크다운 헤더 기반 분할
    headers_to_split_on = [
        ("#", "편"),
        ("##", "장"),
        ("###", "절"),
        ("####", "조"),
    ]

    markdown_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=headers_to_split_on, strip_headers=False
    )

    md_header_splits = markdown_splitter.split_text(full_text)

    for split in md_header_splits:
        split.metadata["file_name"] = file_name

    return md_header_splits


def process_multiple_pdfs(directory_path):
    """디렉토리 내 모든 PDF 처리"""
    pdf_files = list(Path(directory_path).glob("*.pdf"))
    print(f"총 {len(pdf_files)}개의 PDF 파일을 찾았습니다.")

    all_splits = []
    for pdf_file in tqdm.tqdm(pdf_files):
        print(f"\n처리 중: {pdf_file.name}")
        try:
            splits = process_pdf(pdf_file)
            all_splits.extend(splits)
            print(f"  -> {len(splits)}개의 청크 생성")
        except Exception as e:
            print(f"  -> 오류 발생: {str(e)}")
            continue

    print(f"\n총 {len(all_splits)}개의 청크가 생성되었습니다.")
    return all_splits


# ===========================
# 2. Multi-Query Retrieval
# ===========================

class MultiQueryGenerator:
    """사용자 질문을 다양한 관점에서 재작성"""

    def __init__(self, llm):
        self.llm = llm
        self.prompt = ChatPromptTemplate.from_template(
            """
당신은 법률 전문가입니다. 사용자의 질문을 분석하여 다양한 관점에서 4가지 버전의 질문을 생성하세요.

원본 질문: {question}

다음 4가지 전략을 사용하여 질문을 재작성하세요:
1. 핵심 키워드 추출 버전 (법률 용어 중심)
2. 구체적 조항 검색 버전 (제X조, 제X편 등)
3. 사례 기반 버전 (실무 적용 관점)
4. 절차적 관점 버전 (어떻게 진행되는가)

각 질문은 한 줄로 작성하고, 번호를 붙여주세요.
"""
        )

    def generate_queries(self, question: str) -> List[str]:
        """다양한 관점의 질문 생성"""
        chain = self.prompt | self.llm | StrOutputParser()
        result = chain.invoke({"question": question})

        queries = [
            line.strip()
            for line in result.split("\n")
            if line.strip() and any(char.isdigit() for char in line[:3])
        ]
        return [question] + queries


# ===========================
# 3. Self-RAG 검증 메커니즘
# ===========================

class RelevanceGrader(BaseModel):
    """검색된 문서의 관련성 평가"""

    binary_score: str = Field(description="문서가 질문과 관련있으면 'yes', 아니면 'no'")
    confidence: int = Field(description="확신도 (1-10)")


class AnswerQuality(BaseModel):
    """생성된 답변의 품질 평가"""

    is_supported: str = Field(description="답변이 문서에 근거하면 'yes', 아니면 'no'")
    is_useful: str = Field(description="답변이 질문에 유용하면 'yes', 아니면 'no'")
    needs_refinement: str = Field(description="답변 개선이 필요하면 'yes', 아니면 'no'")


class SelfRAGValidator:
    """Self-RAG 검증 시스템"""

    def __init__(self, llm):
        self.llm = llm
        self.grader = llm.with_structured_output(RelevanceGrader)
        self.quality_checker = llm.with_structured_output(AnswerQuality)

    def grade_documents(
        self, question: str, documents: List[Document]
    ) -> List[Document]:
        """문서 관련성 검증"""
        grade_prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    """당신은 법률 문서 평가 전문가입니다.
검색된 문서가 질문과 관련이 있는지 평가하세요.
법률 용어, 조항 번호, 절차적 내용이 일치하면 관련있다고 판단하세요.""",
                ),
                ("human", "질문: {question}\n\n문서 내용: {document}"),
            ]
        )

        grader_chain = grade_prompt | self.grader
        filtered_docs = []

        for doc in documents:
            score = grader_chain.invoke(
                {"question": question, "document": doc.page_content}
            )

            if score.binary_score == "yes" and score.confidence >= 6:
                filtered_docs.append(doc)

        return filtered_docs

    def validate_answer(
        self, question: str, answer: str, documents: List[Document]
    ) -> dict:
        """생성된 답변 검증"""
        context = "\n\n".join([doc.page_content for doc in documents])

        quality_prompt = ChatPromptTemplate.from_messages(
            [
                ("system", "답변이 제공된 문서에 근거하고 질문에 유용한지 평가하세요."),
                (
                    "human",
                    """
질문: {question}
답변: {answer}
참고 문서: {context}

답변을 평가하세요.
""",
                ),
            ]
        )

        quality_chain = quality_prompt | self.quality_checker
        quality = quality_chain.invoke(
            {"question": question, "answer": answer, "context": context}
        )

        return {
            "is_supported": quality.is_supported,
            "is_useful": quality.is_useful,
            "needs_refinement": quality.needs_refinement,
        }


# ===========================
# 4. Multi-Agent 시스템
# ===========================

class LegalAgentState(TypedDict):
    """Agent 상태 정의"""

    question: str
    law_type: str
    queries: List[str]
    documents: List[Document]
    filtered_documents: List[Document]
    answer: str
    validation_result: dict
    needs_refinement: bool


class LegalAgent:
    """특정 법률 전문 Agent with detailed logging"""

    def __init__(self, law_type: str, llm, retriever, validator):
        self.law_type = law_type
        self.llm = llm
        self.retriever = retriever
        self.validator = validator
        self.logger = DetailedLogger()

        self.prompts = {
            "개인정보보호법": """당신은 개인정보보호법 전문가입니다.
개인정보 처리자의 의무, 정보주체의 권리, 위반 시 제재를 중심으로 답변하세요.""",
            "형법": """당신은 형법 전문가입니다.
구성요건, 위법성, 책임, 형벌의 종류를 명확히 설명하세요.""",
            "민법": """당신은 민법 전문가입니다.
불법행위, 손해배상청구권, 계약 관계를 중심으로 답변하세요.""",
            "형사소송법": """당신은 형사소송법 전문가입니다.
수사 절차, 공판 절차, 증거법칙을 명확히 설명하세요.""",
            "민사소송법": """당신은 민사소송법 전문가입니다.
소송 제기, 심리 절차, 판결의 효력을 설명하세요.""",
        }

    def retrieve_documents(self, state: LegalAgentState) -> LegalAgentState:
        """다중 쿼리로 문서 검색 with logging"""
        import time

        start_time = time.time()

        self.logger.log_node_start(
            f"{self.law_type} - Retrieve", {"queries_count": len(state["queries"])}
        )

        try:
            all_docs = []
            for i, query in enumerate(state["queries"], 1):
                logger.info(f"  Query {i}/{len(state['queries'])}: {query[:50]}...")
                docs = self.retriever.invoke(query)
                all_docs.extend(docs)
                logger.info(f"    Retrieved: {len(docs)} documents")

            # 중복 제거
            unique_docs = []
            seen_contents = set()
            for doc in all_docs:
                if doc.page_content not in seen_contents:
                    unique_docs.append(doc)
                    seen_contents.add(doc.page_content)

            state["documents"] = unique_docs

            duration = time.time() - start_time
            logger.info(f"📊 Total documents: {len(all_docs)}")
            logger.info(f"📊 Unique documents: {len(unique_docs)}")
            logger.info(
                f"📊 Deduplication rate: {(1 - len(unique_docs) / len(all_docs)) * 100:.1f}%"
            )

            self.logger.log_node_end(
                f"{self.law_type} - Retrieve",
                {"documents_count": len(unique_docs)},
                duration,
            )

        except Exception as e:
            self.logger.log_error(f"{self.law_type} - Retrieve", e)
            raise

        return state

    def grade_documents(self, state: LegalAgentState) -> LegalAgentState:
        """문서 관련성 검증 with logging"""
        import time

        start_time = time.time()

        self.logger.log_node_start(
            f"{self.law_type} - Grade", {"documents_to_grade": len(state["documents"])}
        )

        try:
            filtered = self.validator.grade_documents(
                state["question"], state["documents"]
            )

            state["filtered_documents"] = filtered

            duration = time.time() - start_time
            self.logger.log_documents(
                self.law_type, len(state["documents"]), len(filtered)
            )

            # 필터링된 문서의 메타데이터 로그
            if filtered:
                logger.info(f"  📑 Sample filtered documents:")
                for i, doc in enumerate(filtered[:3], 1):
                    logger.info(
                        f"    {i}. {doc.metadata.get('file_name', 'Unknown')} - {len(doc.page_content)} chars"
                    )

            self.logger.log_node_end(
                f"{self.law_type} - Grade", {"filtered_count": len(filtered)}, duration
            )

        except Exception as e:
            self.logger.log_error(f"{self.law_type} - Grade", e)
            raise

        return state

    def generate_answer(self, state: LegalAgentState) -> LegalAgentState:
        """답변 생성 with logging"""
        import time

        start_time = time.time()

        self.logger.log_node_start(
            f"{self.law_type} - Generate",
            {"context_docs": len(state["filtered_documents"])},
        )

        try:
            context = "\n\n".join(
                [doc.page_content for doc in state["filtered_documents"]]
            )
            context_length = len(context)

            logger.info(f"  📝 Context length: {context_length} characters")
            logger.info(f"  📝 Question: {state['question'][:100]}...")

            prompt = ChatPromptTemplate.from_template(
                f"""
{self.prompts[self.law_type]}

# 참고 조문:
{{context}}

# 질문:
{{question}}

# 답변 작성 지침:
1. 관련 법률 조항을 명시하세요 (예: 개인정보보호법 제X조)
2. 구체적 사례에 적용하여 설명하세요
3. 법적 책임과 절차를 명확히 하세요
4. 한국어로 답변하세요

# {self.law_type} 관점 답변:
"""
            )

            chain = prompt | self.llm | StrOutputParser()
            answer = chain.invoke({"context": context, "question": state["question"]})

            state["answer"] = answer

            duration = time.time() - start_time
            logger.info(f"  📝 Answer length: {len(answer)} characters")
            logger.info(f"  📝 Answer preview: {answer[:200]}...")

            self.logger.log_node_end(
                f"{self.law_type} - Generate", {"answer_length": len(answer)}, duration
            )

        except Exception as e:
            self.logger.log_error(f"{self.law_type} - Generate", e)
            raise

        return state

    def validate_answer(self, state: LegalAgentState) -> LegalAgentState:
        """답변 검증 with logging"""
        import time

        start_time = time.time()

        self.logger.log_node_start(f"{self.law_type} - Validate")

        try:
            validation = self.validator.validate_answer(
                state["question"], state["answer"], state["filtered_documents"]
            )

            state["validation_result"] = validation
            state["needs_refinement"] = validation["needs_refinement"] == "yes"

            duration = time.time() - start_time
            self.logger.log_validation(self.law_type, validation)

            if state["needs_refinement"]:
                logger.warning(f"  ⚠️  Answer needs refinement!")
            else:
                logger.info(f"  ✅ Answer quality is acceptable")

            self.logger.log_node_end(
                f"{self.law_type} - Validate",
                {"needs_refinement": state["needs_refinement"]},
                duration,
            )

        except Exception as e:
            self.logger.log_error(f"{self.law_type} - Validate", e)
            raise

        return state

    def refine_answer(self, state: LegalAgentState) -> LegalAgentState:
        """답변 개선 with logging"""
        if not state["needs_refinement"]:
            logger.info(
                f"  ⏭️  [{self.law_type}] Refinement skipped - answer is acceptable"
            )
            return state

        import time

        start_time = time.time()

        self.logger.log_node_start(f"{self.law_type} - Refine")

        try:
            logger.info(f"  🔧 Refining answer...")
            logger.info(f"  📝 Original answer length: {len(state['answer'])} chars")

            refine_prompt = ChatPromptTemplate.from_template(
                """
이전 답변에 문제가 있습니다. 다음 사항을 개선하여 답변을 재작성하세요:

1. 문서에 근거한 내용만 포함
2. 더 구체적인 법률 조항 인용
3. 사례에 직접 적용 가능한 설명

원본 질문: {question}
이전 답변: {previous_answer}
참고 문서: {context}

개선된 답변:
"""
            )

            context = "\n\n".join(
                [doc.page_content for doc in state["filtered_documents"]]
            )
            chain = refine_prompt | self.llm | StrOutputParser()

            improved_answer = chain.invoke(
                {
                    "question": state["question"],
                    "previous_answer": state["answer"],
                    "context": context,
                }
            )

            logger.info(f"  📝 Refined answer length: {len(improved_answer)} chars")
            logger.info(
                f"  📝 Length change: {len(improved_answer) - len(state['answer']):+d} chars"
            )

            state["answer"] = improved_answer
            state["needs_refinement"] = False

            duration = time.time() - start_time
            self.logger.log_node_end(
                f"{self.law_type} - Refine",
                {"refined_length": len(improved_answer)},
                duration,
            )

        except Exception as e:
            self.logger.log_error(f"{self.law_type} - Refine", e)
            raise

        return state


# ===========================
# 5. Multi-Agent Supervisor
# ===========================

class SupervisorState(TypedDict):
    """Supervisor 상태 - Annotated로 병렬 업데이트 지원"""

    original_question: str
    sub_questions: Annotated[dict, merge_dicts]  # 병렬 업데이트 허용
    agent_results: Annotated[dict, merge_dicts]  # 병렬 업데이트 허용
    final_answer: str


def create_multi_agent_system(vectorstore):
    """Multi-Agent RAG 시스템 생성"""

    llm = AzureChatOpenAI(
        openai_api_version="2024-08-01-preview",
        azure_deployment=AOAI_DEPLOY_GPT4O_MINI,
        temperature=0.0,
        api_key=AOAI_API_KEY,
        azure_endpoint=AOAI_ENDPOINT,
    )

    retriever = vectorstore.as_retriever(search_kwargs={"k": 10})
    validator = SelfRAGValidator(llm)
    query_generator = MultiQueryGenerator(llm)

    # 법률별 Agent 생성 - 매핑 사용
    law_types = ["개인정보보호법", "형법", "민법", "형사소송법", "민사소송법"]

    # 영문 노드 이름 매핑
    node_name_map = {
        "개인정보보호법": "privacy_law",
        "형법": "criminal_law",
        "민법": "civil_law",
        "형사소송법": "criminal_procedure",
        "민사소송법": "civil_procedure",
    }

    # 역방향 매핑
    law_type_map = {v: k for k, v in node_name_map.items()}

    agents = {
        node_name: LegalAgent(law_type, llm, retriever, validator)
        for law_type, node_name in node_name_map.items()
    }

    def supervisor_node(state: SupervisorState) -> SupervisorState:
        """질문을 분석하고 각 법률별 sub-question 생성"""
        print("\n=== Supervisor: 질문 분석 중 ===")

        prompt = ChatPromptTemplate.from_template(
            """
다음 법률 사례를 분석하여 각 법률 관점에서 답변해야 할 세부 질문을 생성하세요.

원본 질문:
{question}

5가지 법률 관점:
1. 개인정보보호법
2. 형법
3. 민법
4. 형사소송법
5. 민사소송법

각 법률 관점에서 구체적으로 답변할 질문을 한 줄씩 작성하세요.
형식: 
개인정보보호법: [질문]
형법: [질문]
...
"""
        )

        chain = prompt | llm | StrOutputParser()
        result = chain.invoke({"question": state["original_question"]})

        # 결과 파싱
        sub_questions = {}
        for line in result.split("\n"):
            line = line.strip()
            if ":" in line:
                law_type = line.split(":")[0].strip()
                question = line.split(":", 1)[1].strip()
                if law_type in law_types:
                    # 영문 노드 이름으로 저장
                    node_name = node_name_map[law_type]
                    sub_questions[node_name] = question

        return {"sub_questions": sub_questions}

    def agent_executor_node(node_name: str, state: SupervisorState) -> dict:
        """특정 법률 Agent 실행 - dictionary만 반환"""
        agent = agents[node_name]
        question = state["sub_questions"].get(node_name, state["original_question"])

        # Multi-Query 생성
        queries = query_generator.generate_queries(question)

        # Agent 상태 초기화
        agent_state = LegalAgentState(
            question=question,
            law_type=agent.law_type,  # 실제 한글 법률명
            queries=queries,
            documents=[],
            filtered_documents=[],
            answer="",
            validation_result={},
            needs_refinement=False,
        )

        # Agent 워크플로우 실행
        agent_state = agent.retrieve_documents(agent_state)
        agent_state = agent.grade_documents(agent_state)
        agent_state = agent.generate_answer(agent_state)
        agent_state = agent.validate_answer(agent_state)
        agent_state = agent.refine_answer(agent_state)

        # agent_results에 영문 노드 이름으로 저장
        return {"agent_results": {node_name: agent_state["answer"]}}

    def aggregator_node(state: SupervisorState) -> dict:
        """각 Agent 결과를 종합"""
        print("\n=== Aggregator: 최종 답변 생성 중 ===")

        # 영문 노드 이름을 한글로 변환하여 답변 결합
        combined_answers = "\n\n".join(
            [
                f"## {law_type_map[node_name]}\n{answer}"
                for node_name, answer in state["agent_results"].items()
            ]
        )

        final_prompt = ChatPromptTemplate.from_template(
            """
다음은 5가지 법률 관점에서 분석한 결과입니다.
이를 종합하여 사용자가 이해하기 쉽게 구조화된 최종 답변을 작성하세요.

원본 질문:
{question}

각 법률별 분석:
{combined_answers}

최종 종합 답변 (각 법률 관점을 모두 포함하여 구조화):
        """
        )

        chain = final_prompt | llm | StrOutputParser()
        final_answer = chain.invoke(
            {
                "question": state["original_question"],
                "combined_answers": combined_answers,
            }
        )

        return {"final_answer": final_answer}

    # LangGraph 구성
    workflow = StateGraph(SupervisorState)

    # 노드 추가 - 영문 이름 사용
    workflow.add_node("supervisor", supervisor_node)
    for node_name in node_name_map.values():
        workflow.add_node(node_name, lambda s, nn=node_name: agent_executor_node(nn, s))
    workflow.add_node("aggregator", aggregator_node)

    # 엣지 구성
    workflow.add_edge(START, "supervisor")
    for node_name in node_name_map.values():
        workflow.add_edge("supervisor", node_name)
        workflow.add_edge(node_name, "aggregator")
    workflow.add_edge("aggregator", END)

    return workflow.compile()


# ===========================
# 6. 실행 코드
# ===========================

def main():
    # 1. PDF 처리 및 벡터 저장소 생성 (또는 기존 저장소 로드)
    print("=== 벡터 저장소 로드 ===")

    embeddings = AzureOpenAIEmbeddings(
        model=AOAI_DEPLOY_EMBED_3_LARGE,
        openai_api_version="2024-08-01-preview",
        api_key=AOAI_API_KEY,
        azure_endpoint=AOAI_ENDPOINT,
    )

    # 기존 저장소가 있으면 로드, 없으면 새로 생성
    try:
        vectorstore = FAISS.load_local(
            folder_path="./faiss_db2",
            embeddings=embeddings,
            allow_dangerous_deserialization=True,
        )
        print("기존 벡터 저장소를 로드했습니다.")
    except:
        print("=== PDF 처리 시작 ===")
        directory = "./pdf/"
        all_chunks = process_multiple_pdfs(directory)

        print("\n=== 벡터 저장소 생성 중 ===")
        vectorstore = FAISS.from_documents(
            documents=all_chunks,
            embedding=embeddings,
        )

        vectorstore.save_local(folder_path="./faiss_db2")

    # 2. Multi-Agent 시스템 생성
    print("\n=== Multi-Agent 시스템 초기화 ===")
    app = create_multi_agent_system(vectorstore)

    # from IPython.display import Image, display
    #
    # display(
    #     Image(
    #         app.get_graph().draw_mermaid_png()
    #     )
    # )

    # 3. 질문 실행
    question = """
[사례]
온라인 쇼핑몰 'A'사의 개발팀에서 근무하던 **갑(甲)**은 퇴사 직전, 
회사의 고객 관리 데이터베이스에 접근하여 고객 1만 명의 이름, 주소, 연락처, 구매 내역 등 개인정보를 
자신의 개인 서버로 무단 유출했습니다.

이후 **갑(甲)**은 유출한 개인정보 중 일부를 이용하여 
특정 고객 **을(乙)**에게 전화를 걸어 'A'사 직원을 사칭하며 "시스템 오류로 결제가 중복 처리되었으니, 
환불을 위해 알려주는 특정 계좌로 수수료 10만 원을 먼저 입금하라"고 속여 돈을 편취했습니다.

이 사실을 뒤늦게 알게 된 'A'사는 내부 감사를 통해 **갑(甲)**의 소행임을 파악했고, 
고객 **을(乙)**을 포함한 다수의 피해자는 'A'사를 상대로 집단적으로 항의하기 시작했습니다.

[문제]
위 사례를 바탕으로, 갑(甲), 'A'사, 그리고 피해 고객 을(乙) 사이에 발생할 수 있는 법적 문제들을 
아래 5가지 법률의 관점에서 각각 분석하고 그 근거 조항과 함께 설명하시오.

1. 개인정보보호법: 'A'사와 갑(甲)은 각각 어떤 의무를 위반했으며, 어떤 책임을 지게 되는가?
2. 형법: 갑(甲)의 행위는 어떤 범죄에 해당하며, 그 이유는 무엇인가?
3. 민법: 을(乙)은 갑(甲)과 'A'사를 상대로 어떤 권리를 주장하며 손해배상을 청구할 수 있는가? 그 법적 근거는 무엇인가?
4. 형사소송법: 갑(甲)의 범죄 혐의에 대해 수사기관이 수사를 개시하고 재판에 넘기는 과정은 어떻게 진행되는가?
5. 민사소송법: 을(乙)이 자신의 금전적, 정신적 피해를 구제받기 위해 법원에 소송을 제기한다면, 그 절차는 어떻게 진행되는가?
"""

    print("\n=== 질문 처리 시작 ===")
    logger.info("=" * 80)
    logger.info("🎬 EXECUTION START")
    logger.info("=" * 80)

    state = {
        "original_question": question,
        "sub_questions": {},
        "agent_results": {},
        "final_answer": "",
    }

    # final_state = None
    # for update in app.stream(state, stream_mode="updates"):
    #     logger.info(f"📦 State Update: {list(update.keys())}")
    #     for node_name, node_output in update.items():
    #         logger.info(f"  [{node_name}] completed")
    #         # 각 노드의 출력 상세 로그
    #         if isinstance(node_output, dict):
    #             for key, value in node_output.items():
    #                 if isinstance(value, str):
    #                     logger.info(f"    {key}: {value[:100]}...")
    #                 else:
    #                     logger.info(f"    {key}: {type(value)}")
    #     final_state = update

    result = app.invoke(state)

    logger.info("=" * 80)
    logger.info("🏁 EXECUTION COMPLETE")
    logger.info("=" * 80)

    print("\n" + "=" * 80)
    print("최종 답변:")
    print("=" * 80)
    print(result["final_answer"])


if __name__ == "__main__":
    main()
