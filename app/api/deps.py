"""Зависимости FastAPI."""

from __future__ import annotations

from fastapi import Request

from app.storage.repository import DocumentRepository


def get_repository(request: Request) -> DocumentRepository:
    """Хранилище документов, созданное при старте приложения."""
    return request.app.state.repository
