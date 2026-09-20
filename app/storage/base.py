"""Контракт хранилища документов КС-2 и КС-3."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from app.domain.models import KS2Act, KS3Certificate


class DocumentRepository(ABC):
    """Хранилище актов КС-2 и справок КС-3.

    Реализации: SQLite (файл на диске) и PostgreSQL (внешняя база).
    """

    # ------------------------------------------------------------------
    # КС-2
    # ------------------------------------------------------------------

    @abstractmethod
    def save_act(self, act: KS2Act) -> KS2Act:
        """Сохраняет акт, перезаписывая документ с тем же идентификатором."""

    @abstractmethod
    def get_act(self, act_id: str) -> KS2Act:
        """Возвращает акт или бросает NotFoundError."""

    @abstractmethod
    def list_acts(
        self,
        *,
        contract_number: str | None = None,
        period_from: date | None = None,
        period_to: date | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[KS2Act]:
        """Акты по фильтрам, свежие сверху."""

    @abstractmethod
    def delete_act(self, act_id: str) -> None:
        """Удаляет акт или бросает NotFoundError."""

    # ------------------------------------------------------------------
    # КС-3
    # ------------------------------------------------------------------

    @abstractmethod
    def save_certificate(self, certificate: KS3Certificate) -> KS3Certificate:
        """Сохраняет справку, перезаписывая документ с тем же идентификатором."""

    @abstractmethod
    def get_certificate(self, certificate_id: str) -> KS3Certificate:
        """Возвращает справку или бросает NotFoundError."""

    @abstractmethod
    def list_certificates(
        self,
        *,
        contract_number: str | None = None,
        period_from: date | None = None,
        period_to: date | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[KS3Certificate]:
        """Справки по фильтрам, свежие сверху."""

    @abstractmethod
    def delete_certificate(self, certificate_id: str) -> None:
        """Удаляет справку или бросает NotFoundError."""

    # ------------------------------------------------------------------

    def get_acts(self, act_ids: list[str]) -> list[KS2Act]:
        """Акты в порядке переданных идентификаторов, дубликаты отбрасываются."""
        unique_ids = list(dict.fromkeys(act_ids))
        return [self.get_act(act_id) for act_id in unique_ids]

    def close(self) -> None:
        """Освобождает ресурсы хранилища."""
