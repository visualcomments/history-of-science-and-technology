#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""CLI сессий экспертной калибровки (stdlib-only).

Команды::

  init      --session SID --session-file F --task task.json --timestamp TS
  append    --session-file F --event event.json
  validate  --session-file F [--json]
  summary   --session-file F [--json]
  export    --session-file F --out publishable.jsonl [--max-excerpt N]

Все аргументы — через JSON-файлы либо на диске; никаких секретов в командной
строке. Коды возврата: ``0`` — успех, ``1`` — невалидные данные/сессия,
``2`` — невозможно выполнить (нет файла/аргументов/зависимости).

``init`` создаёт первое событие ``task``; ``append`` добавляет одно событие из
JSON-файла; ``validate`` проверяет схему, порядок ролей и одобренный ``final``;
``summary`` печатает прогресс; ``export`` пишет публикуемый JSONL без локальных
путей и полного текста источников.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

MODULE_ROOT = Path(__file__).resolve().parent.parent
CALIBRATION = MODULE_ROOT / "calibration"
if str(CALIBRATION) not in sys.path:
    sys.path.insert(0, str(CALIBRATION))

from session import (  # type: ignore[import-not-found]  # noqa: E402
    SessionWriter,
    export_publishable,
    load_session,
    summarize,
    validate_session,
)


def _read_json(path: str, what: str) -> dict[str, Any]:
    """Прочитать JSON-объект; при ошибке печатает JSON и поднимает SystemExit(2)."""
    p = Path(path)
    if not p.is_file():
        print(
            json.dumps({"error": f"{what}: файл не найден: {p}"}, ensure_ascii=False),
            file=sys.stderr,
        )
        raise SystemExit(2)
    try:
        data = json.loads(p.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        print(
            json.dumps({"error": f"{what}: {exc}"}, ensure_ascii=False), file=sys.stderr
        )
        raise SystemExit(2) from exc
    if not isinstance(data, dict):
        print(
            json.dumps({"error": f"{what}: ожидался JSON-объект"}, ensure_ascii=False),
            file=sys.stderr,
        )
        raise SystemExit(2)
    return data


def _load(path: str) -> list[dict[str, Any]]:
    """Прочитать журнал; при ошибке печатает JSON и поднимает SystemExit(2)."""
    p = Path(path)
    if not p.is_file():
        print(
            json.dumps({"error": f"сессия не найдена: {p}"}, ensure_ascii=False),
            file=sys.stderr,
        )
        raise SystemExit(2)
    try:
        return load_session(p)
    except (OSError, json.JSONDecodeError) as exc:
        print(
            json.dumps(
                {"error": f"не удалось прочитать сессию: {exc}"}, ensure_ascii=False
            ),
            file=sys.stderr,
        )
        raise SystemExit(2) from exc


def cmd_init(args: argparse.Namespace) -> int:
    task = _read_json(args.task, "task")
    source = task.get("source")
    if not isinstance(source, dict):
        print(
            json.dumps(
                {"error": "task.source обязателен (объект)"}, ensure_ascii=False
            ),
            file=sys.stderr,
        )
        return 2
    # В событие task попадает только prompt — схема payload не допускает лишних полей.
    payload = {"prompt": task.get("prompt", "")}
    if "expert_approved" in task:
        payload["expert_approved"] = task["expert_approved"]
    try:
        writer = SessionWriter(args.session_file, args.session)
        event = writer.append(
            role="task",
            timestamp=args.timestamp,
            source=source,
            payload=payload,
            round=0,
        )
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(
        json.dumps(
            {"session_id": event["session_id"], "event_id": event["event_id"]},
            ensure_ascii=False,
        )
    )
    return 0


def cmd_append(args: argparse.Namespace) -> int:
    event = _read_json(args.event, "event")
    required = ("role", "timestamp", "source", "payload")
    missing = [k for k in required if k not in event]
    if missing:
        print(
            json.dumps(
                {"error": f"event: отсутствуют поля {missing}"}, ensure_ascii=False
            ),
            file=sys.stderr,
        )
        return 2
    # session_id берём из файла сессии, если он там уже есть.
    events = (
        load_session(args.session_file) if Path(args.session_file).is_file() else []
    )
    session_id = event.get("session_id") or (
        events[0].get("session_id") if events else None
    )
    if not isinstance(session_id, str):
        print(
            json.dumps(
                {"error": "event.session_id обязателен для первой записи"},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2
    try:
        writer = SessionWriter(args.session_file, session_id)
        written = writer.append(
            role=event["role"],
            timestamp=event["timestamp"],
            source=event["source"],
            payload=event["payload"],
            round=event.get("round"),
        )
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(
        json.dumps(
            {"event_id": written["event_id"], "round": written["round"]},
            ensure_ascii=False,
        )
    )
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    events = _load(args.session_file)
    report = validate_session(events)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        status = "OK" if report["ok"] else "ОШИБКИ"
        print(f"{status}: событий={report['events']} сессия={report['session_id']}")
        for err in report["errors"]:
            print(f"  - {err}")
    return 0 if report["ok"] else 1


def cmd_summary(args: argparse.Namespace) -> int:
    events = _load(args.session_file)
    report = summarize(events)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(
            f"сессия={report['session_id']} событий={report['events']} "
            f"раундов={report['rounds']} исправлений={report['corrections']} "
            f"одобрено={'да' if report['expert_approved'] else 'нет'}"
        )
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    events = _load(args.session_file)
    report = validate_session(events)
    if not report["ok"]:
        print(
            json.dumps({"errors": report["errors"]}, ensure_ascii=False),
            file=sys.stderr,
        )
        return 1
    clean = export_publishable(events, max_excerpt=args.max_excerpt)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        "\n".join(json.dumps(e, ensure_ascii=False, sort_keys=True) for e in clean)
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"out": str(out), "events": len(clean)}, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Сессии экспертной калибровки: JSONL-журнал, валидация, публикация."
    )
    sub = ap.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="создать сессию и первое событие task")
    p_init.add_argument("--session", required=True, help="идентификатор сессии")
    p_init.add_argument("--session-file", required=True, help="путь к JSONL-журналу")
    p_init.add_argument(
        "--task", required=True, help="JSON-файл задачи: prompt + source"
    )
    p_init.add_argument(
        "--timestamp", required=True, help="ISO-8601 UTC (явно, не из часов)"
    )
    p_init.set_defaults(func=cmd_init)

    p_app = sub.add_parser("append", help="дописать одно событие из JSON-файла")
    p_app.add_argument("--session-file", required=True, help="путь к JSONL-журналу")
    p_app.add_argument("--event", required=True, help="JSON-файл события")
    p_app.set_defaults(func=cmd_append)

    p_val = sub.add_parser("validate", help="проверить схему, порядок и одобрение")
    p_val.add_argument("--session-file", required=True, help="путь к JSONL-журналу")
    p_val.add_argument("--json", action="store_true", help="машиночитаемая сводка")
    p_val.set_defaults(func=cmd_validate)

    p_sum = sub.add_parser("summary", help="показать прогресс сессии")
    p_sum.add_argument("--session-file", required=True, help="путь к JSONL-журналу")
    p_sum.add_argument("--json", action="store_true", help="машиночитаемая сводка")
    p_sum.set_defaults(func=cmd_summary)

    p_exp = sub.add_parser(
        "export", help="записать публикуемый JSONL (без локальных путей)"
    )
    p_exp.add_argument("--session-file", required=True, help="путь к JSONL-журналу")
    p_exp.add_argument("--out", required=True, help="выходной JSONL для публикации")
    p_exp.add_argument(
        "--max-excerpt", type=int, default=200, help="макс. длина выдержки"
    )
    p_exp.set_defaults(func=cmd_export)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except SystemExit as exc:
        # Ошибки чтения ввода возвращают код доступности 2 (а не прерывание).
        code = exc.code
        return code if isinstance(code, int) else 2


if __name__ == "__main__":
    raise SystemExit(main())
