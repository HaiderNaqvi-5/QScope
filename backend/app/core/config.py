"""Core application configuration using Pydantic Settings.

Loads configuration from environment variables and .env file.
"""
from typing import Literal
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Application settings loaded from environment."""
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env", env_file_encoding="utf-8", case_sensitive=True, extra="ignore"
    )

    # Server
    DEBUG: bool = Field(default=False, description="Debug mode")
    BACKEND_HOST: str = Field(default="127.0.0.1", description="Backend host")
    BACKEND_PORT: int = Field(default=8000, description="Backend port")
    BACKEND_RELOAD: bool = Field(default=True, description="Auto-reload on file changes")

    # Database
    DATABASE_URL: str = Field(
        default="sqlite:///./qsscope.db",
        description="SQLAlchemy database URL",
    )
    DATABASE_ECHO: bool = Field(default=False, description="SQL query logging")

    # Data directory
    QSSCOPE_DATA_DIR: str = Field(default=".qsscope", description="Local data directory")

    # Logging
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO", description="Logging level"
    )
    LOG_FORMAT: Literal["json", "text"] = Field(default="json", description="Log format")

    # LLM / Groq
    GROQ_API_KEY: str = Field(default="", description="Groq API key")
    GROQ_BASE_URL: str = Field(default="https://api.groq.com/openai/v1", description="Groq OpenAI-compatible API")
    GROQ_MODEL: str = Field(default="openai/gpt-oss-20b", description="Groq model to use")
    GROQ_MAX_TOKENS: int = Field(default=2048, description="Max tokens for LLM")
    GROQ_TIMEOUT_SECONDS: int = Field(default=60, description="Groq API timeout in seconds")
    GROQ_MAX_RETRIES: int = Field(default=3, ge=0, le=5)
    GROQ_MAX_CONCURRENT_REQUESTS: int = Field(default=2, ge=1, le=8)

    # Features
    QSSCOPE_LLM_ENABLED: bool = Field(default=True, description="Enable LLM features")
    ENABLE_ADVANCED_TESTING: bool = Field(default=True, description="Enable advanced testing")

    # Performance
    SCAN_TIMEOUT: int = Field(default=3600, description="Scan timeout in seconds")
    TOOL_TIMEOUT: int = Field(default=300, description="Tool execution timeout")
    MAX_FILE_SIZE_MB: int = Field(default=100, description="Max file size to analyze")

    @property
    def data_dir(self) -> Path:
        """Get the data directory path."""
        return Path(self.QSSCOPE_DATA_DIR).resolve()

    @property
    def ENABLE_LLM_FEATURES(self) -> bool:
        """Compatibility alias for the original settings/API name."""
        return self.QSSCOPE_LLM_ENABLED

    @ENABLE_LLM_FEATURES.setter
    def ENABLE_LLM_FEATURES(self, value: bool) -> None:
        self.QSSCOPE_LLM_ENABLED = value

    @property
    def GROQ_TIMEOUT(self) -> int:
        return self.GROQ_TIMEOUT_SECONDS


# Global settings instance
settings = Settings()
