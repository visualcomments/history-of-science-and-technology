#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""CLI коррекции: создать НОВУЮ запись-исправление, не перезаписывая историю.

Использование:
  python scripts/correct.py --record CORRECT.json --parent-record-id OLD-ID \\
      [--out RECORDS.jsonl] [--records EXISTING.jsonl]

Правила (DESIGN §4.4 — неизменяемость):
  * новый ``record_id`` генерируется детерминированно от содержимого;
  * в ``provenance.parent_record_id`` указывается исправляемая запись;
  * исходная запись НЕ изменяется и НЕ перезаписывается;
  * запись валидируется (структура + домен) ДО добавления в JSONL.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parent.parent
SRC = MODULE_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from physics_ds.schema.validate import DOMAINS, RECORD_ID_RE, validate_record  # noqa: E402
from physics_ds.validation.checks import (  # noqa: E402
    check_record_domain,
    load_domain_config,
)

SCHEMA_VERSION = "1.0.0"


def _existing_ids(records_path: str | None) -> set[str]:
    if not records_path:
        return set()
    p = Path(records_path)
    if not p.is_file():
        return set()
    ids: set[str] = set()
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            ids.add(str(json.loads(line).get("record_id")))
    return ids


def make_corrected(
    correct: dict,
    parent_record_id: str,
    *,
    taken: set[str] | None = None,
) -> dict:
    """Построить запись-исправление с новым id и parent_record_id."""
    if not parent_record_id or not RECORD_ID_RE.match(parent_record_id):
        raise ValueError(f"parent-record-id недопустим: {parent_record_id!r}")

    domain = str(correct.get("domain") or "")
    if domain not in DOMAINS:
        raise ValueError(f"domain недопустим: {domain!r}")

    canonical = json.dumps(correct, ensure_ascii=False, sort_keys=True)
    base = f"{domain}|{parent_record_id}|{canonical}".encode("utf-8")
    counter = 0
    taken = taken or set()
    while True:
        digest = hashlib.sha256(base + f"|{counter}".encode("utf-8")).hexdigest()
        new_id = f"{domain}-{digest[:10].upper()}"
        if new_id not in taken and new_id != parent_record_id:
            break
        counter += 1

    record = dict(correct)
    record["record_id"] = new_id
    record.setdefault("schema_version", SCHEMA_VERSION)
    provenance = dict(record.get("provenance") or {})
    provenance["parent_record_id"] = parent_record_id
    record["provenance"] = provenance
    return record


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Создать запись-исправление (append-only, без перезаписи истории)."
    )
    ap.add_argument("--record", required=True, help="JSON корректной записи.")
    ap.add_argument("--parent-record-id", required=True, help="ID исправляемой записи.")
    ap.add_argument("--out", help="JSONL-файл, куда ДОПИСАТЬ запись.")
    ap.add_argument("--records", help="Существующий JSONL (для проверки коллизий id).")
    args = ap.parse_args(argv)

    try:
        correct = json.loads(Path(args.record).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(
            json.dumps(
                {"error": f"не удалось прочитать запись: {exc}"}, ensure_ascii=False
            ),
            file=sys.stderr,
        )
        return 2

    try:
        record = make_corrected(
            correct, args.parent_record_id, taken=_existing_ids(args.records)
        )
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2

    errors = validate_record(record)
    try:
        errors.extend(check_record_domain(record, load_domain_config(record["domain"])))
    except OSError as exc:
        errors.append(f"нет конфига домена: {exc}")

    if errors:
        print(json.dumps({"errors": errors}, ensure_ascii=False), file=sys.stderr)
        return 1

    if args.out:
        p = Path(args.out)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(
        json.dumps(
            {
                "record_id": record["record_id"],
                "parent_record_id": args.parent_record_id,
                "out": args.out,
                "appended": bool(args.out),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
