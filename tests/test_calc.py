"""Тесты расчёта форм КС-2 и КС-3."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.domain.calc import build_act, build_certificate_from_acts
from app.domain.errors import DomainError
from app.domain.models import (
    Contract,
    DocumentHeader,
    KS2Input,
    KS3FromActs,
    Organization,
    ReportingPeriod,
    VatMode,
    WorkItemInput,
)


def make_header(**overrides) -> DocumentHeader:
    data = {
        "customer": Organization(name="ООО «Заказчик»"),
        "contractor": Organization(name="ООО «Подрядчик»"),
        "construction_site": "Жилой комплекс «Северный»",
        "facility": "Корпус 1",
        "contract": Contract(number="СМР-15/2026", date=date(2026, 1, 15)),
    }
    data.update(overrides)
    return DocumentHeader(**data)


def make_act(
    *,
    number: str = "1",
    period: tuple[date, date] = (date(2026, 3, 1), date(2026, 3, 31)),
    items: list[WorkItemInput] | None = None,
    header: DocumentHeader | None = None,
    vat_mode: VatMode = VatMode.CHARGED,
    vat_rate: str = "20",
):
    payload = KS2Input(
        header=header or make_header(),
        document_number=number,
        document_date=period[1],
        period=ReportingPeriod(start=period[0], end=period[1]),
        vat_mode=vat_mode,
        vat_rate=Decimal(vat_rate),
        items=items
        or [WorkItemInput(name="Монолитные работы", unit="м3", quantity="10", unit_price="1000")],
    )
    return build_act(payload)


def test_item_amount_rounds_to_kopecks():
    act = make_act(
        items=[WorkItemInput(name="Кладка", unit="м3", quantity="12.5", unit_price="1533.333")]
    )

    assert act.items[0].amount == Decimal("19166.66")
    assert act.items[0].number == 1


def test_coefficient_applies_to_amount():
    act = make_act(
        items=[
            WorkItemInput(
                name="Кладка", unit="м3", quantity="100", unit_price="1000", coefficient="1.15"
            )
        ]
    )

    assert act.items[0].amount == Decimal("115000.00")


def test_totals_sum_rounded_lines_not_raw_products():
    act = make_act(
        items=[
            WorkItemInput(name="Работа 1", unit="шт", quantity="3", unit_price="0.005"),
            WorkItemInput(name="Работа 2", unit="шт", quantity="3", unit_price="0.005"),
        ]
    )

    # 3 × 0,005 = 0,015 → 0,02 по каждой строке, итог считается по округлённым строкам
    assert [item.amount for item in act.items] == [Decimal("0.02"), Decimal("0.02")]
    assert act.totals.net == Decimal("0.04")


def test_vat_charged_on_top():
    act = make_act(
        items=[WorkItemInput(name="Работы", unit="шт", quantity="1", unit_price="19166.63")]
    )

    assert act.totals.net == Decimal("19166.63")
    assert act.totals.vat == Decimal("3833.33")
    assert act.totals.gross == Decimal("22999.96")


def test_vat_mode_none_zeroes_rate_and_amount():
    act = make_act(vat_mode=VatMode.NONE, vat_rate="20")

    assert act.totals.vat_rate == Decimal("0")
    assert act.totals.vat == Decimal("0")
    assert act.totals.gross == act.totals.net


def test_reduced_vat_rate():
    act = make_act(vat_rate="5")

    assert act.totals.vat == Decimal("500.00")
    assert act.totals.gross == Decimal("10500.00")


def test_document_date_before_period_start_is_rejected():
    with pytest.raises(ValueError):
        KS2Input(
            header=make_header(),
            document_number="1",
            document_date=date(2026, 2, 1),
            period=ReportingPeriod(start=date(2026, 3, 1), end=date(2026, 3, 31)),
            items=[WorkItemInput(name="Работы", unit="шт", quantity="1", unit_price="1")],
        )


def test_period_order_is_validated():
    with pytest.raises(ValueError):
        ReportingPeriod(start=date(2026, 3, 31), end=date(2026, 3, 1))


# --------------------------------------------------------------------------
# КС-3
# --------------------------------------------------------------------------


def from_acts(acts, previous=None, **overrides):
    payload = {
        "act_ids": [act.id for act in acts],
        "document_number": "1",
        "document_date": date(2026, 3, 31),
    }
    payload.update(overrides)
    return build_certificate_from_acts(KS3FromActs(**payload), acts, previous)


def test_certificate_groups_acts_by_facility():
    first = make_act(number="1", header=make_header(facility="Корпус 1"))
    second = make_act(number="2", header=make_header(facility="Корпус 2"))
    third = make_act(number="3", header=make_header(facility="Корпус 1"))

    certificate = from_acts([first, second, third])

    assert [(row.number, row.name, row.cost_for_period) for row in certificate.rows] == [
        (1, "Корпус 1", Decimal("20000.00")),
        (2, "Корпус 2", Decimal("10000.00")),
    ]
    assert certificate.totals.net == Decimal("30000.00")
    assert certificate.totals.vat == Decimal("6000.00")
    assert certificate.totals.gross == Decimal("36000.00")


def test_certificate_group_by_act_and_total():
    first = make_act(number="1")
    second = make_act(number="2")

    by_act = from_acts([first, second], group_by="act")
    assert len(by_act.rows) == 2
    assert by_act.rows[0].name.startswith("Акт о приёмке выполненных работ № 1")

    single = from_acts([first, second], group_by="total")
    assert len(single.rows) == 1
    assert single.rows[0].cost_for_period == Decimal("20000.00")


def test_certificate_period_covers_all_acts():
    march = make_act(number="1", period=(date(2026, 3, 1), date(2026, 3, 31)))
    april = make_act(number="2", period=(date(2026, 4, 1), date(2026, 4, 30)))

    certificate = from_acts([march, april], document_date=date(2026, 4, 30))

    assert certificate.period.start == date(2026, 3, 1)
    assert certificate.period.end == date(2026, 4, 30)


def test_cumulative_totals_continue_previous_certificate():
    march = make_act(number="1", period=(date(2026, 3, 1), date(2026, 3, 31)))
    first = from_acts([march])

    april = make_act(number="2", period=(date(2026, 4, 1), date(2026, 4, 30)))
    second = from_acts(
        [april], previous=first, document_number="2", document_date=date(2026, 4, 30)
    )

    row = second.rows[0]
    assert row.cost_for_period == Decimal("10000.00")
    assert row.cost_from_year_start == Decimal("20000.00")
    assert row.cost_from_start == Decimal("20000.00")
    assert second.totals_from_start.net == Decimal("20000.00")
    assert second.totals_from_start.vat == Decimal("4000.00")
    assert second.totals_from_start.gross == Decimal("24000.00")


def test_new_year_resets_year_to_date_column():
    december = make_act(number="1", period=(date(2026, 12, 1), date(2026, 12, 31)))
    previous = from_acts([december], document_date=date(2026, 12, 31))

    january = make_act(number="2", period=(date(2027, 1, 1), date(2027, 1, 31)))
    certificate = from_acts(
        [january], previous=previous, document_number="2", document_date=date(2027, 1, 31)
    )

    row = certificate.rows[0]
    assert row.cost_from_start == Decimal("20000.00")
    assert row.cost_from_year_start == Decimal("10000.00")


def test_opening_balances_override_previous_certificate():
    act = make_act(header=make_header(facility="Корпус 1"))

    certificate = from_acts(
        [act],
        opening_balances=[
            {"name": "Корпус 1", "cost_from_start": "500000", "cost_from_year_start": "120000"}
        ],
    )

    row = certificate.rows[0]
    assert row.cost_from_start == Decimal("510000.00")
    assert row.cost_from_year_start == Decimal("130000.00")


def test_acts_from_different_contracts_are_rejected():
    first = make_act(number="1")
    second = make_act(
        number="2",
        header=make_header(contract=Contract(number="СМР-16/2026", date=date(2026, 2, 1))),
    )

    with pytest.raises(DomainError, match="разным договорам"):
        from_acts([first, second])


def test_acts_with_different_vat_rates_are_rejected():
    first = make_act(number="1", vat_rate="20")
    second = make_act(number="2", vat_rate="10")

    with pytest.raises(DomainError, match="ставки НДС"):
        from_acts([first, second])


def test_inconsistent_opening_balance_is_rejected():
    act = make_act(header=make_header(facility="Корпус 1"))

    with pytest.raises(DomainError, match="Остаток с начала года"):
        from_acts(
            [act],
            opening_balances=[
                {"name": "Корпус 1", "cost_from_start": "100", "cost_from_year_start": "200"}
            ],
        )
