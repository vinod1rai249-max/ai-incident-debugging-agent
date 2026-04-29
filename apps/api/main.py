import os
import uuid

import structlog
from dotenv import load_dotenv

load_dotenv()
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from prometheus_client import make_asgi_app

from apps.incident_debugger.api import router as incident_router
from core.config import settings
from core.exceptions import AppError
from core.logging import configure_logging

configure_logging()
logger = structlog.get_logger(__name__)

app = FastAPI(title="AI GenAI Agentic Platform", version="0.1.0")

# ---------------------------------------------------------------------------
# OpenTelemetry — enabled only when OTEL_EXPORTER_OTLP_ENDPOINT is set
# ---------------------------------------------------------------------------
_otel_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "")
if _otel_endpoint:
    try:
        import logging

        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import (
            BatchSpanProcessor,
            ConsoleSpanExporter,
            SimpleSpanProcessor,
        )

        _service_name = os.environ.get("OTEL_SERVICE_NAME", "incident-debugger")
        _raw_headers = os.environ.get("OTEL_EXPORTER_OTLP_HEADERS", "")

        _resource = Resource.create(
            {
                "service.name": _service_name,
                "service.version": "1.0.0",
                "deployment.environment": settings.app_env,
            }
        )

        _otlp_exporter = OTLPSpanExporter(
            endpoint=f"{_otel_endpoint}/v1/traces"
            if _otel_endpoint.endswith("/otlp")
            else _otel_endpoint,
            headers=dict(item.split("=", 1) for item in _raw_headers.split(",") if "=" in item),
        )

        _provider = TracerProvider(resource=_resource)
        _provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
        _provider.add_span_processor(BatchSpanProcessor(_otlp_exporter))
        trace.set_tracer_provider(_provider)

        FastAPIInstrumentor.instrument_app(app)
        HTTPXClientInstrumentor().instrument()

        if os.environ.get("OTEL_LOG_LEVEL", "").lower() == "debug":
            logging.getLogger("opentelemetry").setLevel(logging.DEBUG)
            logging.getLogger("opentelemetry.exporter.otlp").setLevel(logging.DEBUG)
            logging.basicConfig(level=logging.DEBUG)

        print(f"OTEL configured for service={_service_name}, endpoint={_otel_endpoint}")
        logger.info("otel.configured", endpoint=_otel_endpoint, service=_service_name)
    except Exception as _otel_err:  # pragma: no cover
        logger.warning("otel.setup_failed", error=str(_otel_err))

metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)


@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
    correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(correlation_id=correlation_id)
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = correlation_id
    return response


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    logger.warning("app_error", code=exc.code, message=exc.message)
    status = 400 if exc.code == "VALIDATION_ERROR" else 500
    return JSONResponse(status_code=status, content={"error": exc.message, "code": exc.code})


app.include_router(incident_router, prefix="/api/v1")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "env": settings.app_env}
