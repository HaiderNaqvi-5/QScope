"""Core application configuration using Pydantic Settings.

Loads configuration from environment variables and .env file.
"""
from typing import Literal
from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from environment."""

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
    GROQ_MODEL: str = Field(
        default="mixtral-8x7b-32768", description="Groq model to use"
    )
    GROQ_MAX_TOKENS: int = Field(default=2048, description="Max tokens for LLM")
    GROQ_TIMEOUT: int = Field(default=30, description="Groq API timeout in seconds")

    # Features
    ENABLE_LLM_FEATURES: bool = Field(default=True, description="Enable LLM features")
    ENABLE_ADVANCED_TESTING: bool = Field(default=True, description="Enable advanced testing")

    # Performance
    SCAN_TIMEOUT: int = Field(default=3600, description="Scan timeout in seconds")
    TOOL_TIMEOUT: int = Field(default=300, description="Tool execution timeout")
    MAX_FILE_SIZE_MB: int = Field(default=100, description="Max file size to analyze")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True

    @property
    def data_dir(self) -> Path:
        """Get the data directory path."""
        return Path(self.QSSCOPE_DATA_DIR).resolve()


# Global settings instance
settings = Settings()
