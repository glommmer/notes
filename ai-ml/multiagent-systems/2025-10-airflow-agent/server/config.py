"""
Configuration Management using Pydantic Settings
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # BaseSettings를 상속하여 애플리케이션 설정 값을 환경 변수로부터 읽어오는 모델 정의
    # 여러 환경 변수를 속성으로 선언, 각 속성은 타입 힌트로 선언 -> 검증 시 활용
    # 기본 값이 없는 필드는 환경 변수로부터 반드시 값을 받아야 함. 기본값이 있는 필드는 optional 하거나 기본 값으로 동작
    # 기본 값이 설정되어 있거나, Optional[...] 가 존재할 경우 optinal

    AZURE_OPENAI_API_KEY: str
    AZURE_OPENAI_ENDPOINT: str
    AZURE_OPENAI_DEPLOYMENT: str
    AZURE_OPENAI_API_VERSION: str
    AZURE_EMBEDDING_DEPLOYMENT: str

    # Airflow Configuration
    AIRFLOW_HOST: str = "http://localhost:8080"
    AIRFLOW_USERNAME: str = "admin"
    AIRFLOW_PASSWORD: str = "admin"

    # OpenAI Configuration
    OPENAI_API_KEY: str
    OPENAI_BASE_URL: str
    OPENAI_MODEL: str = "ax4"
    OPENAI_TEMPERATURE: float = 0.7

    # Langfuse Configuration
    LANGFUSE_PUBLIC_KEY: str
    LANGFUSE_SECRET_KEY: str
    LANGFUSE_HOST: str = "https://cloud.langfuse.com"
    LANGFUSE_BASE_URL: str = "https://us.cloud.langfuse.com"

    # FastAPI Server Configuration
    API_BASE_URL: str = "http://localhost:8000"
    SERVER_HOST: str = "0.0.0.0"
    SERVER_PORT: int = 8000

    # Application Configuration
    PROJECT_NAME: str = "Airflow Monitoring Agent"
    API_V1_STR: str = "/api/v1"
    DEBUG: bool = False

    # Monitoring Configuration
    MONITORING_INTERVAL: int = 60  # seconds
    MAX_LOG_LENGTH: int = 10000  # characters

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=True, extra="ignore"
    )
    # `model_config` 변수 명은 Pydantic 프레임워크가 모델 클래스 생성 시 해당 값을 읽어 내부 설정을 적용할 때 사용하는 예약어
    # env_file: 기본으로 사용할 환경 변수 파일 이름
    # env_file_encoding: 환경 변수 파일의 인코딩 지정
    # case_sensitive: 환경 변수 이름 대소문자 구분 여부
    # extra: 설정 모델에 없는 extra 환경 변수가 있어도 무시(ignore). 기본은 에러 발생(forbid)


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    # @lru_cache(): Least Recently Used (LRU) 캐시 전략
    # 함수 호출 결과를 메모리에 저장해 같은 입력  값에 대해 함수가 여러 번 호출되는 경우,
    # 이전에 저장된 결과를 재사용하여 실행 시간을 크게 단축
    return Settings()


# Global settings instance
settings = get_settings()
