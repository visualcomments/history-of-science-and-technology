#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""CLI автозаполнения: собрать черновую спецификацию извлечения из манифеста.

Использование:
  python scripts/autofill.py --manifest FETCH.jsonl --bronze-dir DIR \\
      --domain AERO|STR|RADAR|CTRL --out SPEC.json \\
      [--target-records N] [--query TEXT] [--agent-role-id ID] [--retrieved-at ISO]

Что делает:
  * из строк манифеста со ``status=downloaded`` читает локальные файлы;
  * для текстовых форматов предлагает числа+единицы регуляркой (ПРЕДЛОЖЕНИЕ);
  * для бинарных (PDF и др.) не парсит содержимое и помечает запись как
    требующую проверки агентом;
  * собирает спецификацию, которую потребляет ``scripts/extract.py``.

Чего НЕ делает:
  * не выдумывает метаданные — копирует их только из манифеста;
  * не задаёт права — это делает ``rights.classifier`` при сборке записи;
  * не выводит секреты.

``--retrieved-at`` обязателен; как fallback допускается ``SOURCE_DATE_EPOCH``
(unix-время → ISO UTC). Фиксированное «1970-01-01» не подставляется.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# UTF-8 вывод: русский текст не должен падать при перенаправлении stdout/stderr
# на консоли с не-UTF-8 кодировкой (Windows cp1251 и т.п.).
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass

MODULE_ROOT = Path(__file__).resolve().parent.parent
SRC = MODULE_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from physics_ds.collection import manifest as manifest_mod  # noqa: E402
from physics_ds.extract.autofill import (  # noqa: E402
    build_spec,
    resolve_retrieved_at,
    summarize,
    write_spec,
)

DOMAINS = ("AERO", "STR", "RADAR", "CTRL")
DEFAULT_AGENT_ROLE_ID = "agent"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Собрать черновую спецификацию извлечения из bronze-манифеста."
    )
    ap.add_argument(
        "--manifest", required=True, help="JSONL-манифест загрузки (fetch-manifest)."
    )
    ap.add_argument(
        "--bronze-dir",
        default=None,
        help="Каталог со скачанными файлами (для поиска по имени, если path устарел).",
    )
    ap.add_argument("--domain", choices=DOMAINS, required=True, help="Домен датасета.")
    ap.add_argument("--out", required=True, help="Куда записать спецификацию JSON.")
    ap.add_argument(
        "--target-records",
        type=int,
        default=3,
        help="Желаемое число записей (0 = без ограничения).",
    )
    ap.add_argument(
        "--query", default=None, help="Поисковый запрос (сохраняется в спеке)."
    )
    ap.add_argument(
        "--agent-role-id",
        default=DEFAULT_AGENT_ROLE_ID,
        help="Роль/идентификатор агента для provenance.",
    )
    ap.add_argument(
        "--retrieved-at",
        default=None,
        help="Время получения в ISO-8601 (иначе — SOURCE_DATE_EPOCH).",
    )
    args = ap.parse_args(argv)

    try:
        retrieved_at = resolve_retrieved_at(args.retrieved_at)
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2

    rows = manifest_mod.read(args.manifest)
    if not rows:
        print(
            json.dumps(
                {"error": f"манифест пуст или не найден: {args.manifest}"},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2

    spec, statuses = build_spec(
        rows,
        domain=args.domain,
        agent_role_id=args.agent_role_id,
        retrieved_at=retrieved_at,
        bronze_dir=args.bronze_dir,
        query=args.query,
        target_records=args.target_records,
    )
    write_spec(args.out, spec)

    summary = summarize(statuses)
    report = {
        "command": "autofill",
        "domain": args.domain,
        "out": str(args.out),
        "records": len(spec["records"]),
        "target_records": args.target_records,
        "sources": summary["sources"],
        "proposed": summary["proposed"],
        "needs_agent_review": summary["needs_agent_review"],
        "skipped": summary["skipped"],
        "skipped_reasons": summary["skipped_reasons"],
        "note": "числа предложены регуляркой; эксперт обязан проверить каждое значение",
    }
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
