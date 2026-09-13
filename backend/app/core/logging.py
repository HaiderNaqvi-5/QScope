"""Structured logging configuration with secret redaction.

Provides JSON and text logging formats with automatic redaction of sensitive data.
"""
import logging
import json
import re
from typing import Any

from app.core.config import settings


# Patterns for sensitive data that should be redacted
SENSITIVE_PATTERNS = [
    r"password['\"]?\s*[:=]\s*['\"]?([^'\"]+)['\"]?",
    r"api[_-]?key['\"]?\s*[:=]\s*['\"]?([^'\"]+)['\"]?",
    r"token['\"]?\s*[:=]\s*['\"]?([^'\"]+)['\"]?",
    r"secret['\"]?\s*[:=]\s*['\"]?([^'\"]+)['\"]?",
    r"authorization['\"]?\s*[:=]\s*['\"]?([^'\"]+)['\"]?",
]


def redact_secrets(text: str) -> str:
    """Redact sensitive information from text."""
    if not text:
        return text
    
    for pattern in SENSITIVE_PATTERNS:
        text = re.sub(pattern, lambda m: f"{m.group(0)[:20]}***", text, flags=re.IGNORECASE)
    
    return text


class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_secrets(record.getMessage()),
        }

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        extra = getattr(record, "extra", None)
        if isinstance(extra, dict):
            log_data.update(extra)

        return json.dumps(log_data)


class TextFormatter(logging.Formatter):
    """Custom text formatter with color support."""

    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",   # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
        "RESET": "\033[0m",
    }

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as colored text."""
        color = self.COLORS.get(record.levelname, "")
        reset = self.COLORS["RESET"]
        
        # Redact sensitive information
        message = redact_secrets(record.getMessage())
        
        # Format with timestamp, level, logger, and message
        formatted = (
            f"{color}[{self.formatTime(record, self.datefmt)}] "
            f"{record.levelname:8s}{reset} "
            f"{record.name}: {message}"
        )

        if record.exc_info:
            formatted += "\n" + self.formatException(record.exc_info)

        return formatted


def setup_logging() -> None:
    """Configure application logging."""
    root_logger = logging.getLogger()
    root_logger.setLevel(settings.LOG_LEVEL)

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(settings.LOG_LEVEL)

    # Set formatter based on configuration
    if settings.LOG_FORMAT == "json":
        formatter = JSONFormatter()
    else:
        formatter = TextFormatter()

    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # Set third-party loggers to WARNING to reduce noise
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
    logging.getLogger("alembic").setLevel(logging.WARNING)


# Configure logging on module import
setup_logging()
