"""Выбор хранилища по настройкам сервиса."""

from __future__ import annotations

from app.config import Settings
from app.storage.base import DocumentRepository
from app.storage.sqlite import SQLiteRepository

POSTGRES_SCHEMES = ("postgres://", "postgresql://")


def create_repository(settings: Settings) -> DocumentRepository:
    """PostgreSQL, если задан KS_DATABASE_URL, иначе файл SQLite."""
    url = settings.database_url.strip()
    if not url:
        return SQLiteRepository(settings.database_path)

    if url.startswith(POSTGRES_SCHEMES):
        # Драйвер импортируется лениво: без PostgreSQL он не нужен
        from app.storage.postgres import PostgresRepository

        return PostgresRepository(url)

    raise ValueError(
        f"Неизвестная схема подключения в KS_DATABASE_URL: {url.split('://', 1)[0]}://"
    )
