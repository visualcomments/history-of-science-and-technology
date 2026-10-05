#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Ядро разработческой калибровки агента (harness, stdlib-only).

Загружает кейсы из JSONL (``harness/schema/calibration_case.schema.json``),
исполняет раунды «промпт → ответ агента → автопроверка → обратная связь →
следующий ответ» с ограничением ``max_rounds``, детерминированно собирает
:class:`HarnessResult`. Экспертное одобрение в harness **не фабрикуется**:
любой успешный прогон помечается ``needs_expert_approval=True``.

Детерминизм: не используется системное время, порядок обхода — вставления,
``event_id``/id кейса — SHA-256 канонического JSON. Секреты не проходят
ни в промпт, ни в результаты (см. :func:`redact_text`).
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Protocol

# Корень модуля: <repo>/physics-dataset-competition
MODULE_ROOT = Path(__file__).resolve().parents[1]
CASE_SCHEMA = MODULE_ROOT / "harness" / "schema" / "calibration_case.schema.json"
RECORD_SCHEMA = MODULE_ROOT / "configs" / "schema" / "record.schema.json"

DOMAINS = ("AERO", "STR", "RADAR", "CTRL")
SPLITS = ("train", "validation", "test")
VALUE_TOLERANCE_EPS = 1e-12
MAX_ANSWER_BYTES = 512 * 1024  # лимит размера ответа агента

RECORD_ID_RE = re.compile(r"^[A-Z]{2,6}-[0-9A-F]{8,}$")
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SESSION_ID_RE = re.compile(r"^[A-Za-z0-9._-]{4,64}$")
CASE_ID_RE = SESSION_ID_RE

SOURCE_TYPES = {
    "book",
    "article",
    "report",
    "dataset",
    "standard",
    "patent",
    "thesis",
    "other",
}
RECORD_SOURCE_TYPES = SOURCE_TYPES - {"other"}
RIGHTS_BASE_KEYS = ("reusable", "redistributable", "basis")
UNITS = None  # единицы — свободные строки по record.schema.json

# --- секреты: только обнаружение/редактирование, никакого проброса ------------

_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"hf_[A-Za-z0-9]{8,}"),
    re.compile(r"sk-ant-[A-Za-z0-9_-]{8,}"),
    re.compile(r"sk-[A-Za-z0-9_-]{8,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{8,}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{8,}"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{8,}"),
    re.compile(
        r"(?i)\b(api[_-]?key|token|secret|password|passwd|pwd)\b\s*[:=]\s*[^\s\"',;]{6,}"
    ),
    re.compile(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"
    ),
)
_REDACTED = "[REDACTED]"
_SENSITIVE_KEYS = re.compile(
    r"(?i)(token|secret|password|passwd|pwd|api[_-]?key|authorization)"
)


def redact_text(text: str) -> str:
    """Вырезать очевидные токены/ключи из строки (идемпотентно)."""
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(_REDACTED, text)
    return text


def redact_tree(value: Any) -> Any:
    """Рекурсивно редактировать секреты (в т.ч. по чувствительным ключам)."""
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if isinstance(key, str) and _SENSITIVE_KEYS.search(key):
                out[key] = _REDACTED if item not in (None, "") else item
            else:
                out[key] = redact_tree(item)
        return out
    if isinstance(value, list):
        return [redact_tree(item) for item in value]
    return value


# --- канонизация / id ---------------------------------------------------------


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def deterministic_id(value: Any) -> str:
    """Стабильный hex-id: SHA-256 от канонического JSON без системного времени."""
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


# --- валидация кейса -----------------------------------------------------------


def validate_case(case: Any) -> list[str]:
    """Проверить кейс по calibration_case.schema.json (stdlib-эквивалент).

    Пустой список = валиден. Отклоняются секреты, сырые бинарники,
    ожидания без координат источника, неоднозначные expected.
    """
    errors: list[str] = []
    if not isinstance(case, dict):
        return ["case: должен быть JSON-объектом"]

    for key in (
        "case_id",
        "schema_version",
        "domain",
        "source",
        "prompt",
        "expected",
        "expert_notes",
        "provenance",
        "split",
        "license",
    ):
        if key not in case:
            errors.append(f"отсутствует обязательное поле '{key}'")

    cid = case.get("case_id")
    if not isinstance(cid, str) or not CASE_ID_RE.match(cid or ""):
        errors.append(f"case_id недопустим: {cid!r}")

    sv = case.get("schema_version")
    if not isinstance(sv, str) or not SEMVER_RE.match(sv or ""):
        errors.append(f"schema_version должен быть SemVer: {sv!r}")

    if case.get("domain") not in DOMAINS:
        errors.append(
            f"domain недопустим: {case.get('domain')!r} (AERO/STR/RADAR/CTRL)"
        )

    if case.get("split") not in SPLITS:
        errors.append(
            f"split недопустим: {case.get('split')!r} (train/validation/test)"
        )

    if not isinstance(case.get("prompt"), str) or not case.get("prompt"):
        errors.append("prompt должен быть непустой строкой")
    if not isinstance(case.get("expert_notes"), str):
        errors.append("expert_notes должен быть строкой")
    if not isinstance(case.get("license"), str) or not case.get("license"):
        errors.append("license должен быть непустой строкой")

    src = case.get("source")
    if not isinstance(src, dict):
        errors.append("source: должен быть объектом")
    else:
        if src.get("source_type") not in SOURCE_TYPES:
            errors.append(f"source.source_type недопустим: {src.get('source_type')!r}")
        if not isinstance(src.get("title"), str) or not src.get("title"):
            errors.append("source.title должен быть непустой строкой")
        rights = src.get("rights")
        if not isinstance(rights, dict):
            errors.append("source.rights: должен быть объектом")
        else:
            for key in ("reusable", "redistributable"):
                if not isinstance(rights.get(key), bool):
                    errors.append(f"source.rights.{key} должен быть boolean")
            if not isinstance(rights.get("basis"), str) or not rights.get("basis"):
                errors.append("source.rights.basis должен быть непустой строкой")
        for key in ("excerpt",):
            v = src.get(key)
            if v is not None and (not isinstance(v, str) or len(v) > 2000):
                errors.append(f"source.{key} должен быть строкой ≤ 2000 символов")
        url = src.get("url")
        if isinstance(url, str) and re.search(
            r"\.(pdf|zip|png|jpe?g|tiff?|djvu)(\?|$)", url, re.I
        ):
            errors.append("source.url указывает на сырой бинарник — запрещено")

    prov = case.get("provenance")
    if not isinstance(prov, dict):
        errors.append("provenance: должен быть объектом")
    else:
        if not isinstance(prov.get("method"), str) or not prov.get("method"):
            errors.append("provenance.method обязателен")
        sha = prov.get("sha256")
        if not isinstance(sha, str) or not SHA256_RE.match(sha or ""):
            errors.append("provenance.sha256 должен быть hex из 64 символов")

    expected = case.get("expected")
    if not isinstance(expected, dict):
        errors.append("expected: должен быть объектом")
    else:
        has_records = "records" in expected
        has_constraints = (
            "expected.constraints" in case["expected"] or "constraints" in expected
        )
        if has_records and has_constraints:
            errors.append("expected: records и constraints взаимоисключимы")
        if not has_records and not has_constraints:
            errors.append("expected: нужен ровно один из вариантов records|constraints")
        if has_records:
            recs = expected.get("records")
            if not isinstance(recs, list) or not recs:
                errors.append("expected.records должен быть непустым массивом")
            else:
                for i, rec in enumerate(recs):
                    for err in validate_record(rec):
                        errors.append(f"expected.records[{i}]: {err}")
                    vals = rec.get("values") if isinstance(rec, dict) else None
                    if isinstance(vals, list):
                        for j, v in enumerate(vals):
                            loc = (
                                v.get("source_ref", {}).get("location")
                                if isinstance(v, dict)
                                and isinstance(v.get("source_ref"), dict)
                                else None
                            )
                            if not (
                                isinstance(loc, str) and "#" in loc and len(loc) >= 3
                            ):
                                errors.append(
                                    f"expected.records[{i}].values[{j}]: "
                                    "source_ref.location с '#' обязателен"
                                )
        if has_constraints:
            cons = expected.get("constraints")
            if not isinstance(cons, list) or not cons:
                errors.append("expected.constraints должен быть непустым массивом")
            else:
                for i, c in enumerate(cons):
                    if not isinstance(c, dict):
                        errors.append(
                            f"expected.constraints[{i}]: должен быть объектом"
                        )
                        continue
                    for key in ("name", "value", "unit", "source_ref"):
                        if key not in c:
                            errors.append(
                                f"expected.constraints[{i}]: отсутствует '{key}'"
                            )
                    sref = c.get("source_ref")
                    if not isinstance(sref, dict):
                        errors.append(
                            f"expected.constraints[{i}].source_ref: должен быть объектом"
                        )
                    else:
                        loc = sref.get("location")
                        if not (isinstance(loc, str) and "#" in loc and len(loc) >= 3):
                            errors.append(
                                f"expected.constraints[{i}].source_ref.location: "
                                "координаты источника ('путь#N') обязательны"
                            )
                    if "tolerance" in c and (
                        not isinstance(c["tolerance"], (int, float))
                        or isinstance(c["tolerance"], bool)
                        or c["tolerance"] < 0
                    ):
                        errors.append(
                            f"expected.constraints[{i}].tolerance должен быть числом ≥ 0"
                        )

    # Секреты в кейсе запрещены — валидатор отклоняет.
    blob = _canonical({k: v for k, v in case.items() if k != "expected"})
    if redact_text(blob) != blob:
        errors.append("кейс содержит предполагаемые секреты (токены/ключи) — запрещено")
    return errors


# --- валидация записи (эквивалент configs/schema/record.schema.json) ----------


def validate_record(rec: Any) -> list[str]:
    """Проверить запись физданных по record.schema.json. Пустой список = валидно."""
    errors: list[str] = []
    if not isinstance(rec, dict):
        return ["запись: должна быть JSON-объектом"]

    for key in (
        "record_id",
        "schema_version",
        "domain",
        "source",
        "rights",
        "provenance",
        "values",
        "validation",
    ):
        if key not in rec:
            errors.append(f"отсутствует обязательное поле '{key}'")

    rid = rec.get("record_id")
    if not isinstance(rid, str) or not RECORD_ID_RE.match(rid or ""):
        errors.append(f"record_id должен быть ^[A-Z]{{2,6}}-[0-9A-F]{{8,}}$: {rid!r}")

    sv = rec.get("schema_version")
    if not isinstance(sv, str) or not SEMVER_RE.match(sv or ""):
        errors.append(f"schema_version должен быть SemVer: {sv!r}")

    if rec.get("domain") not in {"AERO", "STR", "RADAR", "CTRL"}:
        errors.append(f"domain недопустим: {rec.get('domain')!r}")

    src = rec.get("source")
    if not isinstance(src, dict):
        errors.append("source: должен быть объектом")
    else:
        for key in ("title", "source_type", "year", "language", "url", "license"):
            if key not in src:
                errors.append(f"source: отсутствует '{key}'")
        if src.get("source_type") not in RECORD_SOURCE_TYPES:
            errors.append(f"source.source_type недопустим: {src.get('source_type')!r}")
        if not isinstance(src.get("year"), int) or isinstance(src.get("year"), bool):
            errors.append("source.year должен быть целым")
        for key in ("title", "language", "url", "license"):
            if not isinstance(src.get(key), str) or not src.get(key):
                errors.append(f"source.{key} должен быть непустой строкой")

    rts = rec.get("rights")
    if not isinstance(rts, dict):
        errors.append("rights: должен быть объектом")
    else:
        for key in ("reusable", "redistributable"):
            if not isinstance(rts.get(key), bool):
                errors.append(f"rights.{key} должен быть boolean")
        if not isinstance(rts.get("basis"), str) or not rts.get("basis"):
            errors.append("rights.basis должен быть непустой строкой")

    vals = rec.get("values")
    if not isinstance(vals, list) or len(vals) < 1:
        errors.append("values: должен быть непустым массивом")
    else:
        for i, v in enumerate(vals):
            if not isinstance(v, dict):
                errors.append(f"values[{i}]: должен быть объектом")
                continue
            for key in ("name", "value", "unit"):
                if key not in v:
                    errors.append(f"values[{i}]: отсутствует '{key}'")
            if isinstance(v.get("value"), bool):
                errors.append(f"values[{i}].value не должен быть boolean")

    prov = rec.get("provenance")
    if not isinstance(prov, dict):
        errors.append("provenance: должен быть объектом")
    else:
        for key in ("activity", "agent_role_id", "retrieved_at", "method", "sha256"):
            if key not in prov:
                errors.append(f"provenance: отсутствует '{key}'")
        sha = prov.get("sha256")
        if not isinstance(sha, str) or not SHA256_RE.match(sha or ""):
            errors.append("provenance.sha256 должен быть hex из 64 символов")

    val = rec.get("validation")
    if not isinstance(val, dict):
        errors.append("validation: должен быть объектом")
    else:
        for key in ("status", "checked_by_role_id", "checked_at"):
            if key not in val:
                errors.append(f"validation: отсутствует '{key}'")
        if val.get("status") not in {
            "unchecked",
            "in-review",
            "accepted",
            "rejected",
            "needs-expert",
        }:
            errors.append(f"validation.status недопустим: {val.get('status')!r}")
    return errors


# --- физическая проверка ответа против expected -------------------------------


def _num_equal(actual: Any, expected: Any, tolerance: float) -> bool:
    try:
        a, e = float(actual), float(expected)
    except (TypeError, ValueError):
        return actual == expected
    return abs(a - e) <= max(tolerance, VALUE_TOLERANCE_EPS)


def _value_matches(actual: Any, expected: Any, tolerance: float) -> bool:
    if isinstance(expected, list) and isinstance(actual, list):
        if len(expected) != len(actual):
            return False
        return all(_value_matches(a, e, tolerance) for a, e in zip(actual, expected))
    return _num_equal(actual, expected, tolerance)


def check_answer_against_expected(answer: Any, expected: dict[str, Any]) -> list[str]:
    """Автопроверка ответа агента против expected кейса.

    Возвращает список ошибок (пустой = согласовано). Проверяются структура
    записей (record.schema.json), значения с допусками, единицы измерения.
    """
    errors: list[str] = []
    if not isinstance(answer, dict):
        return ["ответ агента должен быть JSON-объектом"]

    if "records" in expected:
        recs = answer.get("records")
        if not isinstance(recs, list) or len(recs) != len(expected["records"]):
            errors.append(
                f"records: ожидалось {len(expected.get('records', []))} записей, получено "
                f"{len(recs) if isinstance(recs, list) else 'не-массив'}"
            )
            return errors
        for i, (got, want) in enumerate(zip(recs, expected["records"])):
            for err in validate_record(got):
                errors.append(f"records[{i}]: {err}")
            for j, wv in enumerate(want.get("values", []) or []):
                gv = (
                    (got.get("values") or [None] * (j + 1))[j]
                    if isinstance(got.get("values"), list)
                    else None
                )
                if not isinstance(gv, dict):
                    errors.append(f"records[{i}].values[{j}]: отсутствует")
                    continue
                if str(gv.get("unit", "")).strip() != str(wv.get("unit", "")).strip():
                    errors.append(
                        f"records[{i}].values[{j}].unit: ожидалось {wv.get('unit')!r}, "
                        f"получено {gv.get('unit')!r}"
                    )
                tol = float(wv.get("tolerance", 0.0) or 0.0)
                if not _value_matches(gv.get("value"), wv.get("value"), tol):
                    errors.append(
                        f"records[{i}].values[{j}].value: ожидалось {wv.get('value')!r}, "
                        f"получено {gv.get('value')!r}"
                    )
        return errors

    constraints = expected.get("constraints") or []
    got_values = answer.get("values")
    if not isinstance(got_values, list):
        errors.append("ответ должен содержать массив 'values'")
        got_values = []
    by_name: dict[str, dict[str, Any]] = {}
    for v in got_values:
        if isinstance(v, dict) and isinstance(v.get("name"), str):
            by_name.setdefault(v["name"], v)
    for i, c in enumerate(constraints):
        name = c.get("name")
        got = by_name.get(name)
        if got is None:
            errors.append(f"constraint[{i}] '{name}': значение отсутствует в ответе")
            continue
        tol = float(c.get("tolerance", 0.0) or 0.0)
        if not _value_matches(got.get("value"), c.get("value"), tol):
            errors.append(
                f"constraint[{i}] '{name}'.value: ожидалось {c.get('value')!r} "
                f"(допуск {tol}), получено {got.get('value')!r}"
            )
        want_unit = str(c.get("unit", "")).strip()
        got_unit = str(got.get("unit", "")).strip()
        if want_unit != got_unit:
            errors.append(
                f"constraint[{i}] '{name}'.unit: ожидалось {want_unit!r}, получено {got_unit!r}"
            )
    return errors


# --- загрузка JSONL ------------------------------------------------------------


def load_cases(path: str | Path) -> list[dict[str, Any]]:
    """Прочитать JSONL-файл кейсов. Пустой/отсутствующий файл → ``ValueError``/``[]``."""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"файл кейсов не найден: {p}")
    cases: list[dict[str, Any]] = []
    for lineno, line in enumerate(p.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            cases.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"строка {lineno}: невалидный JSON: {exc}") from exc
    return cases


def validate_cases_file(path: str | Path) -> dict[str, Any]:
    """Проверить все кейсы JSONL. Возвращает {ok, cases, errors, failed_cases}."""
    cases = load_cases(path)
    errors: list[str] = []
    failed: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for i, case in enumerate(cases, 1):
        cid = case.get("case_id") if isinstance(case, dict) else None
        errs = validate_case(case)
        if isinstance(cid, str):
            if cid in seen_ids:
                errs.append(f"повтор case_id {cid!r}")
            seen_ids.add(cid)
        if errs:
            failed.append({"line": i, "case_id": cid, "errors": errs})
            errors.extend(f"кейс #{i} ({cid!r}): {e}" for e in errs)
    return {
        "ok": not errors,
        "cases": len(cases),
        "errors": len(errors),
        "failed_cases": failed,
        "messages": errors,
    }


# --- адаптер агента ------------------------------------------------------------


class AgentAdapter(Protocol):
    """Контракт адаптера агента: `respond(prompt, context) -> dict`.

    Контекст — dict без секретов; ответ — JSON-сериализуемый dict.
    """

    def respond(self, prompt: str, context: dict[str, Any]) -> dict[str, Any]: ...


@dataclass
class HarnessError(Exception):
    message: str
    kind: str = "harness"

    def __str__(self) -> str:  # pragma: no cover - тривиально
        return f"{self.kind}: {self.message}"


@dataclass
class RoundRecord:
    """Один раунд: промпт, ответ, ошибки автопроверки, обратная связь."""

    round_no: int
    prompt: str
    answer: Any
    errors: list[str] = field(default_factory=list)
    feedback: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "round": self.round_no,
            "prompt": self.prompt,
            "answer": self.answer,
            "errors": list(self.errors),
            "feedback": self.feedback,
        }


@dataclass
class HarnessResult:
    """Итог одного прогона кейса. Детерминирован при фиксированном адаптере."""

    case_id: str
    passed: bool
    needs_expert_approval: bool
    rounds: list[RoundRecord] = field(default_factory=list)
    final_answer: Any = None
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "passed": self.passed,
            "needs_expert_approval": self.needs_expert_approval,
            "rounds": [r.to_dict() for r in self.rounds],
            "final_answer": self.final_answer,
            "errors": list(self.errors),
        }


def _answer_bytes(answer: Any) -> int:
    try:
        return len(_canonical(answer).encode("utf-8"))
    except (TypeError, ValueError):
        return -1


def run_case(
    case: dict[str, Any],
    adapter: AgentAdapter,
    *,
    max_rounds: int = 3,
    max_answer_bytes: int = MAX_ANSWER_BYTES,
) -> HarnessResult:
    """Исполнить кейс: bounded-цикл с автопроверкой и явной обратной связью.

    Экспертное одобрение harness не имитирует: при успехе выставляется
    ``needs_expert_approval=True``, ``passed=True`` только при нулевых ошибках.
    Детерминирован: тот же case+adapter → тот же результат.
    """
    case_errors = validate_case(case)
    if case_errors:
        raise HarnessError("невалидный кейс: " + "; ".join(case_errors), kind="case")
    if max_rounds < 1:
        raise HarnessError("max_rounds должен быть ≥ 1", kind="config")

    case_id = str(case["case_id"])
    prompt = str(case["prompt"])
    expected = case["expected"]
    rounds: list[RoundRecord] = []
    errors: list[str] = []

    context: dict[str, Any] = {
        "case_id": case_id,
        "domain": case.get("domain"),
        "subdomain": case.get("subdomain"),
        "source": case.get("source"),
        "round": 0,
        "feedback": None,
        "errors": [],
    }

    final_answer: Any = None
    for round_no in range(1, max_rounds + 1):
        context["round"] = round_no
        context["errors"] = list(errors)
        context["feedback"] = rounds[-1].feedback if rounds else None

        answer = adapter.respond(redact_text(prompt), redact_tree(context))
        size = _answer_bytes(answer)
        if size < 0 or size > max_answer_bytes:
            errors.append(
                f"ответ агента превышает лимит размера ({size} байт > {max_answer_bytes})"
            )
            rounds.append(
                RoundRecord(
                    round_no=round_no,
                    prompt=prompt,
                    answer=None,
                    errors=list(errors),
                    feedback=errors[-1],
                )
            )
            final_answer = None
            continue

        round_errors = check_answer_against_expected(answer, expected)
        errors = round_errors
        feedback = (
            "OK: все автопроверки пройдены; ожидается экспертное одобрение."
            if not round_errors
            else "Ошибки автопроверки: " + "; ".join(round_errors)
        )
        rounds.append(
            RoundRecord(
                round_no=round_no,
                prompt=prompt,
                answer=answer,
                errors=list(round_errors),
                feedback=feedback,
            )
        )
        final_answer = answer
        if not round_errors:
            break

    passed = bool(rounds) and not errors and final_answer is not None
    return HarnessResult(
        case_id=case_id,
        passed=passed,
        # Никогда не «одобряем» автоматически: успешный прогон требует эксперта.
        needs_expert_approval=passed,
        rounds=rounds,
        final_answer=final_answer if passed else None,
        errors=errors,
    )


def summarize_results(results: Iterable[HarnessResult]) -> dict[str, Any]:
    """Детерминированная сводка прогона: pass-rate, раунды, классы ошибок."""
    results = list(results)
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    rounds_used = [len(r.rounds) for r in results]
    error_classes: dict[str, int] = {}
    for r in results:
        for err in r.errors:
            cls = err.split(":")[0].split(".")[0].strip() or "прочее"
            error_classes[cls] = error_classes.get(cls, 0) + 1
    return {
        "cases": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": round(passed / total, 4) if total else 0.0,
        "rounds_total": sum(rounds_used),
        "rounds_max": max(rounds_used) if rounds_used else 0,
        "rounds_avg": round(sum(rounds_used) / total, 2) if total else 0.0,
        "error_classes": dict(sorted(error_classes.items())),
        "needs_expert_approval": sum(1 for r in results if r.needs_expert_approval),
        "expert_approved": 0,  # harness не фабрикует одобрение
    }


def build_report(results: Iterable[HarnessResult]) -> dict[str, Any]:
    """Полный отчёт по прогону: сводка + per-case статус. Без системного времени."""
    results = list(results)
    return {
        "harness": "calibration-harness/1.0.0",
        "summary": summarize_results(results),
        "cases": [
            {
                "case_id": r.case_id,
                "passed": r.passed,
                "rounds_used": len(r.rounds),
                "needs_expert_approval": r.needs_expert_approval,
                "errors": list(r.errors),
            }
            for r in results
        ],
    }


__all__ = [
    "AgentAdapter",
    "CASE_SCHEMA",
    "CASE_ID_RE",
    "HarnessError",
    "HarnessResult",
    "MAX_ANSWER_BYTES",
    "MODULE_ROOT",
    "RECORD_SCHEMA",
    "RECORD_ID_RE",
    "RoundRecord",
    "build_report",
    "check_answer_against_expected",
    "deterministic_id",
    "load_cases",
    "redact_text",
    "redact_tree",
    "run_case",
    "summarize_results",
    "validate_case",
    "validate_cases_file",
    "validate_record",
]
