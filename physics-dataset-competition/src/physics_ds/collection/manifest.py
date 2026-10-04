# SPDX-License-Identifier: GPL-3.0-or-later
"""Чтение/запись JSONL-манифеста отобранных кандидатов (stdlib).

Манифест — построчный JSON, по одному кандидату/артефакту на строку. Поля
описаны в :mod:`physics_ds.collection.openalex` и совместимы между сервисами:

    service, service_id, title, doi, year, oa_url, license, source_url,
    is_oa, domain, query, retrieved_at, provenance_service

``append``/``write`` только дополняют или перезаписывают переданные строки;
никаких секретов здесь не хранится.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

MANIFEST_FIELDS = [
    "service",
    "service_id",
    "title",
    "doi",
    "year",
    "oa_url",
    "license",
    "source_url",
    "is_oa",
    "domain",
    "query",
    "retrieved_at",
    "provenance_service",
]


def normalize(candidate: dict[str, Any]) -> dict[str, Any]:
    """Привести кандидата к каноническому набору полей (без выдумывания данных)."""
    out: dict[str, Any] = {}
    for field in MANIFEST_FIELDS:
        out[field] = candidate.get(field)
    # любые дополнительные безопасные поля сохраняем как есть
    for key, value in candidate.items():
        if key not in out:
            out[key] = value
    return out


def write(path: str | Path, rows: Iterable[dict[str, Any]]) -> int:
    """Записать манифест (перезапись). Возвращает число строк."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with open(p, "w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(normalize(row), ensure_ascii=False) + "\n")
            count += 1
    return count


def read(path: str | Path) -> list[dict[str, Any]]:
    """Прочитать манифест. Пустой/отсутствующий файл → []."""
    p = Path(path)
    if not p.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def append(path: str | Path, row: dict[str, Any]) -> None:
    """Дописать одну строку в манифест (append-only)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(normalize(row), ensure_ascii=False) + "\n")
