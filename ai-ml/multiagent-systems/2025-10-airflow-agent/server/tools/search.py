"""
Internet Search Tool using DuckDuckGo
"""

from langchain_core.tools import Tool
# from duckduckgo_search import DDGS
from langchain_community.tools import DuckDuckGoSearchResults
from typing import List
import logging

logger = logging.getLogger(__name__)


# def search_internet(query: str, max_results: int = 5) -> str:
#     """
#     Search the internet using DuckDuckGo
#
#     Args:
#         query: Search query string
#         max_results: Maximum number of results to return
#
#     Returns:
#         Formatted search results as string
#     """
#     try:
#         logger.info(f"Searching internet for: {query}")
#
#         ddgs = DDGS()
#         results = ddgs.text(
#             query,
#             region="wt-wt",  # Worldwide
#             safesearch="moderate",
#             max_results=max_results,
#         )
#
#         if not results:
#             return "검색 결과를 찾을 수 없습니다."
#
#         # Format results
#         formatted_results = []
#         for i, result in enumerate(results, 1):
#             title = result.get("title", "제목 없음")
#             body = result.get("body", "내용 없음")
#             url = result.get("href", "")
#
#             formatted_results.append(
#                 f"{i}. {title}\n" f"   {body}\n" f"   출처: {url}\n"
#             )
#
#         output = "\n".join(formatted_results)
#         logger.info(f"Found {len(results)} search results")
#
#         return output
#
#     except Exception as e:
#         error_msg = f"검색 중 오류 발생: {str(e)}"
#         logger.error(error_msg)
#         return error_msg


def create_search_tool() -> Tool:
    """
    Create a LangChain Tool for internet search using DuckDuckGo

    Returns:
        Tool instance configured for internet search
    """
    # return Tool(
    #     name="internet_search",
    #     description=(
    #         "인터넷에서 정보를 검색합니다. "
    #         "에러 메시지, 스택 트레이스, 라이브러리 이름 등을 검색하여 "
    #         "해결 방법이나 관련 정보를 찾을 때 유용합니다. "
    #         "입력: 검색하고자 하는 쿼리 문자열"
    #     ),
    #     func=search_internet,
    # )
    # LangChain의 기본 DuckDuckGo 툴 사용

    search = DuckDuckGoSearchResults(
        num_results=5,
        backend="text",  # 'text', 'news', 'images', 'videos' 중 선택
    )

    # description 커스터마이징
    search.name = "internet_search"
    search.description = (
        "인터넷에서 정보를 검색합니다. "
        "에러 메시지, 스택 트레이스, 라이브러리 이름 등을 검색하여 "
        "해결 방법이나 관련 정보를 찾을 때 유용합니다. "
        "입력: 검색하고자 하는 쿼리 문자열"
    )

    return search
