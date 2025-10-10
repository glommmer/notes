import os
import re
import tqdm
import logging
from pathlib import Path
from datetime import datetime
from langchain.document_loaders import PDFPlumberLoader
from langchain.text_splitter import MarkdownHeaderTextSplitter
from langchain_openai import AzureOpenAIEmbeddings
from langchain_community.vectorstores import FAISS


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


if __name__ == "__main__":
    main()

