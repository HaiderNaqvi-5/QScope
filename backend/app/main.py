"""FastAPI application factory and entry point."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import init_db, close_db
from app.core import logging as app_logging
from app.core.errors import install_error_handlers
from app.services.runtime import shutdown_running_scans
from app.api.routes import artifacts, behavior_coverage, dynamic_tests, findings, generated_tests, health, llm, manual_qa, mutation, remediation, settings as settings_routes, projects, runtimes, scans, tests as tests_routes, tooling
from app.services.runtime_manager import shutdown_runtimes

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
        await shutdown_running_scans()
        await shutdown_runtimes()
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
        # QSScope is local-first and developers may need a non-default port
        # when another project is already using 3000. Keep CORS restricted to
        # loopback origins while allowing that safe local flexibility.
        allow_origins=["http://127.0.0.1:3000", "http://localhost:3000"],
        allow_origin_regex=r"https?://(localhost|127\.0\.0\.1):[0-9]+$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    install_error_handlers(app)

    app.include_router(health.router, prefix="/api", tags=["health"])
    app.include_router(settings_routes.router, prefix="/api", tags=["settings"])
    app.include_router(projects.router, prefix="/api", tags=["projects"])
    app.include_router(scans.router, prefix="/api", tags=["scans"])
    app.include_router(llm.router, prefix="/api", tags=["ai"])
    app.include_router(tooling.router, prefix="/api", tags=["tooling"])
    app.include_router(artifacts.router, prefix="/api", tags=["artifacts"])
    app.include_router(findings.router, prefix="/api", tags=["findings"])
    app.include_router(tests_routes.router, prefix="/api", tags=["tests"])
    app.include_router(runtimes.router, prefix="/api", tags=["runtimes"])
    app.include_router(manual_qa.router, prefix="/api", tags=["manual-qa"])
    app.include_router(remediation.router, prefix="/api", tags=["remediation"])
    app.include_router(generated_tests.router, prefix="/api", tags=["generated-tests"])
    app.include_router(dynamic_tests.router, prefix="/api", tags=["dynamic-tests"])
    app.include_router(behavior_coverage.router, prefix="/api", tags=["behavior-coverage"])
    app.include_router(mutation.router, prefix="/api", tags=["mutation"])

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
