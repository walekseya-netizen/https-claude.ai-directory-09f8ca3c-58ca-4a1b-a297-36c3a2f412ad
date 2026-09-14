"""Расчёт форм КС-2 и КС-3."""

from __future__ import annotations

from collections import OrderedDict
from decimal import Decimal
from typing import Iterable

from app.domain.errors import DomainError
from app.domain.models import (
    ColumnTotals,
    DocumentHeader,
    KS2Act,
    KS2Input,
    KS3Certificate,
    KS3FromActs,
    KS3Input,
    KS3Row,
    ReportingPeriod,
    Totals,
    VatMode,
    WorkItem,
)
from app.domain.money import money, vat_amount

ZERO = Decimal("0")

#: Первая строка табличной части КС-3 по унифицированной форме.
TOTAL_ROW_TITLE = "Всего работ и затрат, включаемых в стоимость работ"


def column_totals(net: Decimal, vat_mode: VatMode, vat_rate: Decimal) -> ColumnTotals:
    """Итог по графе: без НДС, НДС и всего."""
    net = money(net)
    vat = ZERO if vat_mode is VatMode.NONE else vat_amount(net, vat_rate)
    return ColumnTotals(net=net, vat=vat, gross=money(net + vat))


def build_totals(net: Decimal, vat_mode: VatMode, vat_rate: Decimal) -> Totals:
    """Итоги документа с сохранением режима НДС."""
    effective_rate = ZERO if vat_mode is VatMode.NONE else vat_rate
    base = column_totals(net, vat_mode, effective_rate)
    return Totals(
        net=base.net,
        vat=base.vat,
        gross=base.gross,
        vat_mode=vat_mode,
        vat_rate=effective_rate,
    )


# --------------------------------------------------------------------------
# КС-2
# --------------------------------------------------------------------------


def build_act(payload: KS2Input) -> KS2Act:
    """Формирует акт КС-2: считает стоимость строк и итоги документа."""
    items: list[WorkItem] = []
    for number, source in enumerate(payload.items, start=1):
        amount = money(source.quantity * source.coefficient * source.unit_price)
        items.append(
            WorkItem(
                number=number,
                amount=amount,
                **source.model_dump(),
            )
        )

    net = sum((item.amount for item in items), ZERO)
    return KS2Act(
        header=payload.header,
        document_number=payload.document_number,
        document_date=payload.document_date,
        period=payload.period,
        contract_cost=payload.contract_cost,
        items=items,
        totals=build_totals(net, payload.vat_mode, payload.vat_rate),
        signed_by_contractor=payload.signed_by_contractor,
        signed_by_customer=payload.signed_by_customer,
    )


# --------------------------------------------------------------------------
# КС-3
# --------------------------------------------------------------------------


def build_certificate(payload: KS3Input) -> KS3Certificate:
    """Формирует справку КС-3 из явно заданных строк."""
    rows = [
        KS3Row(number=number, **source.model_dump())
        for number, source in enumerate(payload.rows, start=1)
    ]
    return _assemble_certificate(
        header=payload.header,
        document_number=payload.document_number,
        document_date=payload.document_date,
        period=payload.period,
        rows=rows,
        vat_mode=payload.vat_mode,
        vat_rate=payload.vat_rate,
        act_ids=payload.act_ids,
        signed_by_contractor=payload.signed_by_contractor,
        signed_by_customer=payload.signed_by_customer,
    )


def build_certificate_from_acts(
    payload: KS3FromActs,
    acts: list[KS2Act],
    previous: KS3Certificate | None = None,
) -> KS3Certificate:
    """Формирует справку КС-3 по актам КС-2 с нарастающими итогами.

    Нарастающие итоги берутся из предыдущей справки (`previous`) и могут быть
    переопределены явными остатками `opening_balances`. Если предыдущая справка
    относится к другому году, графа «с начала года» обнуляется.
    """
    if not acts:
        raise DomainError("Не передан ни один акт КС-2")

    _validate_acts_compatible(acts)

    period = payload.period or ReportingPeriod(
        start=min(act.period.start for act in acts),
        end=max(act.period.end for act in acts),
    )

    period_amounts = _group_acts(acts, payload.group_by)
    opening = _opening_balances(payload, previous, period)

    rows: list[KS3Row] = []
    for number, (name, amount) in enumerate(period_amounts.items(), start=1):
        from_start_base, from_year_base = opening.get(name, (ZERO, ZERO))
        rows.append(
            KS3Row(
                number=number,
                name=name,
                cost_from_start=money(from_start_base + amount),
                cost_from_year_start=money(from_year_base + amount),
                cost_for_period=money(amount),
            )
        )

    reference = acts[0]
    return _assemble_certificate(
        header=reference.header,
        document_number=payload.document_number,
        document_date=payload.document_date,
        period=period,
        rows=rows,
        vat_mode=reference.totals.vat_mode,
        vat_rate=reference.totals.vat_rate,
        act_ids=[act.id for act in acts],
        signed_by_contractor=payload.signed_by_contractor or reference.signed_by_contractor,
        signed_by_customer=payload.signed_by_customer or reference.signed_by_customer,
    )


def _assemble_certificate(
    *,
    header: DocumentHeader,
    document_number: str,
    document_date,
    period: ReportingPeriod,
    rows: list[KS3Row],
    vat_mode: VatMode,
    vat_rate: Decimal,
    act_ids: list[str],
    signed_by_contractor: str | None,
    signed_by_customer: str | None,
) -> KS3Certificate:
    net_period = sum((row.cost_for_period for row in rows), ZERO)
    net_from_start = sum((row.cost_from_start for row in rows), ZERO)
    net_from_year = sum((row.cost_from_year_start for row in rows), ZERO)

    totals = build_totals(net_period, vat_mode, vat_rate)
    return KS3Certificate(
        header=header,
        document_number=document_number,
        document_date=document_date,
        period=period,
        rows=rows,
        totals=totals,
        totals_from_start=column_totals(net_from_start, vat_mode, totals.vat_rate),
        totals_from_year_start=column_totals(net_from_year, vat_mode, totals.vat_rate),
        act_ids=act_ids,
        signed_by_contractor=signed_by_contractor,
        signed_by_customer=signed_by_customer,
    )


def _validate_acts_compatible(acts: Iterable[KS2Act]) -> None:
    """Справка формируется по одному договору и единому режиму НДС."""
    acts = list(acts)
    reference = acts[0]
    for act in acts[1:]:
        if act.header.contract.number != reference.header.contract.number:
            raise DomainError(
                "Акты относятся к разным договорам: "
                f"{reference.header.contract.number} и {act.header.contract.number}"
            )
        if act.header.contractor.name != reference.header.contractor.name:
            raise DomainError("Акты оформлены разными подрядчиками")
        if act.header.customer.name != reference.header.customer.name:
            raise DomainError("Акты оформлены разными заказчиками")
        if act.totals.vat_mode != reference.totals.vat_mode or (
            act.totals.vat_rate != reference.totals.vat_rate
        ):
            raise DomainError("Акты содержат разные ставки НДС")


def _group_acts(acts: list[KS2Act], group_by: str) -> "OrderedDict[str, Decimal]":
    """Суммы за отчётный период в разрезе строк справки."""
    grouped: "OrderedDict[str, Decimal]" = OrderedDict()
    for act in acts:
        if group_by == "act":
            key = f"Акт о приёмке выполненных работ № {act.document_number} от {act.document_date:%d.%m.%Y}"
        elif group_by == "total":
            key = TOTAL_ROW_TITLE
        else:  # "facility"
            key = act.header.facility or act.header.construction_site
        grouped[key] = grouped.get(key, ZERO) + act.totals.net
    return grouped


def _opening_balances(
    payload: KS3FromActs,
    previous: KS3Certificate | None,
    period: ReportingPeriod,
) -> dict[str, tuple[Decimal, Decimal]]:
    """Накопленные суммы прошлых периодов по наименованию строки."""
    balances: dict[str, tuple[Decimal, Decimal]] = {}

    if previous is not None:
        same_year = previous.period.end.year == period.end.year
        for row in previous.rows:
            balances[row.name] = (
                row.cost_from_start,
                row.cost_from_year_start if same_year else ZERO,
            )

    for balance in payload.opening_balances:
        if balance.cost_from_year_start > balance.cost_from_start:
            raise DomainError(
                f"Остаток с начала года больше остатка с начала работ по строке «{balance.name}»"
            )
        balances[balance.name] = (balance.cost_from_start, balance.cost_from_year_start)

    return balances
