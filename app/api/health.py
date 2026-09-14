"""Служебные эндпоинты."""

from __future__ import annotations

from fastapi import APIRouter

from app.config import get_settings

router = APIRouter(tags=["Служебные"])


@router.get("/health", summary="Проверка доступности сервиса")
def health() -> dict[str, str]:
    settings = get_settings()
    return {"status": "ok", "version": settings.version}
