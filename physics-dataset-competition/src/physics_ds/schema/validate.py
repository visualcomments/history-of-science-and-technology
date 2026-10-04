#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Детерминированный валидатор записей по канонической схеме (DESIGN §4.2).

Только стандартная библиотека, без внешних зависимостей — может запускаться
шагом CI на сервере Kurator и в репозиториях курса.

Использование:
  python validate.py RECORDS.jsonl [--json] [--selftest]

Проверки (повторяют ``configs/schema/record.schema.json``):
  * обязательные поля верхнего уровня;
  * ``record_id``        — шаблон ``^[A-Z]{2,6}-[0-9A-F]{8,}$``;
  * ``schema_version``   — SemVer ``^\\d+\\.\\d+\\.\\d+$``;
  * ``domain``           — enum {AERO,STR,RADAR,CTRL};
  * ``source.*``         — обязательные поля и enum ``source_type``;
  * ``rights.*``         — обязательные поля, boolean-типы;
  * ``values[]``         — непустой массив, у элементов name/value/unit;
  * ``provenance.*``     — обязательные поля;
  * ``validation.*``     — обязательные поля и enum ``status``.

Коды возврата: 0 = ok, 1 = есть ошибки, 2 = невозможно проверить (нет файла).

``--selftest`` доказывает, что валидатор УМЕЕТ падать (инвариант I8: проверка,
которая не может упасть, ничего не проверяет): валидируется заведомо сломанная
запись, и код 0 возвращается только если ошибки действительно найдены.

Замена внешних зависимостей: в DESIGN §18.1 упомянут ``jsonschema``/``pydantic``;
здесь эквивалентные проверки реализованы на stdlib, чтобы CI не тянул тяжёлые
пакеты. Проверяется структурное ядро схемы, а не полный draft-2020-12.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

# Корень модуля: <repo>/physics-dataset-competition
MODULE_ROOT = Path(__file__).resolve().parents[3]
REPO_ROOT = MODULE_ROOT.parent
DEFAULT_SCHEMA = MODULE_ROOT / "configs" / "schema" / "record.schema.json"

RECORD_ID_RE = re.compile(r"^[A-Z]{2,6}-[0-9A-F]{8,}$")
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")

DOMAINS = {"AERO", "STR", "RADAR", "CTRL"}
SOURCE_TYPES = {"book", "article", "report", "dataset", "standard", "patent", "thesis"}
VALIDATION_STATUSES = {
    "unchecked",
    "in-review",
    "accepted",
    "rejected",
    "needs-expert",
}

REQUIRED_TOP = [
    "record_id",
    "schema_version",
    "domain",
    "source",
    "rights",
    "provenance",
    "values",
    "validation",
]
SOURCE_REQUIRED = ["title", "source_type", "year", "language", "url", "license"]
RIGHTS_REQUIRED = ["reusable", "redistributable", "basis"]
VALUE_REQUIRED = ["name", "value", "unit"]
PROVENANCE_REQUIRED = ["activity", "agent_role_id", "retrieved_at", "method", "sha256"]
VALIDATION_REQUIRED = ["status", "checked_by_role_id", "checked_at"]


def load_schema(path: Path | None = None) -> dict[str, Any]:
    """Загрузить JSON-схему; путь по умолчанию — относительно корня модуля."""
    p = Path(path) if path else DEFAULT_SCHEMA
    return json.loads(p.read_text(encoding="utf-8"))


def _is_obj(x: Any) -> bool:
    return isinstance(x, dict)


def _require_fields(
    obj: Any, field: str, required: list[str], errors: list[str]
) -> None:
    if not _is_obj(obj):
        errors.append(f"{field}: должен быть объектом")
        return
    for r in required:
        if r not in obj:
            errors.append(f"{field}: отсутствует обязательное поле '{r}'")


def validate_record(rec: Any, errors: list[str] | None = None) -> list[str]:
    """Проверить одну запись. Возвращает список ошибок (пусто = валидна)."""
    if errors is None:
        errors = []
    if not _is_obj(rec):
        errors.append("запись: должна быть JSON-объектом")
        return errors

    for r in REQUIRED_TOP:
        if r not in rec:
            errors.append(f"отсутствует обязательное поле '{r}'")

    rid = rec.get("record_id")
    if not isinstance(rid, str) or not RECORD_ID_RE.match(rid or ""):
        errors.append(
            f"record_id должен соответствовать ^[A-Z]{{2,6}}-[0-9A-F]{{8,}}$: {rid!r}"
        )

    sv = rec.get("schema_version")
    if not isinstance(sv, str) or not SEMVER_RE.match(sv or ""):
        errors.append(f"schema_version должен быть SemVer (MAJOR.MINOR.PATCH): {sv!r}")

    dom = rec.get("domain")
    if dom not in DOMAINS:
        errors.append(f"domain недопустим: {dom!r} (ожидается AERO/STR/RADAR/CTRL)")

    _require_fields(rec.get("source"), "source", SOURCE_REQUIRED, errors)
    src = rec.get("source")
    if _is_obj(src):
        st = src.get("source_type")
        if st not in SOURCE_TYPES:
            errors.append(f"source.source_type недопустим: {st!r}")
        if not isinstance(src.get("year"), int):
            errors.append("source.year должен быть целым числом")
        for k in ("title", "language", "url", "license"):
            if not isinstance(src.get(k), str) or not src.get(k):
                errors.append(f"source.{k} должен быть непустой строкой")

    _require_fields(rec.get("rights"), "rights", RIGHTS_REQUIRED, errors)
    rts = rec.get("rights")
    if _is_obj(rts):
        for k in ("reusable", "redistributable"):
            if not isinstance(rts.get(k), bool):
                errors.append(f"rights.{k} должен быть boolean")
        if not isinstance(rts.get("basis"), str) or not rts.get("basis"):
            errors.append("rights.basis должен быть непустой строкой")

    vals = rec.get("values")
    if not isinstance(vals, list) or len(vals) < 1:
        errors.append("values должен быть непустым массивом")
    else:
        for i, v in enumerate(vals):
            _require_fields(v, f"values[{i}]", VALUE_REQUIRED, errors)
            if _is_obj(v) and isinstance(v.get("value"), bool):
                errors.append(f"values[{i}].value не может быть boolean")

    _require_fields(rec.get("provenance"), "provenance", PROVENANCE_REQUIRED, errors)
    prov = rec.get("provenance")
    if _is_obj(prov):
        sha = prov.get("sha256")
        if not isinstance(sha, str) or not re.match(r"^[0-9a-f]{64}$", sha or ""):
            errors.append("provenance.sha256 должен быть hex-строкой из 64 символов")

    _require_fields(rec.get("validation"), "validation", VALIDATION_REQUIRED, errors)
    val = rec.get("validation")
    if _is_obj(val) and val.get("status") not in VALIDATION_STATUSES:
        errors.append(f"validation.status недопустим: {val.get('status')!r}")

    return errors


def validate_file(path: Path) -> tuple[int, int, list[dict[str, Any]]]:
    """Проверить JSONL-файл.

    Возвращает ``(records, errors_count, failed)``, где ``failed`` — список
    отчетов по строкам с ошибками.
    """
    records = 0
    errors_count = 0
    failed: list[dict[str, Any]] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        records += 1
        try:
            rec = json.loads(line)
        except json.JSONDecodeError as exc:
            errors_count += 1
            failed.append({"line": lineno, "errors": [f"JSON: {exc}"]})
            continue
        errs = validate_record(rec)
        if errs:
            errors_count += 1
            failed.append({"line": lineno, "id": rec.get("record_id"), "errors": errs})
    return records, errors_count, failed


def _selftest() -> int:
    """Доказать, что валидатор может упасть на сломанной записи (I8)."""
    broken = {
        "record_id": "bad-id",
        "schema_version": "1.0",
        "domain": "NOPE",
        "source": {"title": "t"},
        "rights": {"reusable": "yes", "redistributable": True},
        "provenance": {"activity": "collect", "sha256": "zz"},
        "values": [],
        "validation": {"status": "bogus"},
    }
    errs = validate_record(broken)
    ok = bool(errs)
    print(
        f"selftest: обнаружено ошибок={len(errs)} -> {'PASS' if ok else 'FAIL'}",
        file=sys.stderr if not ok else sys.stdout,
    )
    if not ok:
        print(
            "selftest ПРОВАЛЕН: валидатор не смог найти ни одной ошибки",
            file=sys.stderr,
        )
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Валидация записей физического датасета (DESIGN §4.2)"
    )
    ap.add_argument("records", nargs="?", help="JSONL-файл с записями")
    ap.add_argument("--schema", help="альтернативная JSON-схема")
    ap.add_argument("--json", action="store_true", help="машиночитаемая сводка")
    ap.add_argument(
        "--selftest",
        action="store_true",
        help="доказать, что валидатор умеет падать (I8)",
    )
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()

    if not args.records:
        ap.error("нужен файл записей (или используйте --selftest)")

    try:
        load_schema(Path(args.schema) if args.schema else None)
    except OSError as exc:
        print(f"ошибка: не удалось прочитать схему: {exc}", file=sys.stderr)
        return 2

    path = Path(args.records)
    if not path.is_file():
        print(f"ошибка: файл не найден: {path}", file=sys.stderr)
        return 2

    records, errors, failed = validate_file(path)
    summary = {
        "records": records,
        "ok": records - errors,
        "errors": errors,
        "failed_records": failed,
    }
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"записей={records} ok={records - errors} ошибок={errors}")
        for item in failed:
            ident = f" [{item.get('id')}]" if item.get("id") else ""
            print(f"  строка {item['line']}{ident}: " + "; ".join(item["errors"]))

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
