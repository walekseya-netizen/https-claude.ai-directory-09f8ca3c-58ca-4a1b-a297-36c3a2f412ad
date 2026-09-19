"""Защита API ключом доступа.

Ключ задаётся переменной окружения `KS_API_KEY`. Если она пуста, сервис
работает без аутентификации — так удобно на локальной машине, но для
публичного развёртывания ключ следует задать. HTTP-заголовки передают
только латиницу, поэтому ключ должен состоять из ASCII-символов.
"""

from __future__ import annotations

import hmac

from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader

API_KEY_HEADER = "X-API-Key"
PROTECTED_PREFIX = "/api/"

#: Схема для Swagger UI: кнопка Authorize подставляет заголовок в запросы.
api_key_scheme = APIKeyHeader(
    name=API_KEY_HEADER,
    auto_error=False,
    description="Ключ доступа из переменной окружения KS_API_KEY (если она задана)",
)


async def api_key_middleware(request: Request, call_next):
    """Пропускает к /api/** только запросы с верным ключом."""
    settings = request.app.state.settings
    if settings.api_key and request.url.path.startswith(PROTECTED_PREFIX):
        provided = request.headers.get(API_KEY_HEADER, "")
        # Сравниваем байты: ключ может содержать символы вне ASCII
        if not hmac.compare_digest(provided.encode("utf-8"), settings.api_key.encode("utf-8")):
            return JSONResponse(
                status_code=401,
                content={"detail": f"Требуется заголовок {API_KEY_HEADER} с ключом доступа"},
            )
    return await call_next(request)
