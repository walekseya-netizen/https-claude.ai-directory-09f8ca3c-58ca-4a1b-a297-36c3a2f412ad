"""Выгрузка акта КС-2 в XLSX по унифицированной форме (ОКУД 0322005)."""

from __future__ import annotations

from decimal import Decimal

from openpyxl.worksheet.worksheet import Worksheet

from app.domain.models import KS2Act, VatMode
from app.export.common import (
    BOX,
    CENTER,
    FONT_BOLD,
    FONT_SMALL,
    FONT_TITLE,
    LEFT,
    QUANTITY_FORMAT,
    RIGHT,
    UNDERLINE,
    caption,
    code_box,
    field,
    format_date,
    format_money_text,
    money_cell,
    new_sheet,
    to_bytes,
    write,
)

COLUMN_WIDTHS = {
    "A": 6,
    "B": 11,
    "C": 44,
    "D": 13,
    "E": 12,
    "F": 12,
    "G": 14,
    "H": 16,
}


def render_ks2(act: KS2Act) -> bytes:
    """Возвращает содержимое XLSX-файла акта КС-2."""
    workbook, sheet = new_sheet("КС-2", COLUMN_WIDTHS)
    row = _render_header(sheet, act)
    row = _render_table(sheet, act, row)
    _render_signatures(sheet, act, row + 2)
    return to_bytes(workbook)


def _render_header(sheet: Worksheet, act: KS2Act) -> int:
    header = act.header

    write(sheet, "G1:H1", "Унифицированная форма № КС-2", font=FONT_SMALL, alignment=RIGHT)
    write(
        sheet,
        "G2:H2",
        "Утверждена постановлением Госкомстата России от 11.11.99 № 100",
        font=FONT_SMALL,
        alignment=RIGHT,
    )
    write(sheet, "H3", "Коды", font=FONT_SMALL, alignment=CENTER, border=BOX)
    code_box(sheet, "G4", "H4", "Форма по ОКУД", act.okud)

    row = 5
    for label, organization, hint in (
        ("Инвестор", header.investor, "организация, адрес, телефон, факс"),
        ("Заказчик (генподрядчик)", header.customer, "организация, адрес, телефон, факс"),
        ("Подрядчик (субподрядчик)", header.contractor, "организация, адрес, телефон, факс"),
    ):
        value = organization.title_line() if organization else ""
        field(sheet, f"A{row}", f"B{row}:F{row}", label, value)
        code_box(sheet, f"G{row}", f"H{row}", "по ОКПО", organization.okpo if organization else None)
        caption(sheet, f"B{row + 1}:F{row + 1}", hint)
        row += 2

    field(sheet, f"A{row}", f"B{row}:F{row}", "Стройка", header.construction_site)
    caption(sheet, f"B{row + 1}:F{row + 1}", "наименование, адрес")
    row += 2

    field(sheet, f"A{row}", f"B{row}:F{row}", "Объект", header.facility)
    caption(sheet, f"B{row + 1}:F{row + 1}", "наименование")
    row += 2

    code_box(sheet, f"E{row}:G{row}", f"H{row}", "Вид деятельности по ОКДП", header.okdp)
    row += 1

    field(
        sheet,
        f"A{row}",
        f"B{row}:E{row}",
        "Договор подряда (контракт)",
        f"№ {header.contract.number} от {format_date(header.contract.date)}",
    )
    code_box(sheet, f"G{row}", f"H{row}", "номер", header.contract.number)
    row += 1
    code_box(sheet, f"G{row}", f"H{row}", "дата", format_date(header.contract.date))
    row += 1
    code_box(sheet, f"G{row}", f"H{row}", "Вид операции", header.operation_type)
    row += 2

    write(sheet, f"E{row}:E{row + 1}", "Номер документа", font=FONT_SMALL, alignment=CENTER, border=BOX)
    write(sheet, f"F{row}:F{row + 1}", "Дата составления", font=FONT_SMALL, alignment=CENTER, border=BOX)
    write(sheet, f"G{row}:H{row}", "Отчетный период", font=FONT_SMALL, alignment=CENTER, border=BOX)
    write(sheet, f"G{row + 1}", "с", font=FONT_SMALL, alignment=CENTER, border=BOX)
    write(sheet, f"H{row + 1}", "по", font=FONT_SMALL, alignment=CENTER, border=BOX)
    row += 2
    write(sheet, f"E{row}", act.document_number, alignment=CENTER, border=BOX)
    write(sheet, f"F{row}", format_date(act.document_date), alignment=CENTER, border=BOX)
    write(sheet, f"G{row}", format_date(act.period.start), alignment=CENTER, border=BOX)
    write(sheet, f"H{row}", format_date(act.period.end), alignment=CENTER, border=BOX)
    row += 2

    write(sheet, f"A{row}:H{row}", "АКТ О ПРИЕМКЕ ВЫПОЛНЕННЫХ РАБОТ", font=FONT_TITLE, alignment=CENTER)
    sheet.row_dimensions[row].height = 22
    row += 1

    write(
        sheet,
        f"A{row}:H{row}",
        "Сметная (договорная) стоимость в соответствии с договором подряда (субподряда) "
        f"{format_money_text(act.contract_cost)} руб.",
        alignment=CENTER,
    )
    return row + 2


def _render_table(sheet: Worksheet, act: KS2Act, row: int) -> int:
    headers = [
        ("A", "Номер по порядку"),
        ("B", "Позиция по смете"),
        ("C", "Наименование работ"),
        ("D", "Номер единичной расценки"),
        ("E", "Единица измерения"),
    ]
    for column, title in headers:
        write(sheet, f"{column}{row}:{column}{row + 1}", title, font=FONT_SMALL, alignment=CENTER, border=BOX)
    write(sheet, f"F{row}:H{row}", "Выполнено работ", font=FONT_SMALL, alignment=CENTER, border=BOX)
    write(sheet, f"F{row + 1}", "количество", font=FONT_SMALL, alignment=CENTER, border=BOX)
    write(sheet, f"G{row + 1}", "цена за единицу, руб.", font=FONT_SMALL, alignment=CENTER, border=BOX)
    write(sheet, f"H{row + 1}", "стоимость, руб.", font=FONT_SMALL, alignment=CENTER, border=BOX)
    sheet.row_dimensions[row].height = 16
    sheet.row_dimensions[row + 1].height = 30
    row += 2

    for index, column in enumerate("ABCDEFGH", start=1):
        write(sheet, f"{column}{row}", index, font=FONT_SMALL, alignment=CENTER, border=BOX)
    row += 1

    for item in act.items:
        name = item.name
        if item.coefficient != Decimal("1"):
            name = f"{name} (с коэффициентом {_format_number(item.coefficient)})"
        write(sheet, f"A{row}", item.number, alignment=CENTER, border=BOX)
        write(sheet, f"B{row}", item.estimate_position or "", alignment=CENTER, border=BOX)
        write(sheet, f"C{row}", name, alignment=LEFT, border=BOX)
        write(sheet, f"D{row}", item.unit_rate_number or "", alignment=CENTER, border=BOX)
        write(sheet, f"E{row}", item.unit, alignment=CENTER, border=BOX)
        write(
            sheet,
            f"F{row}",
            float(item.quantity),
            alignment=RIGHT,
            border=BOX,
            number_format=QUANTITY_FORMAT,
        )
        money_cell(sheet, f"G{row}", item.unit_price)
        money_cell(sheet, f"H{row}", item.amount)
        row += 1

    totals = act.totals
    if totals.vat_mode is VatMode.NONE:
        vat_label = "Сумма НДС (без НДС)"
    else:
        vat_label = f"Сумма НДС ({_format_number(totals.vat_rate)}%)"

    for label, value in (
        ("Итого", totals.net),
        (vat_label, totals.vat),
        ("Всего с учетом НДС", totals.gross),
    ):
        write(sheet, f"A{row}:G{row}", label, font=FONT_BOLD, alignment=RIGHT, border=BOX)
        money_cell(sheet, f"H{row}", value, font=FONT_BOLD)
        row += 1

    return row


def _render_signatures(sheet: Worksheet, act: KS2Act, row: int) -> None:
    for label, signer, organization in (
        ("Сдал", act.signed_by_contractor, act.header.contractor),
        ("Принял", act.signed_by_customer, act.header.customer),
    ):
        write(sheet, f"A{row}", label, font=FONT_BOLD)
        field(sheet, f"B{row}", f"C{row}:D{row}", "", signer or "")
        write(sheet, f"E{row}:F{row}", "", border=UNDERLINE)
        field(sheet, f"G{row}", f"H{row}", "", organization.name)
        caption(sheet, f"C{row + 1}:D{row + 1}", "должность")
        caption(sheet, f"E{row + 1}:F{row + 1}", "подпись")
        caption(sheet, f"G{row + 1}:H{row + 1}", "расшифровка подписи")
        row += 3


def _format_number(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    return text.replace(".", ",")
