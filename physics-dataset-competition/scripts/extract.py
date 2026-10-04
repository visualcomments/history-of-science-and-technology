#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""CLI извлечения: собрать записи из спецификации эксперта.

Использование:
  python scripts/extract.py --spec SPEC.json [--out RECORDS.jsonl] [--json]

Спецификацию готовит эксперт/агент (не LLM-автоматизация); см.
``docs/EXPERT-ASSIGNMENT.md``. Запись собирается детерминированно, права
выставляет ``rights.classifier``, хэш bronze обязателен. Перед записью JSONL
выполняются:
  * структурная проверка по ``configs/schema/record.schema.json``;
  * доменные проверки диапазонов/единиц/conditions.

При любой ошибке невалидные записи НЕ пишутся (код возврата 1).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parent.parent
SRC = MODULE_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from physics_ds.extract.record_builder import build_records, load_spec  # noqa: E402
from physics_ds.validation.checks import (  # noqa: E402
    check_record_domain,
    load_domain_config,
)


def cmd_extract(spec_path: str, out_path: str | None) -> int:
    try:
        spec = load_spec(spec_path)
    except (OSError, json.JSONDecodeError) as exc:
        print(
            json.dumps(
                {"error": f"не удалось прочитать спек: {exc}"}, ensure_ascii=False
            ),
            file=sys.stderr,
        )
        return 2

    records, errors = build_records(spec)

    domain_errors: list[str] = []
    for i, record in enumerate(records):
        config = load_domain_config(record["domain"])
        for err in check_record_domain(record, config):
            domain_errors.append(f"records[{i}]: {err}")

    all_errors = errors + domain_errors
    report = {
        "records": len(records),
        "errors": len(all_errors),
        "error_details": all_errors,
    }

    if all_errors:
        print(json.dumps(report, ensure_ascii=False), file=sys.stderr)
        return 1

    if out_path:
        p = Path(out_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="\n") as fh:
            for record in records:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        report["out"] = str(p)

    print(json.dumps(report, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Собрать записи датасета из JSON-спецификации эксперта."
    )
    ap.add_argument("--spec", required=True, help="JSON-спецификация извлечения.")
    ap.add_argument("--out", help="Куда записать JSONL (по умолчанию только отчёт).")
    ap.add_argument("--json", action="store_true", help="(зарезервировано) JSON-вывод.")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return cmd_extract(args.spec, args.out)


if __name__ == "__main__":
    raise SystemExit(main())
