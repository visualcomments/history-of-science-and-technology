#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""CLI разработческой калибровки (harness/run.py, stdlib-only).

Команды (справка на русском):
  * ``validate-cases`` — проверить JSONL кейсов по схеме;
  * ``run``            — прогнать кейсы через адаптер (recording|command);
  * ``replay``         — повторно исполнить кейсы и сверить с эталонным
                         отчётом (детерминизм структуры);
  * ``report``         — сводка по отчёту/результатам.

Коды возврата: 0 — успех (все кейсы прошли), 1 — ошибки валидации/прогона,
2 — неверная конфигурация/недоступные файлы.

Детерминизм: системное время не используется, сортировка стабильная,
``event``/``case_id`` — SHA-256 канонического JSON.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Корень модуля: <repo>/physics-dataset-competition
MODULE_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(MODULE_ROOT / "harness"),):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from adapters import adapter_from_config  # noqa: E402
from core import (  # noqa: E402
    HarnessError,
    HarnessResult,
    build_report,
    deterministic_id,
    load_cases,
    run_case,
    validate_case,
)

EXIT_OK = 0
EXIT_VALIDATION = 1
EXIT_CONFIG = 2


def _dump_jsonl(path: Path, items: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        for item in items:
            fh.write(
                json.dumps(
                    item, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                )
                + "\n"
            )


def _load_json_or_jsonl(path: Path) -> list[dict[str, Any]]:
    """Прочитать JSON-объект/массив или JSONL (автоопределение по содержимому)."""
    if not path.is_file():
        raise HarnessError(f"файл не найден: {path}", kind="config")
    text = path.read_text(encoding="utf-8-sig")
    stripped = text.strip()
    if not stripped:
        return []
    if stripped.startswith("{") and "\n{" in text:
        # JSONL: несколько объектов, по одному на строку.
        items: list[dict[str, Any]] = []
        for lineno, line in enumerate(text.splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise HarnessError(
                    f"{path}, строка {lineno}: невалидный JSON: {exc}", kind="config"
                ) from exc
            if not isinstance(obj, dict):
                raise HarnessError(
                    f"{path}, строка {lineno}: должен быть JSON-объектом", kind="config"
                )
            items.append(obj)
        return items
    data = json.loads(stripped)
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    raise HarnessError(f"{path}: ожидался JSON-объект/массив", kind="config")


def cmd_validate_cases(args: argparse.Namespace) -> int:
    path = Path(args.cases)
    try:
        cases = load_cases(path)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ошибка: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    summary: dict[str, Any] = {
        "cases": len(cases),
        "ok": 0,
        "errors": 0,
        "failed_cases": [],
    }
    failed: list[dict[str, Any]] = []
    seen: set[str] = set()
    for i, case in enumerate(cases, 1):
        cid = case.get("case_id") if isinstance(case, dict) else None
        errs = validate_case(case)
        if isinstance(cid, str):
            if cid in seen:
                errs.append(f"повтор case_id {cid!r}")
            seen.add(cid)
        if errs:
            failed.append({"line": i, "case_id": cid, "errors": errs})
        else:
            summary["ok"] += 1
    summary["errors"] = sum(len(f["errors"]) for f in failed)
    summary["failed_cases"] = failed
    summary["ok"] = bool(not failed)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        status = "OK" if not failed else "FAIL"
        print(
            f"validate-cases: {status}  cases={summary['cases']} errors={summary['errors']}"
        )
        for item in failed:
            ident = f" [{item['case_id']}]" if item.get("case_id") else ""
            print(f"  кейс #{item['line']}{ident}: " + "; ".join(item["errors"]))
    return EXIT_OK if not failed else EXIT_VALIDATION


def _run_all(cases_path: Path, adapter: Any, max_rounds: int) -> list[HarnessResult]:
    cases = load_cases(cases_path)
    results: list[HarnessResult] = []
    for case in cases:
        errs = validate_case(case)
        if errs:
            raise HarnessError(
                f"кейс {case.get('case_id')!r}: невалиден: " + "; ".join(errs),
                kind="case",
            )
        results.append(run_case(case, adapter, max_rounds=max_rounds))
    return results


def _write_outputs(
    results: list[HarnessResult], events_path: Path | None, report_path: Path | None
) -> None:
    report = build_report(results)
    if events_path is not None:
        events: list[dict[str, Any]] = []
        for r in results:
            base = {
                "kind": "case_result",
                "result_id": deterministic_id({"case_id": r.case_id}),
                "case_id": r.case_id,
                "passed": r.passed,
                "needs_expert_approval": r.needs_expert_approval,
            }
            events.append(base)
            for round_rec in r.rounds:
                events.append(
                    {
                        "kind": "round",
                        "result_id": base["result_id"],
                        "case_id": r.case_id,
                        "round": round_rec.round_no,
                        "prompt": round_rec.prompt,
                        "answer": round_rec.answer,
                        "errors": round_rec.errors,
                        "feedback": round_rec.feedback,
                    }
                )
        _dump_jsonl(events_path, events)
    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def cmd_run(args: argparse.Namespace) -> int:
    cases_path = Path(args.cases)
    try:
        if args.responses:
            from adapters import RecordingAdapter

            adapter: Any = RecordingAdapter(responses_path=Path(args.responses))
        elif args.command:
            from adapters import OpenCodeAdapter

            adapter = OpenCodeAdapter(
                list(args.command),
                timeout_s=float(args.timeout),
                max_output_bytes=int(args.max_output_bytes),
            )
        else:
            print(
                "ошибка: нужен --responses FILE или --command CMD...",
                file=sys.stderr,
            )
            return EXIT_CONFIG
        if not cases_path.is_file():
            print(f"ошибка: файл кейсов не найден: {cases_path}", file=sys.stderr)
            return EXIT_CONFIG
        results = _run_all(cases_path, adapter, args.max_rounds)
    except HarnessError as exc:
        print(f"ошибка: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    _write_outputs(
        results,
        Path(args.events) if args.events else None,
        Path(args.report) if args.report else None,
    )
    summary = build_report(results)["summary"]
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(
            f"run: cases={summary['cases']} passed={summary['passed']} "
            f"failed={summary['failed']} rounds={summary['rounds_total']} "
            f"needs_expert_approval={summary['needs_expert_approval']}"
        )
    return EXIT_OK if summary["failed"] == 0 else EXIT_VALIDATION


def cmd_replay(args: argparse.Namespace) -> int:
    """Повторить прогон и сверить с эталонным отчётом (детерминизм)."""
    baseline_path = Path(args.baseline)
    cases_path = Path(args.cases)
    try:
        baseline_docs = _load_json_or_jsonl(baseline_path)
        if not baseline_docs:
            print("ошибка: пустой эталонный отчёт", file=sys.stderr)
            return EXIT_CONFIG
        baseline = baseline_docs[0] if len(baseline_docs) == 1 else None
        if baseline is None or "summary" not in baseline or "cases" not in baseline:
            print(
                "ошибка: эталон должен быть отчётом (report) с полями summary+cases",
                file=sys.stderr,
            )
            return EXIT_CONFIG
        if args.responses:
            from adapters import RecordingAdapter

            adapter: Any = RecordingAdapter(responses_path=Path(args.responses))
        elif args.command:
            from adapters import OpenCodeAdapter

            adapter = OpenCodeAdapter(
                list(args.command),
                timeout_s=float(args.timeout),
                max_output_bytes=int(args.max_output_bytes),
            )
        else:
            print(
                "ошибка: нужен --responses FILE или --command CMD...", file=sys.stderr
            )
            return EXIT_CONFIG
        if not cases_path.is_file():
            print(f"ошибка: файл кейсов не найден: {cases_path}", file=sys.stderr)
            return EXIT_CONFIG
        results = _run_all(cases_path, adapter, args.max_rounds)
    except HarnessError as exc:
        print(f"ошибка: {exc}", file=sys.stderr)
        return EXIT_CONFIG

    rerun = build_report(results)
    # Сверяем структуру: сводка и per-case статусы должны совпасть побитно.
    diffs: list[str] = []
    if rerun["summary"] != baseline.get("summary"):
        diffs.append("summary различается")
    b_cases = {c.get("case_id"): c for c in baseline.get("cases", [])}
    for c in rerun["cases"]:
        b = b_cases.get(c.get("case_id"))
        if b is None:
            diffs.append(f"кейс {c.get('case_id')!r}: отсутствует в эталоне")
            continue
        for key in ("passed", "rounds_used", "needs_expert_approval", "errors"):
            if c.get(key) != b.get(key):
                diffs.append(
                    f"кейс {c.get('case_id')!r}: поле {key} различается "
                    f"(replay={c.get(key)!r}, baseline={b.get(key)!r})"
                )
    if args.json:
        print(
            json.dumps(
                {"deterministic": not diffs, "diffs": diffs},
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        if diffs:
            print("replay: FAIL — структура недетерминирована:")
            for d in diffs:
                print(f"  - {d}")
        else:
            print("replay: OK — структура совпала с эталоном")
    return EXIT_OK if not diffs else EXIT_VALIDATION


def cmd_report(args: argparse.Namespace) -> int:
    path = Path(args.report)
    try:
        docs = _load_json_or_jsonl(path)
    except (HarnessError, json.JSONDecodeError) as exc:
        print(f"ошибка: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    if not docs:
        print("ошибка: пустой отчёт", file=sys.stderr)
        return EXIT_CONFIG
    doc = docs[0] if len(docs) == 1 else None
    if doc is None or "summary" not in doc:
        print("ошибка: ожидался отчёт с полем summary", file=sys.stderr)
        return EXIT_CONFIG
    s = doc["summary"]
    if args.json:
        print(json.dumps(doc, ensure_ascii=False, indent=2))
        return EXIT_OK
    total = s.get("cases", 0)
    passed = s.get("passed", 0)
    pending = s.get("needs_expert_approval", 0)
    print("=== Отчёт калибровки ===")
    print(f"кейсов всего:          {total}")
    print(f"прошли автопроверку:   {passed} ({s.get('pass_rate', 0) * 100:.1f}%)")
    print(f"не прошли:             {s.get('failed', 0)}")
    print(
        f"раундов всего:         {s.get('rounds_total', 0)} "
        f"(макс {s.get('rounds_max', 0)}, средн. {s.get('rounds_avg', 0)})"
    )
    print(f"ждут одобрения эксперта: {pending}")
    print(f"одобрено экспертом:    {s.get('expert_approved', 0)} (harness не одобряет)")
    if s.get("error_classes"):
        print("классы ошибок:")
        for cls, n in sorted(s["error_classes"].items()):
            print(f"  {cls}: {n}")
    for c in doc.get("cases", []):
        status = "PASS" if c.get("passed") else "FAIL"
        expert = " [ждёт эксперта]" if c.get("needs_expert_approval") else ""
        print(f"  {c.get('case_id')}: {status} rounds={c.get('rounds_used')}{expert}")
        for err in c.get("errors", [])[:5]:
            print(f"    - {err}")
    return EXIT_OK if s.get("failed", 0) == 0 else EXIT_VALIDATION


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="harness/run.py",
        description=(
            "Разработческая калибровка агента: прогон кейсов, автопроверка "
            "физических записей, детерминированные отчёты. Экспертное "
            "одобрение harness не фабрикует."
        ),
    )
    sub = ap.add_subparsers(dest="command", required=True)

    p_val = sub.add_parser(
        "validate-cases", help="проверить JSONL кейсов по схеме calibration_case"
    )
    p_val.add_argument("cases", help="JSONL-файл кейсов")
    p_val.add_argument("--json", action="store_true", help="машиночитаемая сводка")
    p_val.set_defaults(func=cmd_validate_cases)

    p_run = sub.add_parser(
        "run", help="прогнать кейсы через адаптер (recording или command)"
    )
    p_run.add_argument("cases", help="JSONL-файл кейсов")
    p_run.add_argument(
        "--responses", help="JSONL-файл заготовленных ответов (адаптер recording)"
    )
    p_run.add_argument(
        "--command",
        nargs="+",
        metavar="ARG",
        help="локальная команда-агент (адаптер command; промпт уходит в stdin)",
    )
    p_run.add_argument(
        "--max-rounds", type=int, default=3, help="лимит раундов (по умолчанию 3)"
    )
    p_run.add_argument(
        "--timeout", type=float, default=30.0, help="таймаут команды, сек"
    )
    p_run.add_argument(
        "--max-output-bytes",
        type=int,
        default=512 * 1024,
        help="лимит размера вывода команды",
    )
    p_run.add_argument("--events", help="выходной JSONL событий (round/case_result)")
    p_run.add_argument("--report", help="выходной JSON отчёта")
    p_run.add_argument("--json", action="store_true", help="машиночитаемая сводка")
    p_run.set_defaults(func=cmd_run)

    p_replay = sub.add_parser(
        "replay",
        help="повторить прогон и сверить структуру с эталонным отчётом",
    )
    p_replay.add_argument("cases", help="JSONL-файл кейсов")
    p_replay.add_argument(
        "--baseline", required=True, help="эталонный JSON-отчёт (report)"
    )
    p_replay.add_argument("--responses", help="JSONL-файл заготовленных ответов")
    p_replay.add_argument(
        "--command", nargs="+", metavar="ARG", help="локальная команда-агент"
    )
    p_replay.add_argument("--max-rounds", type=int, default=3, help="лимит раундов")
    p_replay.add_argument(
        "--timeout", type=float, default=30.0, help="таймаут команды, сек"
    )
    p_replay.add_argument(
        "--max-output-bytes", type=int, default=512 * 1024, help="лимит вывода"
    )
    p_replay.add_argument("--json", action="store_true", help="машиночитаемая сводка")
    p_replay.set_defaults(func=cmd_replay)

    p_rep = sub.add_parser(
        "report", help="сводка: pass-rate, раунды, ошибки, ожидание эксперта"
    )
    p_rep.add_argument("report", help="JSON-отчёт (выход run --report)")
    p_rep.add_argument("--json", action="store_true", help="машиночитаемый вывод")
    p_rep.set_defaults(func=cmd_report)

    return ap


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except HarnessError as exc:
        print(f"ошибка: {exc}", file=sys.stderr)
        return EXIT_CONFIG


if __name__ == "__main__":
    raise SystemExit(main())
