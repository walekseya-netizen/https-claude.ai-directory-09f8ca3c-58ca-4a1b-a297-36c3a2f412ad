"""Выгрузка справки КС-3 в XLSX по унифицированной форме (ОКУД 0322001)."""

from __future__ import annotations

from decimal import Decimal

from openpyxl.worksheet.worksheet import Worksheet

from app.domain.models import KS3Certificate, VatMode
from app.export.common import (
    BOX,
    CENTER,
    FONT_BOLD,
    FONT_SMALL,
    FONT_TITLE,
    LEFT,
    RIGHT,
    UNDERLINE,
    caption,
    code_box,
    field,
    format_date,
    money_cell,
    new_sheet,
    to_bytes,
    write,
)

COLUMN_WIDTHS = {
    "A": 6,
    "B": 50,
    "C": 10,
    "D": 18,
    "E": 18,
    "F": 20,
}


def render_ks3(certificate: KS3Certificate) -> bytes:
    """Возвращает содержимое XLSX-файла справки КС-3."""
    workbook, sheet = new_sheet("КС-3", COLUMN_WIDTHS)
    row = _render_header(sheet, certificate)
    row = _render_table(sheet, certificate, row)
    _render_signatures(sheet, certificate, row + 2)
    return to_bytes(workbook)


def _render_header(sheet: Worksheet, certificate: KS3Certificate) -> int:
    header = certificate.header

    write(sheet, "E1:F1", "Унифицированная форма № КС-3", font=FONT_SMALL, alignment=RIGHT)
    write(
        sheet,
        "E2:F2",
        "Утверждена постановлением Госкомстата России от 11.11.99 № 100",
        font=FONT_SMALL,
        alignment=RIGHT,
    )
    write(sheet, "F3", "Коды", font=FONT_SMALL, alignment=CENTER, border=BOX)
    code_box(sheet, "E4", "F4", "Форма по ОКУД", certificate.okud)

    row = 5
    for label, organization, hint in (
        ("Инвестор", header.investor, "организация, адрес, телефон, факс"),
        ("Заказчик (генподрядчик)", header.customer, "организация, адрес, телефон, факс"),
        ("Подрядчик (субподрядчик)", header.contractor, "организация, адрес, телефон, факс"),
    ):
        value = organization.title_line() if organization else ""
        field(sheet, f"A{row}", f"B{row}:D{row}", label, value)
        code_box(sheet, f"E{row}", f"F{row}", "по ОКПО", organization.okpo if organization else None)
        caption(sheet, f"B{row + 1}:D{row + 1}", hint)
        row += 2

    field(sheet, f"A{row}", f"B{row}:D{row}", "Стройка", header.construction_site)
    caption(sheet, f"B{row + 1}:D{row + 1}", "наименование, адрес")
    row += 2

    if header.facility:
        field(sheet, f"A{row}", f"B{row}:D{row}", "Объект", header.facility)
        caption(sheet, f"B{row + 1}:D{row + 1}", "наименование")
        row += 2

    code_box(sheet, f"C{row}:E{row}", f"F{row}", "Вид деятельности по ОКДП", header.okdp)
    row += 1

    field(
        sheet,
        f"A{row}",
        f"B{row}:C{row}",
        "Договор подряда (контракт)",
        f"№ {header.contract.number} от {format_date(header.contract.date)}",
    )
    code_box(sheet, f"E{row}", f"F{row}", "номер", header.contract.number)
    row += 1
    code_box(sheet, f"E{row}", f"F{row}", "дата", format_date(header.contract.date))
    row += 1
    code_box(sheet, f"E{row}", f"F{row}", "Вид операции", header.operation_type)
    row += 2

    write(sheet, f"C{row}:C{row + 1}", "Номер документа", font=FONT_SMALL, alignment=CENTER, border=BOX)
    write(sheet, f"D{row}:D{row + 1}", "Дата составления", font=FONT_SMALL, alignment=CENTER, border=BOX)
    write(sheet, f"E{row}:F{row}", "Отчетный период", font=FONT_SMALL, alignment=CENTER, border=BOX)
    write(sheet, f"E{row + 1}", "с", font=FONT_SMALL, alignment=CENTER, border=BOX)
    write(sheet, f"F{row + 1}", "по", font=FONT_SMALL, alignment=CENTER, border=BOX)
    row += 2
    write(sheet, f"C{row}", certificate.document_number, alignment=CENTER, border=BOX)
    write(sheet, f"D{row}", format_date(certificate.document_date), alignment=CENTER, border=BOX)
    write(sheet, f"E{row}", format_date(certificate.period.start), alignment=CENTER, border=BOX)
    write(sheet, f"F{row}", format_date(certificate.period.end), alignment=CENTER, border=BOX)
    row += 2

    write(
        sheet,
        f"A{row}:F{row}",
        "СПРАВКА О СТОИМОСТИ ВЫПОЛНЕННЫХ РАБОТ И ЗАТРАТ",
        font=FONT_TITLE,
        alignment=CENTER,
    )
    sheet.row_dimensions[row].height = 22
    return row + 2


def _render_table(sheet: Worksheet, certificate: KS3Certificate, row: int) -> int:
    write(sheet, f"A{row}:A{row + 1}", "Номер по порядку", font=FONT_SMALL, alignment=CENTER, border=BOX)
    write(
        sheet,
        f"B{row}:B{row + 1}",
        "Наименование пусковых комплексов, этапов, объектов, видов выполненных работ, "
        "оборудования, затрат",
        font=FONT_SMALL,
        alignment=CENTER,
        border=BOX,
    )
    write(sheet, f"C{row}:C{row + 1}", "Код", font=FONT_SMALL, alignment=CENTER, border=BOX)
    write(
        sheet,
        f"D{row}:F{row}",
        "Стоимость выполненных работ и затрат, руб.",
        font=FONT_SMALL,
        alignment=CENTER,
        border=BOX,
    )
    write(sheet, f"D{row + 1}", "с начала проведения работ", font=FONT_SMALL, alignment=CENTER, border=BOX)
    write(sheet, f"E{row + 1}", "с начала года", font=FONT_SMALL, alignment=CENTER, border=BOX)
    write(
        sheet,
        f"F{row + 1}",
        "в том числе за отчетный период",
        font=FONT_SMALL,
        alignment=CENTER,
        border=BOX,
    )
    sheet.row_dimensions[row].height = 16
    sheet.row_dimensions[row + 1].height = 34
    row += 2

    for index, column in enumerate("ABCDEF", start=1):
        write(sheet, f"{column}{row}", index, font=FONT_SMALL, alignment=CENTER, border=BOX)
    row += 1

    for item in certificate.rows:
        write(sheet, f"A{row}", item.number, alignment=CENTER, border=BOX)
        write(sheet, f"B{row}", item.name, alignment=LEFT, border=BOX)
        write(sheet, f"C{row}", item.code or "", alignment=CENTER, border=BOX)
        money_cell(sheet, f"D{row}", item.cost_from_start)
        money_cell(sheet, f"E{row}", item.cost_from_year_start)
        money_cell(sheet, f"F{row}", item.cost_for_period)
        row += 1

    totals = certificate.totals
    if totals.vat_mode is VatMode.NONE:
        vat_label = "Сумма НДС (без НДС)"
    else:
        vat_label = f"Сумма НДС ({_format_number(totals.vat_rate)}%)"

    lines = (
        ("Итого", "net"),
        (vat_label, "vat"),
        ("Всего с учетом НДС", "gross"),
    )
    for label, attribute in lines:
        write(sheet, f"A{row}:C{row}", label, font=FONT_BOLD, alignment=RIGHT, border=BOX)
        money_cell(sheet, f"D{row}", getattr(certificate.totals_from_start, attribute), font=FONT_BOLD)
        money_cell(
            sheet, f"E{row}", getattr(certificate.totals_from_year_start, attribute), font=FONT_BOLD
        )
        money_cell(sheet, f"F{row}", getattr(totals, attribute), font=FONT_BOLD)
        row += 1

    return row


def _render_signatures(sheet: Worksheet, certificate: KS3Certificate, row: int) -> None:
    for label, signer, organization in (
        ("Заказчик (генподрядчик)", certificate.signed_by_customer, certificate.header.customer),
        ("Подрядчик (субподрядчик)", certificate.signed_by_contractor, certificate.header.contractor),
    ):
        write(sheet, f"A{row}:B{row}", label, font=FONT_BOLD, alignment=LEFT)
        write(sheet, f"C{row}:D{row}", signer or "", border=UNDERLINE)
        write(sheet, f"E{row}:F{row}", organization.name, border=UNDERLINE)
        caption(sheet, f"C{row + 1}:D{row + 1}", "должность, подпись")
        caption(sheet, f"E{row + 1}:F{row + 1}", "расшифровка подписи")
        row += 2
        write(sheet, f"A{row}", "М.П.", font=FONT_BOLD)
        row += 2


def _format_number(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    return text.replace(".", ",")
