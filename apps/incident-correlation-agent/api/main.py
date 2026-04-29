from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes.analysis import router as analysis_router
from api.routes.health import router as health_router
from api.routes.incidents import router as incidents_router
from api.routes.metrics_route import router as metrics_router
from core.config import get_settings
from core.logging_config import get_logger, setup_logging

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging(debug=settings.debug)
    logger.info("app_startup", app=settings.app_name, debug=settings.debug)
    yield
    logger.info("app_shutdown")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Incident Correlation Agent",
        description="AI-powered ServiceNow + Dynatrace correlation and root cause analysis",
        version="1.0.0",
        lifespan=lifespan,
        debug=settings.debug,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router)
    app.include_router(incidents_router)
    app.include_router(analysis_router)
    app.include_router(metrics_router)

    return app


app = create_app()
