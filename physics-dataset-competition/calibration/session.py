#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Replayable JSONL-сессии экспертной калибровки (stdlib-only).

Сессия — отдельный append-only журнал, где эксперт скармливает агенту
статью/книгу, агент извлекает данные эксперимента, эксперт указывает явные
ошибки, агент исправляет до полного одобрения::

    task -> agent_answer -> expert_review -> correction -> ... -> final

Инварианты:
  * только стандартная библиотека (CI без тяжёлых зависимостей);
  * ``event_id`` детерминирован — SHA-256 от канонического содержимого события
    (без ``event_id``), поэтому один и тот же вход даёт один и тот же id;
  * журнал только дополняется: :class:`SessionWriter` открывает файл в режиме
    ``"a"`` и никогда не перезаписывает; повтор ``event_id`` отклоняется;
  * ``timestamp`` передаётся явно вызывающим (детерминизм, без системных часов);
  * очевидные секреты (HF/OpenAI/Anthropic/GitHub/Slack-токены, ``Bearer``,
    PEM-ключи, ``api_key=...``) вырезаются из строковых полей до записи;
  * валидная сессия обязана завершаться ``final`` с ``payload.expert_approved``
    ``true``.

Схема события — ``calibration/schema/session.schema.json``; CLI —
``scripts/calibration_session.py`` (команды ``init/append/validate/summary/
export``).
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

# Корень модуля: <repo>/physics-dataset-competition
MODULE_ROOT = Path(__file__).resolve().parent
DEFAULT_SCHEMA = MODULE_ROOT / "schema" / "session.schema.json"

ROLES = ("task", "agent_answer", "expert_review", "correction", "final")

SESSION_ID_RE = re.compile(r"^[A-Za-z0-9._-]{4,64}$")
EVENT_ID_RE = re.compile(r"^[0-9a-f]{16,64}$")
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

# --- редактирование секретов -------------------------------------------------
# Покрываем частые формы токенов. Порядок важен: сначала узкие префиксы,
# затем универсальный Bearer.
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
# Ключи, значения которых при аудите считаются чувствительными.
_SENSITIVE_KEYS = re.compile(
    r"(?i)(token|secret|password|passwd|pwd|api[_-]?key|authorization)"
)


def redact_text(text: str) -> str:
    """Вырезать очевидные токены/ключи из строки (идемпотентно)."""
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(_REDACTED, text)
    return text


def _redact_tree(value: Any) -> Any:
    """Рекурсивно отредактировать секреты в значениях по чувствительным ключам."""
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if isinstance(key, str) and _SENSITIVE_KEYS.search(key):
                out[key] = _REDACTED if item not in (None, "") else item
            else:
                out[key] = _redact_tree(item)
        return out
    if isinstance(value, list):
        return [_redact_tree(item) for item in value]
    return value


# --- детерминированные id ----------------------------------------------------


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def deterministic_event_id(event: dict[str, Any]) -> str:
    """Стабильный ``event_id`` — SHA-256 от события без поля ``event_id``."""
    body = {k: v for k, v in event.items() if k != "event_id"}
    return hashlib.sha256(_canonical(body).encode("utf-8")).hexdigest()


# --- сериализация / загрузка -------------------------------------------------


def dumps_event(event: dict[str, Any]) -> str:
    """Каноническая JSONL-строка события (стабильный порядок, UTF-8)."""
    return _canonical(event)


def load_session(path: str | Path) -> list[dict[str, Any]]:
    """Прочитать весь журнал сессии. Пустой/отсутствующий файл → ``[]``."""
    p = Path(path)
    if not p.is_file():
        return []
    events: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8-sig").splitlines():
        if line.strip():
            events.append(json.loads(line))
    return events


# --- структурная валидация (эквивалент session.schema.json) ------------------


def _is_obj(x: Any) -> bool:
    return isinstance(x, dict)


def _check_required(
    obj: Any, field: str, required: list[str], errors: list[str]
) -> None:
    if not _is_obj(obj):
        errors.append(f"{field}: должен быть объектом")
        return
    for key in required:
        if key not in obj:
            errors.append(f"{field}: отсутствует обязательное поле '{key}'")


def _validate_source(source: Any, errors: list[str]) -> None:
    _check_required(source, "source", ["source_type", "title", "rights"], errors)
    if not _is_obj(source):
        return
    st = source.get("source_type")
    if st not in {
        "book",
        "article",
        "report",
        "dataset",
        "standard",
        "patent",
        "thesis",
        "other",
    }:
        errors.append(f"source.source_type недопустим: {st!r}")
    if not isinstance(source.get("title"), str) or not source.get("title"):
        errors.append("source.title должен быть непустой строкой")
    excerpt = source.get("excerpt")
    if excerpt is not None and (not isinstance(excerpt, str) or len(excerpt) > 2000):
        errors.append("source.excerpt должен быть строкой не длиннее 2000 символов")
    rights = source.get("rights")
    _check_required(
        rights, "source.rights", ["reusable", "redistributable", "basis"], errors
    )
    if _is_obj(rights):
        for key in ("reusable", "redistributable"):
            if not isinstance(rights.get(key), bool):
                errors.append(f"source.rights.{key} должен быть boolean")
        if not isinstance(rights.get("basis"), str) or not rights.get("basis"):
            errors.append("source.rights.basis должен быть непустой строкой")
    prov = source.get("provenance")
    if prov is not None and _is_obj(prov):
        sha = prov.get("sha256")
        if sha is not None and not SHA256_RE.match(str(sha)):
            errors.append(
                "source.provenance.sha256 должен быть hex-строкой из 64 символов"
            )
    # Сырые бинарники запрещены.
    if isinstance(source.get("url"), str) and re.search(
        r"\.(pdf|zip|png|jpe?g|tiff?|djvu)(\?|$)", source["url"], re.I
    ):
        errors.append(
            "source.url указывает на сырой бинарник — храните только метаданные"
        )


def _validate_payload_role(role: Any, payload: Any, errors: list[str]) -> None:
    if not _is_obj(payload):
        errors.append("payload: должен быть объектом")
        return
    if role == "task" and not payload.get("prompt"):
        errors.append("payload.prompt обязателен для role=task")
    if role == "agent_answer" and not _is_obj(payload.get("agent_answer")):
        errors.append("payload.agent_answer обязателен для role=agent_answer")
    if role == "expert_review" and not payload.get("expert_analysis"):
        errors.append("payload.expert_analysis обязателен для role=expert_review")
    if role == "correction" and not _is_obj(payload.get("corrected_answer")):
        errors.append("payload.corrected_answer обязателен для role=correction")
    if role == "final" and payload.get("expert_approved") is not True:
        errors.append("payload.expert_approved обязан быть true для role=final")


def validate_event(event: Any) -> list[str]:
    """Проверить одно событие по схеме. Пустой список = валидно."""
    errors: list[str] = []
    if not _is_obj(event):
        return ["событие: должно быть JSON-объектом"]

    _check_required(
        event,
        "event",
        ["session_id", "event_id", "round", "role", "timestamp", "source", "payload"],
        errors,
    )

    sid = event.get("session_id")
    if not isinstance(sid, str) or not SESSION_ID_RE.match(sid or ""):
        errors.append(f"session_id недопустим: {sid!r}")

    eid = event.get("event_id")
    if not isinstance(eid, str) or not EVENT_ID_RE.match(eid or ""):
        errors.append(f"event_id недопустим: {eid!r}")

    rnd = event.get("round")
    if not isinstance(rnd, int) or isinstance(rnd, bool) or rnd < 0:
        errors.append(f"round должен быть целым >= 0: {rnd!r}")

    role = event.get("role")
    if role not in ROLES:
        errors.append(f"role недопустим: {role!r} (ожидается один из {list(ROLES)})")

    ts = event.get("timestamp")
    if not isinstance(ts, str) or not re.match(
        r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", ts or ""
    ):
        errors.append(f"timestamp должен быть ISO-8601: {ts!r}")

    _validate_source(event.get("source"), errors)
    _validate_payload_role(role, event.get("payload"), errors)
    return errors


def check_sequence(events: list[dict[str, Any]]) -> list[str]:
    """Проверить порядок ролей и завершение одобренным ``final``."""
    errors: list[str] = []
    if not events:
        return ["пустая сессия: нет событий"]

    expected = ["task"]
    for i, event in enumerate(events):
        role = event.get("role")
        if role not in expected:
            at = expected[-1]
            errors.append(
                f"событие #{i + 1}: недопустимый порядок role={role!r} "
                f"(ожидалось '{at}' при последовательности {expected})"
            )
            return errors
        if role == "task":
            expected = ["agent_answer"]
        elif role == "agent_answer":
            expected = ["expert_review"]
        elif role == "expert_review":
            approved = (event.get("payload") or {}).get("expert_approved") is True
            expected = ["final"] if approved else ["correction"]
        elif role == "correction":
            expected = ["agent_answer"]

    last = events[-1]
    if last.get("role") != "final":
        errors.append(
            f"сессия не завершена: последнее событие role={last.get('role')!r}, ожидался 'final'"
        )
    elif (last.get("payload") or {}).get("expert_approved") is not True:
        errors.append("final: payload.expert_approved обязан быть true")
    return errors


def validate_session(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Полная проверка сессии: схема каждого события + порядок + одобрение.

    Возвращает сводку ``{ok, events, errors, session_id}``. ``ok`` — истина
    только если ошибок нет и финальное событие одобрено.
    """
    errors: list[str] = []
    seen: set[str] = set()
    session_id = None
    for i, event in enumerate(events):
        if _is_obj(event) and event.get("session_id") and session_id is None:
            session_id = event.get("session_id")
        for err in validate_event(event):
            errors.append(f"событие #{i + 1}: {err}")
        eid = event.get("event_id") if _is_obj(event) else None
        if isinstance(eid, str):
            if eid in seen:
                errors.append(f"событие #{i + 1}: повтор event_id {eid!r}")
            seen.add(eid)

    errors.extend(check_sequence(events))
    return {
        "ok": not errors,
        "events": len(events),
        "session_id": session_id,
        "errors": errors,
    }


def summarize(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Сводка прогресса сессии (раунды, роли, одобрение)."""
    rounds = [int(e["round"]) for e in events if isinstance(e.get("round"), int)]
    roles = [e.get("role") for e in events]
    last = events[-1] if events else {}
    approved = (
        bool((last.get("payload") or {}).get("expert_approved") is True)
        and last.get("role") == "final"
    )
    corrections = roles.count("correction")
    return {
        "session_id": (events[0].get("session_id") if events else None),
        "events": len(events),
        "rounds": (max(rounds) + 1) if rounds else 0,
        "corrections": corrections,
        "roles": roles,
        "expert_approved": approved,
        "complete": approved and bool(events),
    }


class SessionWriter:
    """Append-only писатель одного JSONL-журнала сессии.

    Один писатель = одна сессия (``session_id`` фиксирован в конструкторе).
    ``append`` отклоняет невалидные события, повтор ``event_id`` и запись
    после одобренного ``final``.
    """

    def __init__(self, path: str | Path, session_id: str) -> None:
        if not SESSION_ID_RE.match(str(session_id)):
            raise ValueError(f"session_id недопустим: {session_id!r}")
        self.path = Path(path)
        self.session_id = session_id
        self._events = load_session(self.path)
        if self._events and self._events[0].get("session_id") != session_id:
            raise ValueError(
                f"файл {self.path} принадлежит сессии "
                f"{self._events[0].get('session_id')!r}, а не {session_id!r}"
            )
        self._ids = {e.get("event_id") for e in self._events}
        if self._events:
            check = validate_session(self._events)
            if not check["ok"] and "не завершена" not in " ".join(check["errors"]):
                raise ValueError(
                    "существующий журнал невалиден: " + "; ".join(check["errors"])
                )

    @property
    def events(self) -> list[dict[str, Any]]:
        return list(self._events)

    def next_round(self) -> int:
        """Следующий номер раунда.

        * нет событий → 0 (постановка задачи);
        * после ``task`` → 1 (первый ответ агента);
        * внутри раунда → текущий раунд (ответ/разбор/исправление);
        * после ``correction`` → следующий раунд.
        """
        if not self._events:
            return 0
        rounds = [
            int(e["round"]) for e in self._events if isinstance(e.get("round"), int)
        ]
        current = max(rounds) if rounds else 0
        last_role = self._events[-1].get("role")
        if last_role == "task":
            return 1
        if last_role == "correction":
            return current + 1
        return current

    def append(
        self,
        *,
        role: str,
        timestamp: str,
        source: dict[str, Any],
        payload: dict[str, Any],
        round: int | None = None,  # noqa: A002 - публичное имя по схеме
    ) -> dict[str, Any]:
        """Дописать одно событие. Секреты вырезаются до записи."""
        if role not in ROLES:
            raise ValueError(f"role недопустим: {role!r}")
        self._ensure_open(role)
        rnd = self.next_round() if round is None else round

        event: dict[str, Any] = {
            "session_id": self.session_id,
            "round": rnd,
            "role": role,
            "timestamp": timestamp,
            "source": _redact_tree(source),
            "payload": _redact_tree(payload),
        }
        event["event_id"] = deterministic_event_id(event)

        if event["event_id"] in self._ids:
            raise ValueError(f"повтор event_id: {event['event_id']}")
        errors = validate_event(event)
        if errors:
            raise ValueError("невалидное событие: " + "; ".join(errors))

        line = dumps_event(event)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(line + "\n")
        self._events.append(event)
        self._ids.add(event["event_id"])
        return event

    def _ensure_open(self, role: str) -> None:
        if role == "task" and self._events:
            raise ValueError("task может быть только первым событием сессии")
        if self._events and self._events[-1].get("role") == "final":
            raise ValueError(
                "сессия уже завершена одобренным final — дописывать нельзя"
            )
        if self._events and role == "final":
            last = self._events[-1]
            approved = (last.get("payload") or {}).get("expert_approved") is True
            if last.get("role") != "expert_review" or not approved:
                raise ValueError(
                    "final допустим только сразу после expert_review с expert_approved=true"
                )


def export_publishable(
    events: list[dict[str, Any]], *, max_excerpt: int = 200
) -> list[dict[str, Any]]:
    """Очистить сессию для публикации: без локальных путей и полного текста.

    * ``source.excerpt`` усекается до ``max_excerpt`` символов;
    * ``source`` теряет поля с локальными путями/хэшами, если они похожи на
      артефакты рабочей машины (``path``, ``file``, ``local`` и т.п.);
    * строковые поля повторно проходят редактирование секретов.
    """
    out: list[dict[str, Any]] = []
    for event in events:
        clean = json.loads(json.dumps(event, ensure_ascii=False))
        source = clean.get("source")
        if _is_obj(source):
            if (
                isinstance(source.get("excerpt"), str)
                and len(source["excerpt"]) > max_excerpt
            ):
                source["excerpt"] = source["excerpt"][:max_excerpt] + "…"
            for key in list(source.keys()):
                if re.search(r"(?i)(local_?path|file_?path|path|workdir|abspath)", key):
                    source.pop(key, None)
        clean = _redact_tree(clean)
        out.append(clean)
    return out


__all__ = [
    "DEFAULT_SCHEMA",
    "EVENT_ID_RE",
    "MODULE_ROOT",
    "ROLES",
    "SESSION_ID_RE",
    "SessionWriter",
    "check_sequence",
    "deterministic_event_id",
    "dumps_event",
    "export_publishable",
    "load_session",
    "redact_text",
    "summarize",
    "validate_event",
    "validate_session",
]
