"""Settings API endpoints."""
from fastapi import APIRouter, HTTPException
from app.core.config import settings as app_settings
from app.schemas.settings import AIStatusResponse, SettingsResponse, SettingsUpdate

router = APIRouter()


@router.get("/settings", response_model=SettingsResponse)
async def get_settings() -> SettingsResponse:
    """Get current application settings."""
    return SettingsResponse(
        debug=app_settings.DEBUG,
        log_level=app_settings.LOG_LEVEL,
        enable_llm_features=app_settings.ENABLE_LLM_FEATURES,
        enable_advanced_testing=app_settings.ENABLE_ADVANCED_TESTING,
        backend_host=app_settings.BACKEND_HOST,
        backend_port=app_settings.BACKEND_PORT,
        data_dir=str(app_settings.data_dir),
    )


@router.patch("/settings", response_model=SettingsResponse)
async def update_settings(update: SettingsUpdate) -> SettingsResponse:
    """Update application settings (in-memory only for M1)."""
    if update.debug is not None:
        app_settings.DEBUG = update.debug
    if update.log_level is not None:
        app_settings.LOG_LEVEL = update.log_level
    if update.enable_llm_features is not None:
        app_settings.ENABLE_LLM_FEATURES = update.enable_llm_features
    if update.enable_advanced_testing is not None:
        app_settings.ENABLE_ADVANCED_TESTING = update.enable_advanced_testing
    
    return await get_settings()


@router.get("/settings/ai", response_model=AIStatusResponse)
async def get_ai_status() -> AIStatusResponse:
    """Report local AI readiness without exposing credentials or making a network call."""
    if not app_settings.ENABLE_LLM_FEATURES:
        status = "DISABLED"
    elif not app_settings.GROQ_API_KEY:
        status = "MISSING_KEY"
    else:
        status = "READY"
    return AIStatusResponse(
        provider="Groq",
        status=status,
        model=app_settings.GROQ_MODEL,
        max_tokens=app_settings.GROQ_MAX_TOKENS,
        timeout_seconds=app_settings.GROQ_TIMEOUT,
        source_upload_default=False,
        note="AI actions are opt-in; only bounded redacted context may be sent to Groq.",
    )
