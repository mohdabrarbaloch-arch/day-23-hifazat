"""Health endpoint."""

from fastapi import APIRouter

from ..config import get_settings

router = APIRouter(tags=["health"])

settings = get_settings()


@router.get("/api/health")
def health() -> dict:
    return {"status": "ok", "name": settings.app_name, "version": settings.version}
