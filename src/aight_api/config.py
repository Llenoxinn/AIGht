from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AIGHT_", env_file=".env", extra="ignore")

    redis_url: str = "redis://localhost:6379/0"
    data_dir: Path = Path(".local/data")
    allowed_origins: str = "http://localhost:5080,http://127.0.0.1:5080"
    openai_api_key: str = ""
    chat_model: str = ""
    embedding_model: str = "text-embedding-3-small"
    notice_version: str = ""
    notice_url: str = ""
    processor_retention: str = ""
    processor_region: str = ""
    clamav_host: str = "localhost"
    clamav_port: int = 3310
    pdf_processing_enabled: bool = False
    session_seconds: int = Field(3600, ge=60, le=3600)
    max_pdf_bytes: int = 10_485_760
    max_pdf_pages: int = 50
    max_extracted_code_points: int = 300_000
    max_pasted_code_points: int = 100_000
    max_documents_per_session: int = 5
    max_outstanding_operations: int = 2
    session_provider_tokens: int = 500_000
    daily_provider_tokens: int = 5_000_000
    operation_provider_tokens: int = 120_000
    question_provider_tokens: int = 24_000
    parser_timeout: int = 35
    operation_timeout: int = 240
    queue_timeout: int = 120
    log_network_salt: str = ""

    @property
    def processing_available(self) -> bool:
        return bool(self.openai_api_key and self.chat_model and self.notice_version
                    and self.notice_url.startswith("https://")
                    and self.processor_retention and self.processor_region)

    @property
    def origins(self) -> list[str]:
        return [value.strip() for value in self.allowed_origins.split(",") if value.strip()]


settings = Settings()
