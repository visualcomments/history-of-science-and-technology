# SPDX-License-Identifier: GPL-3.0-or-later
"""Сборка записей из спецификации эксперта (stdlib-only, детерминировано).

Спецификация (JSON), которую готовит эксперт/агент::

    {
      "domain": "AERO",
      "source": {                       # метаданные источника (обязательны)
        "title": "...", "source_type": "report", "year": 1935,
        "language": "en", "url": "https://...", "license": "public-domain",
        "publisher": "NASA", "authors": ["..."], "doi": "..."
      },
      "bronze": {"sha256": "<64hex>", "path": ".local/physics-bronze/xxx.pdf",
                 "service_id": "...", "provenance_service": "..."},
      "conditions": {"Re": 1, "Ma": 0.2, "alpha": 3.0},
      "values": [{"name": "Cx", "value": 0.02, "unit": "-"}],
      "provenance": {"activity": "digitize", "agent_role_id": "R03",
                     "retrieved_at": "2026-10-04T10:00:00Z",
                     "method": "manual", "tool_version": "1.0"},
      "validation": {"status": "unchecked", "checked_by_role_id": "R03",
                     "checked_at": "2026-10-04T10:00:00Z"}
    }

Ключевые инварианты:
  * ``record_id`` детерминирован от ``bronze.sha256`` + индекса: DOMAIN + ≥8 hex;
  * ``source.sha256``/``provenance.sha256`` берутся из ``bronze.sha256`` —
    метаданные не выдумываются;
  * права выставляет ``rights.classifier.classify``, а не спецификация;
  * запись проверяется структурным валидатором и доменными проверками.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from ..rights.classifier import classify
from ..schema.validate import DOMAINS, validate_record

SCHEMA_VERSION = "1.0.0"
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")

# Поля source, переносимые из спека в запись (без выдумывания).
_SOURCE_FIELDS = (
    "title",
    "authors",
    "publisher",
    "year",
    "source_type",
    "language",
    "url",
    "doi",
    "license",
    "archive_location",
)


def load_spec(path: str | Path) -> dict[str, Any]:
    """Прочитать JSON-спецификацию извлечения."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def deterministic_record_id(
    domain: str, bronze_sha256: str, index: int, *, taken: set[str] | None = None
) -> str:
    """Детерминированный ``DOMAIN-<>=8 hex>`` из sha256 bronze и индекса.

    При коллизии (маловероятной) детерминированно увеличиваем счётчик.
    """
    base = f"{domain}|{bronze_sha256}|{index}".encode("utf-8")
    counter = 0
    while True:
        digest = hashlib.sha256(base + f"|{counter}".encode("utf-8")).hexdigest()
        record_id = f"{domain}-{digest[:10].upper()}"
        if taken is None or record_id not in taken:
            return record_id
        counter += 1


def _build_source(
    spec_source: dict[str, Any], rights: dict[str, Any]
) -> dict[str, Any]:
    source: dict[str, Any] = {}
    for field in _SOURCE_FIELDS:
        if field in spec_source and spec_source[field] is not None:
            source[field] = spec_source[field]
    if "copyright_status" in spec_source:
        source["copyright_status"] = spec_source["copyright_status"]
    else:
        source["copyright_status"] = rights["copyright_status"]
    return source


def _provenance(spec: dict[str, Any], bronze_sha256: str) -> dict[str, Any]:
    prov_spec = dict(spec.get("provenance") or {})
    provenance = {
        "activity": prov_spec.get("activity", "digitize"),
        "agent_role_id": prov_spec.get("agent_role_id", ""),
        "retrieved_at": prov_spec.get("retrieved_at", ""),
        "method": prov_spec.get("method", "manual"),
        "tool_version": prov_spec.get("tool_version", ""),
        "sha256": bronze_sha256,
    }
    if prov_spec.get("parent_record_id"):
        provenance["parent_record_id"] = prov_spec["parent_record_id"]
    if prov_spec.get("review_chain"):
        provenance["review_chain"] = prov_spec["review_chain"]
    return provenance


def build_record(
    spec: dict[str, Any],
    *,
    index: int = 0,
    taken: set[str] | None = None,
) -> dict[str, Any]:
    """Собрать одну запись из спека. Не валидирует (см. :func:`build_records`)."""
    domain = str(spec.get("domain") or "")
    if domain not in DOMAINS:
        raise ValueError(f"domain недопустим: {domain!r}")

    source_spec = dict(spec.get("source") or {})
    bronze = dict(spec.get("bronze") or {})
    bronze_sha = str(bronze.get("sha256") or "")
    if not HEX64_RE.match(bronze_sha):
        raise ValueError(
            "bronze.sha256 обязателен и должен быть hex-строкой из 64 символов"
        )

    decisions = classify(source_spec)
    record_id = deterministic_record_id(domain, bronze_sha, index, taken=taken)

    validation_spec = dict(spec.get("validation") or {})
    record: dict[str, Any] = {
        "record_id": record_id,
        "schema_version": SCHEMA_VERSION,
        "domain": domain,
        "source": _build_source(source_spec, decisions),
        "rights": {
            "reusable": decisions["reusable"],
            "redistributable": decisions["redistributable"],
            "basis": decisions["basis"],
        },
        "conditions": dict(spec.get("conditions") or {}),
        "values": list(spec.get("values") or []),
        "provenance": _provenance(spec, bronze_sha),
        "validation": {
            "status": validation_spec.get("status", "unchecked"),
            "checked_by_role_id": validation_spec.get(
                "checked_by_role_id",
                (spec.get("provenance") or {}).get("agent_role_id", ""),
            ),
            "checked_at": validation_spec.get(
                "checked_at", (spec.get("provenance") or {}).get("retrieved_at", "")
            ),
        },
    }
    for optional in ("subdomain", "period"):
        if spec.get(optional):
            record[optional] = spec[optional]
    if validation_spec.get("notes"):
        record["validation"]["notes"] = validation_spec["notes"]
    return record


def build_records(spec: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    """Собрать и проверить записи из спека.

    Спек может быть одним объектом или содержать ``"records": [...]``.
    Возвращает ``(valid_records, errors)``; при ошибках валидные записи всё
    равно возвращаются, но вызывающий код не должен их писать.
    """
    raw_specs = spec.get("records")
    specs: list[dict[str, Any]] = raw_specs if isinstance(raw_specs, list) else [spec]
    records: list[dict[str, Any]] = []
    errors: list[str] = []
    taken: set[str] = set()

    for index, entry in enumerate(specs):
        merged = dict(spec)
        merged.pop("records", None)
        merged.update(entry)
        try:
            record = build_record(merged, index=index, taken=taken)
        except ValueError as exc:
            errors.append(f"records[{index}]: {exc}")
            continue
        struct_errors = validate_record(record)
        if struct_errors:
            errors.extend(f"records[{index}]: {e}" for e in struct_errors)
            continue
        records.append(record)
        taken.add(record["record_id"])
    return records, errors
