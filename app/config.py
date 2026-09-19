"""Настройки сервиса (читаются из переменных окружения)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Settings:
    """Конфигурация приложения."""

    database_path: str = "data/ks.sqlite3"
    title: str = "Сервис формирования КС-2 и КС-3"
    version: str = "1.0.0"
    api_key: str = ""
    """Если задан, запросы к /api/** требуют заголовок X-API-Key."""


@lru_cache
def get_settings() -> Settings:
    return Settings(
        database_path=os.getenv("KS_DATABASE_PATH", Settings.database_path),
        title=os.getenv("KS_APP_TITLE", Settings.title),
        version=os.getenv("KS_APP_VERSION", Settings.version),
        api_key=os.getenv("KS_API_KEY", Settings.api_key),
    )
