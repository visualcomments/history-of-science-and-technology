#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""CLI сбора: поиск по официальным API и право-гейтированная загрузка.

Команды:
  search  — только метаданные из OpenAlex/arXiv/Crossref в JSONL-манифест;
  fetch   — скачать разрешённые OA-источники ЛОКАЛЬНО по манифесту.

Использование:
  python scripts/collect.py search --service openalex|arxiv|crossref|all \\
      --domain AERO|STR|RADAR|CTRL --query TEXT --limit 1..20 --out FILE
  python scripts/collect.py fetch --manifest FILE --out-dir DIR [--max-items N]

Границы (DESIGN §5.3, §8):
  * search — metadata-only, ничего не скачивает;
  * fetch — только ``redistributable=True``, только https, только allow-list OA;
  * скачанные байты — в локальную директорию (рекомендуется
    ``.local/physics-bronze/``), НИКОГДА в отслеживаемые пути git;
  * секреты (``*_MAILTO``, токены) не печатаются и не логируются.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Самодостаточность: добавляем src/ на sys.path.
MODULE_ROOT = Path(__file__).resolve().parent.parent
SRC = MODULE_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from physics_ds.collection import arxiv, crossref, manifest, openalex  # noqa: E402
from physics_ds.collection.download import (  # noqa: E402
    fetch_candidate,
    write_fetch_manifest,
)

DOMAINS = ("AERO", "STR", "RADAR", "CTRL")
SERVICES = ("openalex", "arxiv", "crossref", "all")
DEFAULT_OUT = ".local/physics-bronze/candidates.jsonl"


def _run_search(service: str, domain: str, query: str, limit: int) -> list[dict]:
    if service == "openalex":
        return openalex.search(query, domain=domain, limit=limit)
    if service == "arxiv":
        return arxiv.search(query, domain=domain, limit=limit)
    if service == "crossref":
        return crossref.search(query, domain=domain, limit=limit)
    if service == "all":
        merged: list[dict] = []
        for fn in (
            openalex.search(query, domain=domain, limit=limit),
            arxiv.search(query, domain=domain, limit=limit),
            crossref.search(query, domain=domain, limit=limit),
        ):
            merged.extend(fn)
        return merged[:limit]
    raise ValueError(f"неизвестный сервис: {service!r}")


def cmd_search(args: argparse.Namespace) -> int:
    try:
        rows = _run_search(args.service, args.domain, args.query, args.limit)
    except Exception as exc:  # сеть/парсинг — сообщение без секретов
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    count = manifest.write(args.out, rows)
    summary = {
        "command": "search",
        "service": args.service,
        "domain": args.domain,
        "query": args.query,
        "candidates": count,
        "out": str(args.out),
        "note": "metadata-only; загрузка — только командой fetch",
    }
    print(json.dumps(summary, ensure_ascii=False))
    return 0


def cmd_fetch(args: argparse.Namespace) -> int:
    rows = manifest.read(args.manifest)
    if not rows:
        print(
            json.dumps(
                {"error": f"манифест пуст или не найден: {args.manifest}"},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2

    selected = rows[: args.max_items] if args.max_items > 0 else rows
    outcomes = [fetch_candidate(row, out_dir=args.out_dir) for row in selected]
    manifest_path = Path(args.out_dir) / "fetch-manifest.jsonl"
    write_fetch_manifest(manifest_path, outcomes)

    downloaded = [o for o in outcomes if o.status == "downloaded"]
    skipped = [o for o in outcomes if o.status == "skipped"]
    report = {
        "command": "fetch",
        "requested": len(selected),
        "downloaded": len(downloaded),
        "skipped": len(skipped),
        "out_dir": str(args.out_dir),
        "manifest": str(manifest_path),
        "outcomes": [o.to_dict() for o in outcomes],
    }
    print(json.dumps(report, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Сбор источников: поиск по OpenAlex/arXiv/Crossref и загрузка OA."
    )
    sub = ap.add_subparsers(dest="command", required=True)

    ps = sub.add_parser("search", help="Поиск метаданных (ничего не скачивает).")
    ps.add_argument("--service", choices=SERVICES, required=True, help="API-сервис.")
    ps.add_argument("--domain", choices=DOMAINS, required=True, help="Домен датасета.")
    ps.add_argument("--query", required=True, help="Поисковый запрос.")
    ps.add_argument("--limit", type=int, default=10, help="Число кандидатов (1..20).")
    ps.add_argument("--out", default=DEFAULT_OUT, help="JSONL-манифест для записи.")
    ps.set_defaults(func=cmd_search)

    pf = sub.add_parser(
        "fetch", help="Загрузить разрешённые OA-источники ЛОКАЛЬНО (вне git)."
    )
    pf.add_argument("--manifest", required=True, help="JSONL-манифест кандидатов.")
    pf.add_argument(
        "--out-dir",
        required=True,
        help="Локальная директория (напр. .local/physics-bronze/).",
    )
    pf.add_argument(
        "--max-items",
        type=int,
        default=0,
        help="Обработать не более N строк (0 = все).",
    )
    pf.set_defaults(func=cmd_fetch)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "search" and not (1 <= args.limit <= 20):
        print(
            json.dumps(
                {"error": "--limit должен быть в диапазоне 1..20"}, ensure_ascii=False
            ),
            file=sys.stderr,
        )
        return 2
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
