"""Общие примитивы выгрузки унифицированных форм в XLSX."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from io import BytesIO

from openpyxl.styles import Alignment, Border, Font, Side
from openpyxl.workbook import Workbook
from openpyxl.worksheet.worksheet import Worksheet

FONT_NAME = "Times New Roman"

FONT = Font(name=FONT_NAME, size=10)
FONT_BOLD = Font(name=FONT_NAME, size=10, bold=True)
FONT_SMALL = Font(name=FONT_NAME, size=7)
FONT_TITLE = Font(name=FONT_NAME, size=14, bold=True)

MONEY_FORMAT = "#,##0.00"
QUANTITY_FORMAT = "#,##0.######"

CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
LEFT = Alignment(horizontal="left", vertical="center", wrap_text=True)
RIGHT = Alignment(horizontal="right", vertical="center", wrap_text=True)
LEFT_TOP = Alignment(horizontal="left", vertical="top", wrap_text=True)

_thin = Side(style="thin")
BOX = Border(left=_thin, right=_thin, top=_thin, bottom=_thin)
UNDERLINE = Border(bottom=_thin)


def new_sheet(title: str, widths: dict[str, float]) -> tuple[Workbook, Worksheet]:
    """Создаёт книгу с единственным листом и заданными ширинами колонок."""
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = title
    for column, width in widths.items():
        sheet.column_dimensions[column].width = width
    sheet.page_setup.orientation = "portrait"
    sheet.page_setup.paperSize = sheet.PAPERSIZE_A4
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 0
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.print_options.horizontalCentered = True
    return workbook, sheet


def write(
    sheet: Worksheet,
    coordinate: str,
    value,
    *,
    font: Font = FONT,
    alignment: Alignment = LEFT,
    border: Border | None = None,
    number_format: str | None = None,
):
    """Пишет значение в ячейку (или в первую ячейку объединённого диапазона)."""
    if ":" in coordinate:
        sheet.merge_cells(coordinate)
        coordinate = coordinate.split(":", 1)[0]
    cell = sheet[coordinate]
    cell.value = value
    cell.font = font
    cell.alignment = alignment
    if number_format:
        cell.number_format = number_format
    if border is not None:
        _apply_border(sheet, cell, border)
    return cell


def _apply_border(sheet: Worksheet, cell, border: Border) -> None:
    """Проставляет рамку по всем ячейкам объединённого диапазона."""
    for merged in sheet.merged_cells.ranges:
        if cell.coordinate in merged:
            for row in sheet[merged.coord]:
                for item in row:
                    item.border = border
            return
    cell.border = border


def caption(sheet: Worksheet, coordinate: str, text: str) -> None:
    """Мелкая подпись под линией реквизита."""
    write(sheet, coordinate, text, font=FONT_SMALL, alignment=CENTER)


def field(sheet: Worksheet, label_cell: str, value_cell: str, label: str, value: str | None) -> None:
    """Реквизит формы: название слева, значение на подчёркнутой линии."""
    write(sheet, label_cell, label, font=FONT)
    write(sheet, value_cell, value or "", font=FONT, alignment=LEFT, border=UNDERLINE)


def code_box(sheet: Worksheet, label_cell: str, value_cell: str, label: str, value) -> None:
    """Правая колонка «Коды» унифицированной формы."""
    write(sheet, label_cell, label, font=FONT, alignment=RIGHT)
    write(sheet, value_cell, value if value is not None else "", font=FONT, alignment=CENTER, border=BOX)


def money_cell(sheet: Worksheet, coordinate: str, value: Decimal, *, font: Font = FONT) -> None:
    write(
        sheet,
        coordinate,
        float(value),
        font=font,
        alignment=RIGHT,
        border=BOX,
        number_format=MONEY_FORMAT,
    )


def format_money_text(value: Decimal | None) -> str:
    """Сумма для текстовой строки формы: «5 000 000,00»."""
    if value is None:
        return ""
    return f"{value:,.2f}".replace(",", "\u00a0").replace(".", ",")


def format_date(value: date | None) -> str:
    return value.strftime("%d.%m.%Y") if value else ""


def to_bytes(workbook: Workbook) -> bytes:
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
