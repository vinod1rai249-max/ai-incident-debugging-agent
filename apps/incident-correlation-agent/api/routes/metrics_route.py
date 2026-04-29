from fastapi import APIRouter
from fastapi.responses import Response

from core.metrics import get_metrics_output

router = APIRouter(tags=["metrics"])


@router.get("/metrics")
async def prometheus_metrics():
    output, content_type = get_metrics_output()
    return Response(content=output, media_type=content_type)
