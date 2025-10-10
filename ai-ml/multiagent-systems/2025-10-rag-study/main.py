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

    print("\n[Step 2] LLM 초기화")
    print("-" * 80)

    llm = AzureChatOpenAI(
        openai_api_version="2024-08-01-preview",
        azure_deployment=AOAI_DEPLOY_GPT4O_MINI,
        temperature=0.0,
        api_key=AOAI_API_KEY,
        azure_endpoint=AOAI_ENDPOINT,
    )
    print("✅ Azure OpenAI LLM 초기화 완료")

    print("\n[Step 3] Retriever 테스트")
    print("-" * 80)

    retriever = vectorstore.as_retriever(search_kwargs={"k": 5})

    test_query = "개인정보 유출 시 처리자의 책임은?"
    print(f"테스트 쿼리: {test_query}")

    docs = retriever.invoke(test_query)
    print(f"✅ 검색된 문서 수: {len(docs)}")

    if docs:
        print(f"\n첫 번째 문서 샘플:")
        print(f"  - 파일명: {docs[0].metadata.get('file_name', 'Unknown')}")
        print(f"  - 내용 길이: {len(docs[0].page_content)} 문자")
        print(f"  - 내용 미리보기: {docs[0].page_content[:200]}...")

    print("\n[Step 4] Multi-Query Generator 테스트")
    print("-" * 80)

    query_generator = MultiQueryGenerator(llm)

    original_question = "개인정보보호법 위반 시 처벌 조항은?"
    print(f"원본 질문: {original_question}")

    generated_queries = query_generator.generate_queries(original_question)
    print(f"\n✅ 생성된 쿼리 수: {len(generated_queries)}")

    for i, query in enumerate(generated_queries, 1):
        print(f"  {i}. {query}")

    # Multi-Query로 검색 테스트
    print("\n각 쿼리로 문서 검색 중...")
    all_retrieved_docs = []
    for i, query in enumerate(generated_queries, 1):
        docs = retriever.invoke(query)
        all_retrieved_docs.extend(docs)
        print(f"  쿼리 {i}: {len(docs)}개 문서 검색됨")

    # 중복 제거
    unique_docs = []
    seen_contents = set()
    for doc in all_retrieved_docs:
        if doc.page_content not in seen_contents:
            unique_docs.append(doc)
            seen_contents.add(doc.page_content)

    print(f"\n✅ 총 검색: {len(all_retrieved_docs)}개 → 중복 제거 후: {len(unique_docs)}개")

    print("\n[Step 5] Self-RAG Validator 테스트")
    print("-" * 80)

    validator = SelfRAGValidator(llm)

    # 문서 관련성 평가
    print("\n[5-1] 문서 관련성 평가 (Document Grading)")
    test_question = "개인정보보호법에서 정보 유출 시 처리자의 의무는?"
    print(f"질문: {test_question}")
    print(f"평가 대상 문서 수: {len(unique_docs)}")

    filtered_docs = validator.grade_documents(test_question, unique_docs)
    print(f"\n✅ 관련성 평가 완료:")
    print(f"  - 원본 문서: {len(unique_docs)}개")
    print(f"  - 필터링 후: {len(filtered_docs)}개")
    print(f"  - 필터링 비율: {(len(filtered_docs) / len(unique_docs) * 100):.1f}%")

    if filtered_docs:
        print(f"\n필터링된 문서 샘플:")
        for i, doc in enumerate(filtered_docs[:2], 1):
            print(f"  {i}. {doc.metadata.get('file_name', 'Unknown')}")
            print(f"     내용: {doc.page_content[:150]}...")

    # 답변 생성 (간단한 테스트용)
    print("\n[5-2] 답변 생성 및 품질 검증")

    if filtered_docs:
        context = "\n\n".join([doc.page_content for doc in filtered_docs[:3]])

        # 간단한 답변 생성 프롬프트
        answer_prompt = ChatPromptTemplate.from_template("""
    다음 문서를 참고하여 질문에 답변하세요.

    참고 문서:
    {context}

    질문: {question}

    답변:
    """)

        chain = answer_prompt | llm | StrOutputParser()
        test_answer = chain.invoke({
            "context": context,
            "question": test_question
        })

        print(f"생성된 답변 (길이: {len(test_answer)} 문자):")
        print(f"{test_answer[:300]}...")

        # 답변 품질 검증
        print("\n[5-3] 답변 품질 검증")
        validation_result = validator.validate_answer(
            test_question,
            test_answer,
            filtered_docs[:3]
        )

        print("\n✅ 검증 결과:")
        print(f"  - 문서 근거 여부: {validation_result['is_supported']}")
        print(f"  - 유용성: {validation_result['is_useful']}")
        print(f"  - 개선 필요: {validation_result['needs_refinement']}")

        if validation_result['needs_refinement'] == 'yes':
            print("\n⚠️  답변 개선이 필요합니다.")
        else:
            print("\n✅ 답변 품질이 양호합니다.")


if __name__ == "__main__":
    main()

