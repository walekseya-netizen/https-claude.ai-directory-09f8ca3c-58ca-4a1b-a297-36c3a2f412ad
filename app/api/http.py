"""Вспомогательные функции HTTP-слоя."""

from __future__ import annotations

from urllib.parse import quote

from fastapi import Response

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

#: Описание ответа с XLSX-файлом для OpenAPI.
XLSX_RESPONSES = {
    200: {
        "content": {XLSX_MEDIA_TYPE: {"schema": {"type": "string", "format": "binary"}}},
        "description": "Файл унифицированной формы",
    }
}


def xlsx_response(content: bytes, filename: str) -> Response:
    """Отдаёт XLSX как вложение с корректным кириллическим именем файла."""
    disposition = f"attachment; filename*=UTF-8''{quote(filename)}"
    return Response(
        content=content,
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": disposition},
    )
