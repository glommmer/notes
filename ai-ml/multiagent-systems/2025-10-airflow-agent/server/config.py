"""
Configuration Management using Pydantic Settings
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

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


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()


# Global settings instance
settings = get_settings()
