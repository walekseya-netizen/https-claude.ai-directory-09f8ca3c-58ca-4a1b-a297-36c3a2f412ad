"""Модели предметной области: унифицированные формы КС-2 и КС-3.

КС-2 — акт о приёмке выполненных работ (ОКУД 0322005).
КС-3 — справка о стоимости выполненных работ и затрат (ОКУД 0322001).
Обе формы утверждены постановлением Госкомстата России от 11.11.1999 № 100.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

NonEmptyStr = Annotated[str, Field(min_length=1, max_length=1000)]
Amount = Annotated[Decimal, Field(ge=0, max_digits=18, decimal_places=6)]
Rate = Annotated[Decimal, Field(ge=0, le=100, max_digits=6, decimal_places=4)]

DEFAULT_VAT_RATE = Decimal("20")


def new_id() -> str:
    return uuid4().hex


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Organization(BaseModel):
    """Участник договора: инвестор, заказчик или подрядчик."""

    model_config = ConfigDict(extra="forbid")

    name: NonEmptyStr
    address: str | None = None
    phone: str | None = None
    okpo: str | None = Field(default=None, max_length=14, description="Код по ОКПО")
    inn: str | None = Field(default=None, max_length=12)
    kpp: str | None = Field(default=None, max_length=9)

    def title_line(self) -> str:
        """Строка формы: наименование, адрес, телефон — через запятую."""
        parts = [self.name, self.address, self.phone]
        return ", ".join(part for part in parts if part)


class Contract(BaseModel):
    """Договор подряда (контракт)."""

    model_config = ConfigDict(extra="forbid")

    number: NonEmptyStr
    date: date


class ReportingPeriod(BaseModel):
    """Отчётный период, за который принимаются работы."""

    model_config = ConfigDict(extra="forbid")

    start: date
    end: date

    @model_validator(mode="after")
    def _check_order(self) -> "ReportingPeriod":
        if self.start > self.end:
            raise ValueError("Начало отчётного периода позже его окончания")
        return self


class DocumentHeader(BaseModel):
    """Общая шапка форм КС-2 и КС-3."""

    model_config = ConfigDict(extra="forbid")

    investor: Organization | None = None
    customer: Organization = Field(description="Заказчик (генподрядчик)")
    contractor: Organization = Field(description="Подрядчик (субподрядчик)")
    construction_site: NonEmptyStr = Field(description="Стройка: наименование и адрес")
    facility: str | None = Field(default=None, description="Объект")
    okdp: str | None = Field(default=None, description="Вид деятельности по ОКДП")
    contract: Contract
    operation_type: str | None = Field(default=None, description="Вид операции")


class VatMode(str, Enum):
    """Порядок начисления НДС в документе."""

    CHARGED = "charged"  # НДС начисляется сверху по ставке
    NONE = "none"  # без НДС (УСН, освобождение по ст. 145 НК РФ)


class ColumnTotals(BaseModel):
    """Итог по одной графе документа."""

    model_config = ConfigDict(extra="forbid")

    net: Decimal = Field(description="Итого без НДС, руб.")
    vat: Decimal = Field(description="Сумма НДС, руб.")
    gross: Decimal = Field(description="Всего с учётом НДС, руб.")


class Totals(ColumnTotals):
    """Итоги документа с указанием порядка начисления НДС."""

    vat_mode: VatMode
    vat_rate: Decimal


# --------------------------------------------------------------------------
# КС-2
# --------------------------------------------------------------------------


class WorkItemInput(BaseModel):
    """Строка акта КС-2 в том виде, в каком её передаёт клиент."""

    model_config = ConfigDict(extra="forbid")

    estimate_position: str | None = Field(default=None, description="Номер позиции по смете")
    name: NonEmptyStr = Field(description="Наименование работ")
    unit_rate_number: str | None = Field(default=None, description="Номер единичной расценки")
    unit: NonEmptyStr = Field(description="Единица измерения")
    quantity: Amount
    unit_price: Amount = Field(description="Цена за единицу, руб.")
    coefficient: Annotated[Decimal, Field(gt=0, le=1000, max_digits=10, decimal_places=6)] = Decimal("1")


class WorkItem(WorkItemInput):
    """Строка акта с рассчитанной стоимостью."""

    number: int = Field(ge=1, description="Номер по порядку")
    amount: Decimal = Field(description="Стоимость, руб., без НДС")


class KS2Input(BaseModel):
    """Запрос на формирование акта КС-2."""

    model_config = ConfigDict(extra="forbid")

    header: DocumentHeader
    document_number: NonEmptyStr
    document_date: date
    period: ReportingPeriod
    contract_cost: Decimal | None = Field(
        default=None, ge=0, description="Сметная (договорная) стоимость по договору, руб."
    )
    vat_mode: VatMode = VatMode.CHARGED
    vat_rate: Rate = DEFAULT_VAT_RATE
    items: list[WorkItemInput] = Field(min_length=1)
    signed_by_contractor: str | None = Field(default=None, description="Сдал: должность, Ф.И.О.")
    signed_by_customer: str | None = Field(default=None, description="Принял: должность, Ф.И.О.")

    @model_validator(mode="after")
    def _check_document_date(self) -> "KS2Input":
        if self.document_date < self.period.start:
            raise ValueError("Дата составления акта раньше начала отчётного периода")
        return self


class KS2Act(BaseModel):
    """Сформированный и сохранённый акт КС-2."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=new_id)
    form: Literal["KS-2"] = "KS-2"
    okud: Literal["0322005"] = "0322005"
    created_at: datetime = Field(default_factory=utc_now)
    header: DocumentHeader
    document_number: str
    document_date: date
    period: ReportingPeriod
    contract_cost: Decimal | None = None
    items: list[WorkItem]
    totals: Totals
    signed_by_contractor: str | None = None
    signed_by_customer: str | None = None


# --------------------------------------------------------------------------
# КС-3
# --------------------------------------------------------------------------


class KS3RowInput(BaseModel):
    """Строка справки КС-3, заданная вручную."""

    model_config = ConfigDict(extra="forbid")

    name: NonEmptyStr = Field(
        description="Наименование пусковых комплексов, этапов, объектов, видов работ, затрат"
    )
    code: str | None = None
    cost_from_start: Amount = Field(description="С начала проведения работ, руб.")
    cost_from_year_start: Amount = Field(description="С начала года, руб.")
    cost_for_period: Amount = Field(description="В том числе за отчётный период, руб.")

    @model_validator(mode="after")
    def _check_cumulative_order(self) -> "KS3RowInput":
        if self.cost_for_period > self.cost_from_year_start:
            raise ValueError("Стоимость за отчётный период больше стоимости с начала года")
        if self.cost_from_year_start > self.cost_from_start:
            raise ValueError("Стоимость с начала года больше стоимости с начала проведения работ")
        return self


class KS3Row(KS3RowInput):
    """Строка справки с порядковым номером."""

    number: int = Field(ge=1)


class KS3Input(BaseModel):
    """Запрос на формирование справки КС-3 с явно заданными строками."""

    model_config = ConfigDict(extra="forbid")

    header: DocumentHeader
    document_number: NonEmptyStr
    document_date: date
    period: ReportingPeriod
    vat_mode: VatMode = VatMode.CHARGED
    vat_rate: Rate = DEFAULT_VAT_RATE
    rows: list[KS3RowInput] = Field(min_length=1)
    act_ids: list[str] = Field(default_factory=list, description="Акты КС-2, включённые в справку")
    signed_by_contractor: str | None = None
    signed_by_customer: str | None = None


class OpeningBalance(BaseModel):
    """Накопленные суммы предыдущих периодов по строке справки."""

    model_config = ConfigDict(extra="forbid")

    name: NonEmptyStr
    cost_from_start: Amount = Decimal("0")
    cost_from_year_start: Amount = Decimal("0")


class KS3FromActs(BaseModel):
    """Запрос на формирование справки КС-3 по актам КС-2."""

    model_config = ConfigDict(extra="forbid")

    act_ids: list[str] = Field(min_length=1)
    document_number: NonEmptyStr
    document_date: date
    group_by: Literal["facility", "act", "total"] = "facility"
    previous_certificate_id: str | None = Field(
        default=None, description="Предыдущая справка КС-3 — источник нарастающих итогов"
    )
    opening_balances: list[OpeningBalance] = Field(default_factory=list)
    period: ReportingPeriod | None = Field(
        default=None, description="По умолчанию — объединение периодов актов"
    )
    signed_by_contractor: str | None = None
    signed_by_customer: str | None = None


class KS3Certificate(BaseModel):
    """Сформированная и сохранённая справка КС-3."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=new_id)
    form: Literal["KS-3"] = "KS-3"
    okud: Literal["0322001"] = "0322001"
    created_at: datetime = Field(default_factory=utc_now)
    header: DocumentHeader
    document_number: str
    document_date: date
    period: ReportingPeriod
    rows: list[KS3Row]
    totals: Totals = Field(description="Итоги за отчётный период")
    totals_from_start: ColumnTotals = Field(description="Итоги с начала проведения работ")
    totals_from_year_start: ColumnTotals = Field(description="Итоги с начала года")
    act_ids: list[str] = Field(default_factory=list)
    signed_by_contractor: str | None = None
    signed_by_customer: str | None = None
