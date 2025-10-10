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

    llm = AzureChatOpenAI(
        openai_api_version="2024-08-01-preview",
        azure_deployment=AOAI_DEPLOY_GPT4O_MINI,
        temperature=0.0,
        api_key=AOAI_API_KEY,
        azure_endpoint=AOAI_ENDPOINT,
    )

    print(MultiQueryGenerator(llm).generate_queries(question))


if __name__ == "__main__":
    main()
