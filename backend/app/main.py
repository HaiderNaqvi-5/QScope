"""FastAPI application factory and entry point."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import init_db, close_db
from app.core import logging as app_logging
from app.api.routes import health, settings as settings_routes, projects

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown."""
    logger.info("🚀 QSScope backend starting...")
    try:
        await init_db()
        logger.info("✓ Database initialized")
    except Exception as e:
        logger.error(f"✗ Database initialization failed: {e}", exc_info=True)
        raise
    
    yield
    
    logger.info("🛑 QSScope backend shutting down...")
    try:
        await close_db()
        logger.info("✓ Database closed")
    except Exception as e:
        logger.error(f"✗ Database close failed: {e}", exc_info=True)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="QSScope",
        description="Local full-stack quality, security & testing intelligence platform",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:3000", "http://localhost:3000", "http://localhost:3001"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router, prefix="/api", tags=["health"])
    app.include_router(settings_routes.router, prefix="/api", tags=["settings"])
    app.include_router(projects.router, prefix="/api", tags=["projects"])

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.BACKEND_HOST,
        port=settings.BACKEND_PORT,
        reload=settings.BACKEND_RELOAD,
        log_level=settings.LOG_LEVEL.lower(),
    )
