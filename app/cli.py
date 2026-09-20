"""Резервное копирование и перенос документов между хранилищами.

    python -m app.cli dump --output backup.json
    python -m app.cli load --input backup.json --database-url postgresql://...

Связка двух команд переносит документы, например из локального SQLite
в постоянную базу PostgreSQL после развёртывания.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from app.config import Settings, get_settings
from app.domain.models import KS2Act, KS3Certificate
from app.storage.base import DocumentRepository
from app.storage.factory import create_repository

FORMAT = "ks-documents/1"
PAGE_SIZE = 200


def _settings(args: argparse.Namespace) -> Settings:
    settings = get_settings()
    if args.database_path:
        settings = replace(settings, database_path=args.database_path, database_url="")
    if args.database_url:
        settings = replace(settings, database_url=args.database_url)
    return settings


def _all_acts(repository: DocumentRepository) -> Iterator[KS2Act]:
    offset = 0
    while page := repository.list_acts(limit=PAGE_SIZE, offset=offset):
        yield from page
        offset += len(page)


def _all_certificates(repository: DocumentRepository) -> Iterator[KS3Certificate]:
    offset = 0
    while page := repository.list_certificates(limit=PAGE_SIZE, offset=offset):
        yield from page
        offset += len(page)


def dump(args: argparse.Namespace) -> int:
    """Выгружает все документы в один JSON-файл."""
    repository = create_repository(_settings(args))
    try:
        payload = {
            "format": FORMAT,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "acts": [json.loads(act.model_dump_json()) for act in _all_acts(repository)],
            "certificates": [
                json.loads(certificate.model_dump_json())
                for certificate in _all_certificates(repository)
            ],
        }
    finally:
        repository.close()

    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(
            f"Выгружено: актов КС-2 — {len(payload['acts'])}, "
            f"справок КС-3 — {len(payload['certificates'])} → {args.output}"
        )
    else:
        print(text)
    return 0


def load(args: argparse.Namespace) -> int:
    """Загружает документы из файла выгрузки в хранилище."""
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    if payload.get("format") != FORMAT:
        print(f"Неизвестный формат файла: {payload.get('format')!r}", file=sys.stderr)
        return 1

    acts = [KS2Act.model_validate(item) for item in payload.get("acts", [])]
    certificates = [
        KS3Certificate.model_validate(item) for item in payload.get("certificates", [])
    ]

    repository = create_repository(_settings(args))
    try:
        for act in acts:
            repository.save_act(act)
        for certificate in certificates:
            repository.save_certificate(certificate)
    finally:
        repository.close()

    print(f"Загружено: актов КС-2 — {len(acts)}, справок КС-3 — {len(certificates)}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.cli",
        description="Резервное копирование документов КС-2 и КС-3",
    )
    parser.add_argument("--database-path", help="Файл SQLite вместо значения KS_DATABASE_PATH")
    parser.add_argument("--database-url", help="Подключение к PostgreSQL вместо KS_DATABASE_URL")

    commands = parser.add_subparsers(dest="command", required=True)

    dump_command = commands.add_parser("dump", help="выгрузить документы в JSON")
    dump_command.add_argument("--output", "-o", help="файл; без него вывод в stdout")
    dump_command.set_defaults(handler=dump)

    load_command = commands.add_parser("load", help="загрузить документы из JSON")
    load_command.add_argument("--input", "-i", required=True, help="файл выгрузки")
    load_command.set_defaults(handler=load)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
