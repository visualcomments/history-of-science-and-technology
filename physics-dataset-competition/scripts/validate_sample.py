#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""CLI выборочной проверки: детерминированная выборка + отчёт.

Использование:
  python scripts/validate_sample.py --records RECORDS.jsonl \\
      [--sample 0.0..1.0] [--seed 42] [--report FILE]

Коды возврата: 0 = чисто; 1 = есть ошибки валидации; 2 = вход недоступен.
Выборка детерминирована: при одинаковых ``--records``/``--sample``/``--seed``
отчёт воспроизводится.
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

from physics_ds.validation.sampling import check_records, sample  # noqa: E402


def _read_jsonl(path: Path) -> tuple[list[dict], list[str]]:
    records: list[dict] = []
    errors: list[str] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            errors.append(f"строка {lineno}: JSON: {exc}")
    return records, errors


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Выборочная проверка записей (структура + домен + дубли)."
    )
    ap.add_argument("--records", required=True, help="JSONL-файл с записями.")
    ap.add_argument("--sample", type=float, default=1.0, help="Доля выборки 0..1.")
    ap.add_argument(
        "--seed", type=int, default=42, help="Seed детерминированной выборки."
    )
    ap.add_argument("--report", help="Куда записать JSON-отчёт.")
    args = ap.parse_args(argv)

    path = Path(args.records)
    if not path.is_file():
        print(
            json.dumps({"error": f"файл не найден: {path}"}, ensure_ascii=False),
            file=sys.stderr,
        )
        return 2

    records, parse_errors = _read_jsonl(path)
    selected = sample(records, args.sample, args.seed)
    report = check_records(selected)
    report["input"] = {
        "records": str(path),
        "total": len(records),
        "sample": args.sample,
        "seed": args.seed,
        "selected": len(selected),
    }
    report["parse_errors"] = parse_errors
    if parse_errors:
        report["ok"] = False

    if args.report:
        rp = Path(args.report)
        rp.parent.mkdir(parents=True, exist_ok=True)
        rp.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
