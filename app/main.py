"""Точка входа сервиса формирования КС-2 и КС-3."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api import health, ks2, ks3
from app.config import Settings, get_settings
from app.domain.errors import DomainError, NotFoundError
from app.storage.repository import DocumentRepository

DESCRIPTION = """
Формирование первичных документов строительного подряда:

* **КС-2** — акт о приёмке выполненных работ (ОКУД 0322005);
* **КС-3** — справка о стоимости выполненных работ и затрат (ОКУД 0322001),
  в том числе автоматически по ранее сохранённым актам КС-2 с нарастающими итогами.

Расчёты ведутся в Decimal с округлением до копеек, выгрузка — в XLSX
по унифицированным формам, утверждённым постановлением Госкомстата России
от 11.11.1999 № 100.
"""


def create_app(settings: Settings | None = None) -> FastAPI:
    """Собирает приложение FastAPI."""
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        application.state.repository = DocumentRepository(settings.database_path)
        try:
            yield
        finally:
            application.state.repository.close()

    application = FastAPI(
        title=settings.title,
        version=settings.version,
        description=DESCRIPTION,
        lifespan=lifespan,
    )

    application.include_router(health.router)
    application.include_router(ks2.router)
    application.include_router(ks3.router)

    @application.exception_handler(NotFoundError)
    async def _not_found(_: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @application.exception_handler(DomainError)
    async def _domain_error(_: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    return application


app = create_app()
