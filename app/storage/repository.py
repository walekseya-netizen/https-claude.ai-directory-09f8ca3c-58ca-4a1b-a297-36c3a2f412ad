"""Хранилище документов КС-2/КС-3 на SQLite.

Документ целиком хранится как JSON, а поля, по которым идёт поиск,
дублируются в отдельные колонки.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Iterator

from app.domain.errors import NotFoundError
from app.domain.models import KS2Act, KS3Certificate

SCHEMA = """
CREATE TABLE IF NOT EXISTS acts (
    id              TEXT PRIMARY KEY,
    document_number TEXT NOT NULL,
    document_date   TEXT NOT NULL,
    period_start    TEXT NOT NULL,
    period_end      TEXT NOT NULL,
    contract_number TEXT NOT NULL,
    contractor      TEXT NOT NULL,
    customer        TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    payload         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_acts_contract ON acts (contract_number);
CREATE INDEX IF NOT EXISTS idx_acts_period ON acts (period_end);

CREATE TABLE IF NOT EXISTS certificates (
    id              TEXT PRIMARY KEY,
    document_number TEXT NOT NULL,
    document_date   TEXT NOT NULL,
    period_start    TEXT NOT NULL,
    period_end      TEXT NOT NULL,
    contract_number TEXT NOT NULL,
    contractor      TEXT NOT NULL,
    customer        TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    payload         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_certificates_contract ON certificates (contract_number);
CREATE INDEX IF NOT EXISTS idx_certificates_period ON certificates (period_end);
"""


class DocumentRepository:
    """CRUD для актов КС-2 и справок КС-3."""

    def __init__(self, database: str | Path) -> None:
        self.database = str(database)
        if self.database != ":memory:":
            Path(self.database).parent.mkdir(parents=True, exist_ok=True)
        self._shared: sqlite3.Connection | None = None
        if self.database == ":memory:":
            # in-memory база живёт ровно столько, сколько открыто соединение
            self._shared = self._connect()
        with self._cursor() as cursor:
            cursor.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    @contextmanager
    def _cursor(self) -> Iterator[sqlite3.Cursor]:
        connection = self._shared or self._connect()
        try:
            with connection:
                yield connection.cursor()
        finally:
            if self._shared is None:
                connection.close()

    def close(self) -> None:
        if self._shared is not None:
            self._shared.close()
            self._shared = None

    # ------------------------------------------------------------------
    # КС-2
    # ------------------------------------------------------------------

    def save_act(self, act: KS2Act) -> KS2Act:
        with self._cursor() as cursor:
            cursor.execute(
                """
                INSERT OR REPLACE INTO acts (id, document_number, document_date, period_start,
                                             period_end, contract_number, contractor, customer,
                                             created_at, payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    act.id,
                    act.document_number,
                    act.document_date.isoformat(),
                    act.period.start.isoformat(),
                    act.period.end.isoformat(),
                    act.header.contract.number,
                    act.header.contractor.name,
                    act.header.customer.name,
                    act.created_at.isoformat(),
                    act.model_dump_json(),
                ),
            )
        return act

    def get_act(self, act_id: str) -> KS2Act:
        with self._cursor() as cursor:
            row = cursor.execute("SELECT payload FROM acts WHERE id = ?", (act_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"Акт КС-2 {act_id} не найден")
        return KS2Act.model_validate_json(row["payload"])

    def get_acts(self, act_ids: list[str]) -> list[KS2Act]:
        """Возвращает акты в порядке переданных идентификаторов."""
        found = {}
        for act_id in dict.fromkeys(act_ids):
            found[act_id] = self.get_act(act_id)
        return [found[act_id] for act_id in dict.fromkeys(act_ids)]

    def list_acts(
        self,
        *,
        contract_number: str | None = None,
        period_from: date | None = None,
        period_to: date | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[KS2Act]:
        rows = self._list("acts", contract_number, period_from, period_to, limit, offset)
        return [KS2Act.model_validate_json(row["payload"]) for row in rows]

    def delete_act(self, act_id: str) -> None:
        self._delete("acts", act_id, f"Акт КС-2 {act_id} не найден")

    # ------------------------------------------------------------------
    # КС-3
    # ------------------------------------------------------------------

    def save_certificate(self, certificate: KS3Certificate) -> KS3Certificate:
        with self._cursor() as cursor:
            cursor.execute(
                """
                INSERT OR REPLACE INTO certificates (id, document_number, document_date, period_start,
                                                     period_end, contract_number, contractor, customer,
                                                     created_at, payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    certificate.id,
                    certificate.document_number,
                    certificate.document_date.isoformat(),
                    certificate.period.start.isoformat(),
                    certificate.period.end.isoformat(),
                    certificate.header.contract.number,
                    certificate.header.contractor.name,
                    certificate.header.customer.name,
                    certificate.created_at.isoformat(),
                    certificate.model_dump_json(),
                ),
            )
        return certificate

    def get_certificate(self, certificate_id: str) -> KS3Certificate:
        with self._cursor() as cursor:
            row = cursor.execute(
                "SELECT payload FROM certificates WHERE id = ?", (certificate_id,)
            ).fetchone()
        if row is None:
            raise NotFoundError(f"Справка КС-3 {certificate_id} не найдена")
        return KS3Certificate.model_validate_json(row["payload"])

    def list_certificates(
        self,
        *,
        contract_number: str | None = None,
        period_from: date | None = None,
        period_to: date | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[KS3Certificate]:
        rows = self._list("certificates", contract_number, period_from, period_to, limit, offset)
        return [KS3Certificate.model_validate_json(row["payload"]) for row in rows]

    def delete_certificate(self, certificate_id: str) -> None:
        self._delete("certificates", certificate_id, f"Справка КС-3 {certificate_id} не найдена")

    # ------------------------------------------------------------------

    def _list(
        self,
        table: str,
        contract_number: str | None,
        period_from: date | None,
        period_to: date | None,
        limit: int,
        offset: int,
    ) -> list[sqlite3.Row]:
        conditions: list[str] = []
        params: list[object] = []
        if contract_number:
            conditions.append("contract_number = ?")
            params.append(contract_number)
        if period_from:
            conditions.append("period_end >= ?")
            params.append(period_from.isoformat())
        if period_to:
            conditions.append("period_start <= ?")
            params.append(period_to.isoformat())
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.extend([limit, offset])
        query = (
            f"SELECT payload FROM {table} {where} "
            "ORDER BY document_date DESC, created_at DESC LIMIT ? OFFSET ?"
        )
        with self._cursor() as cursor:
            return cursor.execute(query, params).fetchall()

    def _delete(self, table: str, document_id: str, message: str) -> None:
        with self._cursor() as cursor:
            cursor.execute(f"DELETE FROM {table} WHERE id = ?", (document_id,))
            if cursor.rowcount == 0:
                raise NotFoundError(message)
