"""Хранилище документов КС-2/КС-3 на PostgreSQL.

Документ целиком лежит в колонке `payload` типа JSONB, а поля, по которым
идёт поиск, продублированы обычными колонками. Подходит для развёртываний,
где файловая система эфемерна (Render, Fly без тома, Kubernetes).
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from app.domain.errors import NotFoundError
from app.domain.models import KS2Act, KS3Certificate
from app.storage.base import DocumentRepository

SCHEMA = """
CREATE TABLE IF NOT EXISTS acts (
    id              text PRIMARY KEY,
    document_number text NOT NULL,
    document_date   date NOT NULL,
    period_start    date NOT NULL,
    period_end      date NOT NULL,
    contract_number text NOT NULL,
    contractor      text NOT NULL,
    customer        text NOT NULL,
    created_at      timestamptz NOT NULL,
    payload         jsonb NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_acts_contract ON acts (contract_number);
CREATE INDEX IF NOT EXISTS idx_acts_period ON acts (period_end);

CREATE TABLE IF NOT EXISTS certificates (
    id              text PRIMARY KEY,
    document_number text NOT NULL,
    document_date   date NOT NULL,
    period_start    date NOT NULL,
    period_end      date NOT NULL,
    contract_number text NOT NULL,
    contractor      text NOT NULL,
    customer        text NOT NULL,
    created_at      timestamptz NOT NULL,
    payload         jsonb NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_certificates_contract ON certificates (contract_number);
CREATE INDEX IF NOT EXISTS idx_certificates_period ON certificates (period_end);
"""

UPSERT = """
INSERT INTO {table} (id, document_number, document_date, period_start, period_end,
                     contract_number, contractor, customer, created_at, payload)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (id) DO UPDATE SET
    document_number = EXCLUDED.document_number,
    document_date   = EXCLUDED.document_date,
    period_start    = EXCLUDED.period_start,
    period_end      = EXCLUDED.period_end,
    contract_number = EXCLUDED.contract_number,
    contractor      = EXCLUDED.contractor,
    customer        = EXCLUDED.customer,
    created_at      = EXCLUDED.created_at,
    payload         = EXCLUDED.payload
"""


def normalize_dsn(url: str) -> str:
    """Render и Heroku выдают строку со схемой postgres://, psycopg ждёт postgresql://."""
    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://") :]
    return url


class PostgresRepository(DocumentRepository):
    """Документы во внешней базе PostgreSQL."""

    def __init__(self, dsn: str, *, min_size: int = 1, max_size: int = 5) -> None:
        self.pool = ConnectionPool(
            normalize_dsn(dsn),
            min_size=min_size,
            max_size=max_size,
            kwargs={"row_factory": dict_row},
            open=True,
        )
        with self.pool.connection() as connection:
            connection.execute(SCHEMA)

    def close(self) -> None:
        self.pool.close()

    # ------------------------------------------------------------------
    # КС-2
    # ------------------------------------------------------------------

    def save_act(self, act: KS2Act) -> KS2Act:
        self._save("acts", act)
        return act

    def get_act(self, act_id: str) -> KS2Act:
        payload = self._get("acts", act_id)
        if payload is None:
            raise NotFoundError(f"Акт КС-2 {act_id} не найден")
        return KS2Act.model_validate(payload)

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
        return [KS2Act.model_validate(row["payload"]) for row in rows]

    def delete_act(self, act_id: str) -> None:
        self._delete("acts", act_id, f"Акт КС-2 {act_id} не найден")

    # ------------------------------------------------------------------
    # КС-3
    # ------------------------------------------------------------------

    def save_certificate(self, certificate: KS3Certificate) -> KS3Certificate:
        self._save("certificates", certificate)
        return certificate

    def get_certificate(self, certificate_id: str) -> KS3Certificate:
        payload = self._get("certificates", certificate_id)
        if payload is None:
            raise NotFoundError(f"Справка КС-3 {certificate_id} не найдена")
        return KS3Certificate.model_validate(payload)

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
        return [KS3Certificate.model_validate(row["payload"]) for row in rows]

    def delete_certificate(self, certificate_id: str) -> None:
        self._delete("certificates", certificate_id, f"Справка КС-3 {certificate_id} не найдена")

    # ------------------------------------------------------------------

    def _save(self, table: str, document: KS2Act | KS3Certificate) -> None:
        payload = json.loads(document.model_dump_json())
        with self.pool.connection() as connection:
            connection.execute(
                UPSERT.format(table=table),
                (
                    document.id,
                    document.document_number,
                    document.document_date,
                    document.period.start,
                    document.period.end,
                    document.header.contract.number,
                    document.header.contractor.name,
                    document.header.customer.name,
                    document.created_at,
                    Jsonb(payload),
                ),
            )

    def _get(self, table: str, document_id: str) -> dict[str, Any] | None:
        with self.pool.connection() as connection:
            row = connection.execute(
                f"SELECT payload FROM {table} WHERE id = %s", (document_id,)
            ).fetchone()
        return row["payload"] if row else None

    def _list(
        self,
        table: str,
        contract_number: str | None,
        period_from: date | None,
        period_to: date | None,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        conditions: list[str] = []
        params: list[object] = []
        if contract_number:
            conditions.append("contract_number = %s")
            params.append(contract_number)
        if period_from:
            conditions.append("period_end >= %s")
            params.append(period_from)
        if period_to:
            conditions.append("period_start <= %s")
            params.append(period_to)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.extend([limit, offset])
        query = (
            f"SELECT payload FROM {table} {where} "
            "ORDER BY document_date DESC, created_at DESC LIMIT %s OFFSET %s"
        )
        with self.pool.connection() as connection:
            return connection.execute(query, params).fetchall()

    def _delete(self, table: str, document_id: str, message: str) -> None:
        with self.pool.connection() as connection:
            cursor = connection.execute(f"DELETE FROM {table} WHERE id = %s", (document_id,))
            if cursor.rowcount == 0:
                raise NotFoundError(message)
