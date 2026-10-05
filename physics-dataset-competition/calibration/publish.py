#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Публикация цепочки калибровочной сессии в отдельный HF-dataset.

Датасет: **``top-papers/physics-agent-calibrations``** — хранит
*цепочки сессий калибровки* (task → agent_answer → expert_review → correction →
… → final), а не финальные записи эксперимента (для них отдельный репозиторий
``physics-experiment-records``).

CLI::

  python calibration/publish.py --session-file SESSION.jsonl \\
      [--repo-id top-papers/physics-agent-calibrations] \\
      [--revision expert/<slug>] [--title T] [--description D] [--dry-run]

Инварианты безопасности (по образцу ``physics_ds.publish.hf``):
  * вход — уже готовый публикуемый JSONL (результат ``calibration_session.py
    export``); publisher повторно очищает выдержки и локальные пути;
  * ``huggingface_hub`` импортируется лениво только в не-dry-run ветке;
  * токен читается только из ``HF_TOKEN`` и НИКОГДА не печатается/не логируется;
  * ``--dry-run`` не делает сети и печатает JSON-план;
  * реальный PR — ``create_pr=True`` (merge не выполняется).

Коды возврата: ``0`` — успех, ``1`` — невалидные данные, ``2`` — нельзя
выполнить (нет файла/токена/зависимости).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parent
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from session import export_publishable, validate_session  # type: ignore[import-not-found]  # noqa: E402

DEFAULT_REPO_ID = "top-papers/physics-agent-calibrations"
SLUG_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def _read_events(path: Path) -> list[dict]:
    events: list[dict] = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if line.strip():
            events.append(json.loads(line))
    return events


def build_plan(
    events: list[dict], *, repo_id: str, revision: str, path_in_repo: str
) -> dict:
    """Построить JSON-план публикации (без сети)."""
    payload = "\n".join(
        json.dumps(e, ensure_ascii=False, sort_keys=True) for e in events
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return {
        "repo_id": repo_id,
        "revision": revision,
        "events": len(events),
        "sha256": digest,
        "path_in_repo": path_in_repo,
        "files": [path_in_repo],
        "dry_run": True,
    }


def _publish(
    events: list[dict],
    *,
    repo_id: str,
    revision: str,
    path_in_repo: str,
    title: str,
    description: str,
) -> dict:
    """Реальный PR в Hub. Импорт huggingface_hub — лениво, здесь."""
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
        "\n".join(json.dumps(e, ensure_ascii=False, sort_keys=True) for e in events)
        + "\n"
    )
    message = title or f"Калибровочная сессия: {path_in_repo}"
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
        "events": len(events),
        "path_in_repo": path_in_repo,
        "dry_run": False,
        "note": "PR создан; URL ревизии смотрите в интерфейсе Hub",
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Публикация цепочки калибровочной сессии в HF Hub (по умолчанию dry-run)."
    )
    ap.add_argument(
        "--session-file", required=True, help="JSONL-сессия (после export)."
    )
    ap.add_argument("--repo-id", default=DEFAULT_REPO_ID, help="Целевой HF-датасет.")
    ap.add_argument(
        "--revision", default="expert/session", help="Целевая ветка/ревизия."
    )
    ap.add_argument("--title", default="", help="Заголовок PR.")
    ap.add_argument("--description", default="", help="Описание PR.")
    ap.add_argument("--dry-run", action="store_true", help="Только план, без сети.")
    args = ap.parse_args(argv)

    path = Path(args.session_file)
    if not path.is_file():
        print(
            json.dumps({"error": f"файл не найден: {path}"}, ensure_ascii=False),
            file=sys.stderr,
        )
        return 2
    try:
        events = _read_events(path)
    except json.JSONDecodeError as exc:
        print(
            json.dumps({"error": f"JSON: {exc}"}, ensure_ascii=False), file=sys.stderr
        )
        return 2

    report = validate_session(events)
    if not report["ok"]:
        print(
            json.dumps({"errors": report["errors"]}, ensure_ascii=False),
            file=sys.stderr,
        )
        return 1
    if not events:
        print(json.dumps({"error": "нет событий"}, ensure_ascii=False), file=sys.stderr)
        return 1

    session_id = str(report.get("session_id") or "session")
    if not SLUG_RE.match(session_id):
        print(
            json.dumps(
                {"error": f"недопустимый session_id: {session_id!r}"},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2
    # Повторная очистка перед публикацией: без локальных путей и длинных выдержек.
    clean = export_publishable(events, max_excerpt=200)
    path_in_repo = f"calibrations/{session_id}/session.jsonl"

    plan = build_plan(
        clean, repo_id=args.repo_id, revision=args.revision, path_in_repo=path_in_repo
    )
    if args.dry_run:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0

    try:
        result = _publish(
            clean,
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
