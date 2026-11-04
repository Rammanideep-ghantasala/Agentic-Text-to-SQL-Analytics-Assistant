from functools import lru_cache
from typing import List, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Agentic Text-to-SQL Assistant"
    environment: str = "local"

    database_url: Optional[str] = Field(default=None, alias="DATABASE_URL")

    openai_api_key: Optional[str] = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")
    ollama_base_url: Optional[str] = Field(default=None, alias="OLLAMA_BASE_URL")
    ollama_model: str = Field(default="llama2", alias="OLLAMA_MODEL")

    demo_mode: bool = Field(default=False, alias="DEMO_MODE")
    frontend_origin: str = Field(default="http://localhost:3000", alias="FRONTEND_ORIGIN")
    cors_allow_origins: str = Field(default="", alias="CORS_ALLOW_ORIGINS")

    llm_access_token: Optional[str] = Field(default=None, alias="LLM_ACCESS_TOKEN")
    rate_limit_per_minute: int = Field(default=5, alias="RATE_LIMIT_PER_MINUTE")
    query_row_limit: int = Field(default=200, alias="QUERY_ROW_LIMIT")

    @property
    def effective_demo_mode(self) -> bool:
        return self.demo_mode or not (self.openai_api_key or self.ollama_base_url)

    @property
    def allowed_origins(self) -> List[str]:
        origins = [self.frontend_origin, "http://localhost:3000", "http://127.0.0.1:3000"]
        if self.cors_allow_origins:
            origins.extend([origin.strip() for origin in self.cors_allow_origins.split(",") if origin.strip()])
        return sorted(set(origins))


@lru_cache
def get_settings() -> Settings:
    return Settings()

