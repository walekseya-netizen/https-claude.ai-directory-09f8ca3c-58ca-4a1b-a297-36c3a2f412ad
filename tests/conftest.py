"""Общие фикстуры и конструкторы тестовых данных."""

from __future__ import annotations

from datetime import date
from typing import Any, Iterator

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture()
def client(tmp_path) -> Iterator[TestClient]:
    settings = Settings(database_path=str(tmp_path / "ks.sqlite3"))
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def header_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "investor": {"name": "АО «Инвестор»", "okpo": "12345678"},
        "customer": {
            "name": "ООО «Заказчик»",
            "address": "г. Москва, ул. Тверская, д. 1",
            "phone": "+7 495 000-00-00",
            "okpo": "87654321",
            "inn": "7701234567",
        },
        "contractor": {
            "name": "ООО «Подрядчик»",
            "address": "г. Москва, ул. Строителей, д. 5",
            "okpo": "11223344",
        },
        "construction_site": "Жилой комплекс «Северный», г. Москва, ул. Полярная, д. 10",
        "facility": "Корпус 1",
        "contract": {"number": "СМР-15/2026", "date": "2026-01-15"},
    }
    payload.update(overrides)
    return payload


def ks2_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "header": header_payload(),
        "document_number": "1",
        "document_date": "2026-03-31",
        "period": {"start": "2026-03-01", "end": "2026-03-31"},
        "contract_cost": "5000000.00",
        "items": [
            {
                "estimate_position": "1-1",
                "name": "Устройство монолитных железобетонных стен",
                "unit_rate_number": "ФЕР06-01-015-01",
                "unit": "м3",
                "quantity": "125.5",
                "unit_price": "8450.75",
            },
            {
                "estimate_position": "1-2",
                "name": "Кладка наружных стен из керамического кирпича",
                "unit": "м3",
                "quantity": "48.25",
                "unit_price": "6120.40",
                "coefficient": "1.15",
            },
        ],
        "signed_by_contractor": "Производитель работ Иванов И.И.",
        "signed_by_customer": "Технический заказчик Петров П.П.",
    }
    payload.update(overrides)
    return payload


def create_act(client: TestClient, **overrides: Any) -> dict[str, Any]:
    response = client.post("/api/v1/ks2", json=ks2_payload(**overrides))
    assert response.status_code == 201, response.text
    return response.json()


def month_period(year: int, month: int, last_day: int) -> dict[str, str]:
    return {
        "start": date(year, month, 1).isoformat(),
        "end": date(year, month, last_day).isoformat(),
    }
