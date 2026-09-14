"""HTTP-эндпоинты справки о стоимости выполненных работ и затрат (КС-3)."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import get_repository
from app.api.http import XLSX_RESPONSES, xlsx_response
from app.domain.calc import build_certificate, build_certificate_from_acts
from app.domain.models import KS3Certificate, KS3FromActs, KS3Input
from app.export.xlsx_ks3 import render_ks3
from app.storage.repository import DocumentRepository

router = APIRouter(prefix="/api/v1/ks3", tags=["КС-3"])


@router.post(
    "",
    response_model=KS3Certificate,
    status_code=status.HTTP_201_CREATED,
    summary="Сформировать и сохранить справку КС-3 по заданным строкам",
)
def create_certificate(
    payload: KS3Input,
    repository: DocumentRepository = Depends(get_repository),
) -> KS3Certificate:
    return repository.save_certificate(build_certificate(payload))


@router.post(
    "/from-acts",
    response_model=KS3Certificate,
    status_code=status.HTTP_201_CREATED,
    summary="Сформировать и сохранить справку КС-3 по актам КС-2",
)
def create_certificate_from_acts(
    payload: KS3FromActs,
    repository: DocumentRepository = Depends(get_repository),
) -> KS3Certificate:
    return repository.save_certificate(_build_from_acts(payload, repository))


@router.post(
    "/from-acts/preview",
    response_model=KS3Certificate,
    summary="Рассчитать справку КС-3 по актам КС-2 без сохранения",
)
def preview_certificate_from_acts(
    payload: KS3FromActs,
    repository: DocumentRepository = Depends(get_repository),
) -> KS3Certificate:
    return _build_from_acts(payload, repository)


@router.get("", response_model=list[KS3Certificate], summary="Список справок КС-3")
def list_certificates(
    contract_number: str | None = Query(default=None, description="Номер договора подряда"),
    period_from: date | None = Query(default=None, description="Отчётный период не ранее"),
    period_to: date | None = Query(default=None, description="Отчётный период не позднее"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    repository: DocumentRepository = Depends(get_repository),
) -> list[KS3Certificate]:
    return repository.list_certificates(
        contract_number=contract_number,
        period_from=period_from,
        period_to=period_to,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{certificate_id}",
    response_model=KS3Certificate,
    summary="Справка КС-3 по идентификатору",
)
def get_certificate(
    certificate_id: str,
    repository: DocumentRepository = Depends(get_repository),
) -> KS3Certificate:
    return repository.get_certificate(certificate_id)


@router.get("/{certificate_id}/xlsx", summary="Выгрузка справки КС-3 в XLSX", responses=XLSX_RESPONSES)
def download_certificate(
    certificate_id: str,
    repository: DocumentRepository = Depends(get_repository),
):
    certificate = repository.get_certificate(certificate_id)
    return xlsx_response(render_ks3(certificate), _filename(certificate))


@router.delete(
    "/{certificate_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить справку КС-3",
)
def delete_certificate(
    certificate_id: str,
    repository: DocumentRepository = Depends(get_repository),
) -> None:
    repository.delete_certificate(certificate_id)


def _build_from_acts(payload: KS3FromActs, repository: DocumentRepository) -> KS3Certificate:
    acts = repository.get_acts(payload.act_ids)
    previous = (
        repository.get_certificate(payload.previous_certificate_id)
        if payload.previous_certificate_id
        else None
    )
    return build_certificate_from_acts(payload, acts, previous)


def _filename(certificate: KS3Certificate) -> str:
    number = certificate.document_number.replace("/", "-")
    return f"КС-3 № {number} от {certificate.document_date:%d.%m.%Y}.xlsx"
