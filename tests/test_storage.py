"""Контракт хранилища: одни и те же проверки для SQLite и PostgreSQL.

Тесты PostgreSQL выполняются, если задана переменная окружения
`KS_TEST_DATABASE_URL` с адресом тестовой базы, иначе пропускаются.
"""

from __future__ import annotations

import os
from datetime import date

import pytest

from app.domain.calc import build_act, build_certificate_from_acts
from app.domain.errors import NotFoundError
from app.domain.models import KS2Input, KS3FromActs
from app.storage.factory import create_repository
from app.config import Settings
from tests.conftest import ks2_payload

POSTGRES_URL = os.getenv("KS_TEST_DATABASE_URL", "")


@pytest.fixture(params=["sqlite", "postgres"])
def repository(request, tmp_path):
    if request.param == "postgres":
        if not POSTGRES_URL:
            pytest.skip("KS_TEST_DATABASE_URL не задан — тесты PostgreSQL пропущены")
        settings = Settings(database_url=POSTGRES_URL)
    else:
        settings = Settings(database_path=str(tmp_path / "ks.sqlite3"))

    storage = create_repository(settings)
    _clear(storage)
    try:
        yield storage
    finally:
        _clear(storage)
        storage.close()


def _clear(storage) -> None:
    for act in storage.list_acts(limit=500):
        storage.delete_act(act.id)
    for certificate in storage.list_certificates(limit=500):
        storage.delete_certificate(certificate.id)


def make_act(**overrides):
    return build_act(KS2Input.model_validate(ks2_payload(**overrides)))


def test_save_and_read_act(repository):
    act = repository.save_act(make_act())

    stored = repository.get_act(act.id)
    assert stored == act
    assert stored.totals.net == act.totals.net
    assert stored.items[0].amount == act.items[0].amount


def test_missing_act_raises(repository):
    with pytest.raises(NotFoundError):
        repository.get_act("нет такого")


def test_save_is_idempotent_by_id(repository):
    act = repository.save_act(make_act())
    repository.save_act(act.model_copy(update={"document_number": "1-исправленный"}))

    assert len(repository.list_acts()) == 1
    assert repository.get_act(act.id).document_number == "1-исправленный"


def test_list_filters(repository):
    repository.save_act(make_act())
    repository.save_act(
        make_act(
            document_number="2",
            document_date="2026-04-30",
            period={"start": "2026-04-01", "end": "2026-04-30"},
        )
    )

    assert len(repository.list_acts()) == 2
    assert len(repository.list_acts(contract_number="СМР-15/2026")) == 2
    assert len(repository.list_acts(contract_number="нет такого")) == 0
    assert len(repository.list_acts(period_from=date(2026, 4, 1))) == 1
    assert len(repository.list_acts(period_to=date(2026, 3, 31))) == 1
    assert len(repository.list_acts(limit=1)) == 1
    assert len(repository.list_acts(limit=1, offset=1)) == 1


def test_get_acts_keeps_order_and_drops_duplicates(repository):
    first = repository.save_act(make_act())
    second = repository.save_act(make_act(document_number="2"))

    found = repository.get_acts([second.id, first.id, second.id])

    assert [act.id for act in found] == [second.id, first.id]


def test_delete_act(repository):
    act = repository.save_act(make_act())

    repository.delete_act(act.id)

    with pytest.raises(NotFoundError):
        repository.get_act(act.id)
    with pytest.raises(NotFoundError):
        repository.delete_act(act.id)


def test_certificate_round_trip(repository):
    act = repository.save_act(make_act())
    certificate = build_certificate_from_acts(
        KS3FromActs(act_ids=[act.id], document_number="1", document_date=date(2026, 3, 31)),
        [act],
    )

    repository.save_certificate(certificate)
    stored = repository.get_certificate(certificate.id)

    assert stored == certificate
    assert stored.rows[0].cost_for_period == act.totals.net
    assert stored.totals_from_start.gross == certificate.totals_from_start.gross
    assert len(repository.list_certificates(contract_number="СМР-15/2026")) == 1

    repository.delete_certificate(certificate.id)
    with pytest.raises(NotFoundError):
        repository.get_certificate(certificate.id)


@pytest.mark.skipif(not POSTGRES_URL, reason="KS_TEST_DATABASE_URL не задан")
def test_full_flow_over_postgres():
    """Сквозная проверка API поверх PostgreSQL: акт, справка и выгрузка XLSX."""
    from fastapi.testclient import TestClient

    from app.main import create_app

    settings = Settings(database_url=POSTGRES_URL)
    with TestClient(create_app(settings)) as client:
        act = client.post("/api/v1/ks2", json=ks2_payload()).json()
        assert act["totals"]["gross"] == "1680209.80"

        certificate = client.post(
            "/api/v1/ks3/from-acts",
            json={
                "act_ids": [act["id"]],
                "document_number": "1",
                "document_date": "2026-03-31",
            },
        ).json()
        assert certificate["rows"][0]["cost_for_period"] == "1400174.83"

        xlsx = client.get(f"/api/v1/ks3/{certificate['id']}/xlsx")
        assert xlsx.status_code == 200
        assert xlsx.content.startswith(b"PK")

        assert client.delete(f"/api/v1/ks3/{certificate['id']}").status_code == 204
        assert client.delete(f"/api/v1/ks2/{act['id']}").status_code == 204
