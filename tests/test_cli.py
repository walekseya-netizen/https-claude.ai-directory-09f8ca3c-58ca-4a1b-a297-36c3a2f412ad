"""Тесты выгрузки и загрузки документов."""

from __future__ import annotations

import json
import os
from datetime import date

import pytest

from app import cli
from app.config import Settings
from app.domain.calc import build_act, build_certificate_from_acts
from app.domain.models import KS2Input, KS3FromActs
from app.storage.factory import create_repository
from tests.conftest import ks2_payload

POSTGRES_URL = os.getenv("KS_TEST_DATABASE_URL", "")


def fill(database_path: str) -> tuple[str, str]:
    repository = create_repository(Settings(database_path=database_path))
    try:
        act = repository.save_act(build_act(KS2Input.model_validate(ks2_payload())))
        certificate = repository.save_certificate(
            build_certificate_from_acts(
                KS3FromActs(act_ids=[act.id], document_number="1", document_date=date(2026, 3, 31)),
                [act],
            )
        )
        return act.id, certificate.id
    finally:
        repository.close()


def test_dump_and_load_round_trip(tmp_path, capsys):
    source = tmp_path / "source.sqlite3"
    target = tmp_path / "target.sqlite3"
    backup = tmp_path / "backup.json"
    act_id, certificate_id = fill(str(source))

    assert cli.main(["--database-path", str(source), "dump", "--output", str(backup)]) == 0
    payload = json.loads(backup.read_text(encoding="utf-8"))
    assert payload["format"] == "ks-documents/1"
    assert payload["acts"][0]["totals"]["net"] == "1400174.83"

    assert cli.main(["--database-path", str(target), "load", "--input", str(backup)]) == 0

    repository = create_repository(Settings(database_path=str(target)))
    try:
        restored = repository.get_act(act_id)
        assert restored.totals.gross == build_act(
            KS2Input.model_validate(ks2_payload())
        ).totals.gross
        assert repository.get_certificate(certificate_id).rows[0].cost_for_period == restored.totals.net
    finally:
        repository.close()

    assert "Загружено: актов КС-2 — 1" in capsys.readouterr().out


def test_load_rejects_foreign_format(tmp_path, capsys):
    broken = tmp_path / "broken.json"
    broken.write_text(json.dumps({"format": "чужой", "acts": []}), encoding="utf-8")

    assert cli.main(["--database-path", str(tmp_path / "db.sqlite3"), "load", "--input", str(broken)]) == 1
    assert "Неизвестный формат" in capsys.readouterr().err


@pytest.mark.skipif(not POSTGRES_URL, reason="KS_TEST_DATABASE_URL не задан")
def test_migration_from_sqlite_to_postgres(tmp_path):
    source = tmp_path / "source.sqlite3"
    backup = tmp_path / "backup.json"
    act_id, certificate_id = fill(str(source))

    assert cli.main(["--database-path", str(source), "dump", "--output", str(backup)]) == 0
    assert cli.main(["--database-url", POSTGRES_URL, "load", "--input", str(backup)]) == 0

    repository = create_repository(Settings(database_url=POSTGRES_URL))
    try:
        assert repository.get_act(act_id).totals.net.as_tuple().exponent == -2
        assert repository.get_certificate(certificate_id).act_ids == [act_id]
        repository.delete_certificate(certificate_id)
        repository.delete_act(act_id)
    finally:
        repository.close()
