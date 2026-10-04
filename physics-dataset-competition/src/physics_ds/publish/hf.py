#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Публикация записей в Hugging Face Hub через pull request.

CLI:
  python src/physics_ds/publish/hf.py --records RECORDS.jsonl \\
      [--repo-id chaotic-good-project/physics-experiment-records] \\
      [--revision expert/<slug>] [--title T] [--description D] [--dry-run]

Инварианты безопасности (DESIGN §7, §8):
  * публикуются ТОЛЬКО записи с ``rights.redistributable is True``;
  * схема и домены проверяются ДО любого сетевого вызова;
  * токен читается из ``HF_TOKEN`` и НИКОГДА не печатается/не логируется;
  * ``--dry-run`` не делает сети и печатает JSON-план (число записей, SHA256,
    целевая ревизия, пути);
  * ``huggingface_hub`` импортируется лениво только в не-dry-run ветке.

Опциональная зависимость — см. ``docs/requirements-publish.txt``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

# Самодостаточность CLI.
MODULE_ROOT = Path(__file__).resolve().parents[3]
SRC = MODULE_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from physics_ds.schema.validate import validate_record  # noqa: E402
from physics_ds.validation.checks import (  # noqa: E402
    check_record_domain,
    load_domain_config,
)

DEFAULT_REPO_ID = "chaotic-good-project/physics-experiment-records"
SLUG_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def _read_records(path: Path) -> list[dict]:
    records: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def validate_for_publish(records: list[dict]) -> list[str]:
    """Проверить схему, домены и ``rights.redistributable``. Возвращает ошибки."""
    errors: list[str] = []
    for i, record in enumerate(records):
        rid = record.get("record_id")
        for err in validate_record(record):
            errors.append(f"[{rid}] {err}")
        try:
            config = load_domain_config(record["domain"])
            for err in check_record_domain(record, config):
                errors.append(f"[{rid}] {err}")
        except OSError:
            errors.append(f"[{rid}] нет конфига домена {record.get('domain')!r}")
        rights = record.get("rights") or {}
        if rights.get("redistributable") is not True:
            errors.append(
                f"[{rid}] rights.redistributable is not True — публиковать запрещено"
            )
    return errors


def _slug_from_revision(revision: str) -> str:
    slug = revision.split("/", 1)[-1]
    return slug or "submission"


def build_plan(
    records: list[dict],
    *,
    repo_id: str,
    revision: str,
    path_in_repo: str,
) -> dict:
    """Построить JSON-план публикации (без сети)."""
    payload = "\n".join(
        json.dumps(r, ensure_ascii=False, sort_keys=True) for r in records
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return {
        "repo_id": repo_id,
        "revision": revision,
        "records": len(records),
        "sha256": digest,
        "path_in_repo": path_in_repo,
        "files": [path_in_repo],
        "dry_run": True,
    }


def _publish(
    records: list[dict],
    *,
    repo_id: str,
    revision: str,
    path_in_repo: str,
    title: str,
    description: str,
) -> dict:
    """Выполнить реальный PR в Hub. Импорт huggingface_hub — лениво, здесь."""
    token = os.environ.get("HF_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "не задан HF_TOKEN (секрет берётся только из окружения, в файлы не пишется)"
        )

    try:
        from huggingface_hub import CommitOperationAdd, HfApi  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - зависит от окружения
        raise RuntimeError(
            "huggingface_hub не установлен; см. docs/requirements-publish.txt"
        ) from exc

    content = (
        "\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True) for r in records)
        + "\n"
    )
    message = title or f"Экспертная запись: {path_in_repo}"
    if description:
        message = f"{message}\n\n{description}"

    api = HfApi(token=token)
    api.create_commit(
        repo_id=repo_id,
        repo_type="dataset",
        revision=revision,
        create_pr=True,
        commit_message=message,
        operations=[
            CommitOperationAdd(
                path_in_repo=path_in_repo,
                path_or_fileobj=content.encode("utf-8"),
            )
        ],
    )
    return {
        "repo_id": repo_id,
        "revision": revision,
        "records": len(records),
        "path_in_repo": path_in_repo,
        "dry_run": False,
        "note": "PR создан; URL ревизии смотрите в интерфейсе Hub",
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Публикация записей в HF Hub через PR (по умолчанию dry-run)."
    )
    ap.add_argument("--records", required=True, help="JSONL-файл с записями.")
    ap.add_argument(
        "--repo-id", default=DEFAULT_REPO_ID, help="Целевой HF-репозиторий."
    )
    ap.add_argument(
        "--revision", default="expert/submission", help="Целевая ветка/ревизия."
    )
    ap.add_argument("--title", default="", help="Заголовок PR.")
    ap.add_argument("--description", default="", help="Описание PR.")
    ap.add_argument("--dry-run", action="store_true", help="Только план, без сети.")
    args = ap.parse_args(argv)

    path = Path(args.records)
    if not path.is_file():
        print(
            json.dumps({"error": f"файл не найден: {path}"}, ensure_ascii=False),
            file=sys.stderr,
        )
        return 2

    try:
        records = _read_records(path)
    except json.JSONDecodeError as exc:
        print(
            json.dumps({"error": f"JSON: {exc}"}, ensure_ascii=False), file=sys.stderr
        )
        return 2

    errors = validate_for_publish(records)
    if errors:
        print(json.dumps({"errors": errors}, ensure_ascii=False), file=sys.stderr)
        return 1
    if not records:
        print(json.dumps({"error": "нет записей"}, ensure_ascii=False), file=sys.stderr)
        return 1

    slug = _slug_from_revision(args.revision)
    if not SLUG_RE.match(slug):
        print(
            json.dumps(
                {"error": f"недопустимый slug ревизии: {slug!r}"}, ensure_ascii=False
            ),
            file=sys.stderr,
        )
        return 2
    path_in_repo = f"submissions/{slug}/records.jsonl"

    plan = build_plan(
        records,
        repo_id=args.repo_id,
        revision=args.revision,
        path_in_repo=path_in_repo,
    )

    if args.dry_run:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0

    try:
        result = _publish(
            records,
            repo_id=args.repo_id,
            revision=args.revision,
            path_in_repo=path_in_repo,
            title=args.title,
            description=args.description,
        )
    except RuntimeError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
