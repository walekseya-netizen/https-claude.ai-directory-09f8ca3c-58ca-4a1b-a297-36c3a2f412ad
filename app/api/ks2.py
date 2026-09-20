"""HTTP-эндпоинты акта о приёмке выполненных работ (КС-2)."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import get_repository
from app.api.http import XLSX_RESPONSES, xlsx_response
from app.domain.calc import build_act
from app.domain.models import KS2Act, KS2Input
from app.export.xlsx_ks2 import render_ks2
from app.storage.base import DocumentRepository

router = APIRouter(prefix="/api/v1/ks2", tags=["КС-2"])


@router.post(
    "",
    response_model=KS2Act,
    status_code=status.HTTP_201_CREATED,
    summary="Сформировать и сохранить акт КС-2",
)
def create_act(
    payload: KS2Input,
    repository: DocumentRepository = Depends(get_repository),
) -> KS2Act:
    return repository.save_act(build_act(payload))


@router.post(
    "/preview",
    response_model=KS2Act,
    summary="Рассчитать акт КС-2 без сохранения",
)
def preview_act(payload: KS2Input) -> KS2Act:
    return build_act(payload)


@router.post(
    "/preview/xlsx",
    summary="Получить XLSX акта КС-2 без сохранения",
    responses=XLSX_RESPONSES,
)
def preview_act_xlsx(payload: KS2Input):
    act = build_act(payload)
    return xlsx_response(render_ks2(act), _filename(act))


@router.get("", response_model=list[KS2Act], summary="Список актов КС-2")
def list_acts(
    contract_number: str | None = Query(default=None, description="Номер договора подряда"),
    period_from: date | None = Query(default=None, description="Отчётный период не ранее"),
    period_to: date | None = Query(default=None, description="Отчётный период не позднее"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    repository: DocumentRepository = Depends(get_repository),
) -> list[KS2Act]:
    return repository.list_acts(
        contract_number=contract_number,
        period_from=period_from,
        period_to=period_to,
        limit=limit,
        offset=offset,
    )


@router.get("/{act_id}", response_model=KS2Act, summary="Акт КС-2 по идентификатору")
def get_act(act_id: str, repository: DocumentRepository = Depends(get_repository)) -> KS2Act:
    return repository.get_act(act_id)


@router.get("/{act_id}/xlsx", summary="Выгрузка акта КС-2 в XLSX", responses=XLSX_RESPONSES)
def download_act(act_id: str, repository: DocumentRepository = Depends(get_repository)):
    act = repository.get_act(act_id)
    return xlsx_response(render_ks2(act), _filename(act))


@router.delete("/{act_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Удалить акт КС-2")
def delete_act(act_id: str, repository: DocumentRepository = Depends(get_repository)) -> None:
    repository.delete_act(act_id)


def _filename(act: KS2Act) -> str:
    number = act.document_number.replace("/", "-")
    return f"КС-2 № {number} от {act.document_date:%d.%m.%Y}.xlsx"
