"""Тесты защиты API ключом доступа."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests.conftest import ks2_payload

API_KEY = "test-key-2f8c"


@pytest.fixture()
def secured_client(tmp_path):
    settings = Settings(database_path=str(tmp_path / "ks.sqlite3"), api_key=API_KEY)
    with TestClient(create_app(settings)) as client:
        yield client


def test_api_requires_key(secured_client):
    response = secured_client.get("/api/v1/ks2")

    assert response.status_code == 401
    assert "X-API-Key" in response.json()["detail"]


def test_wrong_key_is_rejected(secured_client):
    response = secured_client.get("/api/v1/ks2", headers={"X-API-Key": "wrong-key"})

    assert response.status_code == 401


def test_correct_key_grants_access(secured_client):
    headers = {"X-API-Key": API_KEY}

    created = secured_client.post("/api/v1/ks2", json=ks2_payload(), headers=headers)
    assert created.status_code == 201

    listed = secured_client.get("/api/v1/ks2", headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()) == 1


def test_health_and_docs_stay_open(secured_client):
    assert secured_client.get("/health").status_code == 200
    assert secured_client.get("/openapi.json").status_code == 200


def test_service_without_key_is_open(client):
    assert client.get("/api/v1/ks2").status_code == 200
