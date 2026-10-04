# SPDX-License-Identifier: GPL-3.0-or-later
"""Детерминированная выборка и проверка записей (stdlib-only).

Функции:
  * :func:`sample` — детерминированная выборка по seed (``random.Random(seed)``);
  * :func:`check_records` — структурная + доменная проверка, поиск дублей,
    подсчёт статусов.

Один и тот же вход + seed всегда дают одну и ту же выборку.
"""

from __future__ import annotations

import random
from collections import Counter
from typing import Any

from ..schema.validate import validate_record
from .checks import check_record_domain, load_domain_config


def sample(
    records: list[dict[str, Any]], rate: float, seed: int
) -> list[dict[str, Any]]:
    """Выбрать детерминированную подвыборку.

    ``rate`` ∈ [0, 1]. ``rate <= 0`` → пусто; ``rate >= 1`` → все записи
    (в исходном порядке). Иначе — ``k`` записей, где ``k = max(1, round(n*rate))``,
    выбранных ``random.Random(seed).sample`` и возвращённых в исходном порядке.
    """
    if rate <= 0:
        return []
    if rate >= 1:
        return list(records)
    n = len(records)
    if n == 0:
        return []
    k = max(1, round(n * rate))
    rng = random.Random(seed)
    chosen = set(rng.sample(range(n), k))
    return [rec for i, rec in enumerate(records) if i in chosen]


def check_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Проверить записи: структура, домены, дубли, статусы.

    Возвращает отчёт ``{counts, duplicates, errors, status_counts, ok}``.
    """
    errors: list[dict[str, Any]] = []
    seen: dict[str, int] = {}
    duplicates: list[str] = []
    status_counts: Counter[str] = Counter()

    for i, record in enumerate(records):
        rid = str(record.get("record_id") or "")
        if rid in seen:
            duplicates.append(rid)
            errors.append(
                {"index": i, "record_id": rid, "errors": ["дубликат record_id"]}
            )
        else:
            seen[rid] = i

        struct_errors = validate_record(record)
        if not struct_errors:
            try:
                config = load_domain_config(record["domain"])
                struct_errors = check_record_domain(record, config)
            except OSError:
                struct_errors = [f"нет конфига домена для {record.get('domain')!r}"]
        if struct_errors:
            errors.append({"index": i, "record_id": rid, "errors": struct_errors})

        status = str((record.get("validation") or {}).get("status", "missing"))
        status_counts[status] += 1

    return {
        "counts": {
            "total": len(records),
            "valid": len(records)
            - len({e["index"] for e in errors if "дубликат" not in str(e["errors"])}),
            "errors": len(errors),
            "duplicates": len(duplicates),
        },
        "duplicates": duplicates,
        "errors": errors,
        "status_counts": dict(sorted(status_counts.items())),
        "ok": len(errors) == 0,
    }
