# SPDX-License-Identifier: GPL-3.0-or-later
"""Append-only JSONL-журнал происхождения (W3C PROV-O, DESIGN §4.4).

Каждый шаг пайплайна (collect → ocr → digitize → validate → publish) пишет
запись вида::

    {"activity": "...", "agent_role_id": "R01", "retrieved_at": "...",
     "method": "...", "sha256": "...", "input_sha256": "...",
     "output_sha256": "..."}

Журнал только дополняется: ``ProvenanceWriter`` открывает файл в режиме ``"a"``
и никогда не перезаписывает содержимое. Детерминированность: ``retrieved_at``
явно передаётся вызывающим (не берётся из системных часов), порядок ключей
фиксирован, JSON сериализуется с ``sort_keys=False``.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

REQUIRED_KEYS = [
    "activity",
    "agent_role_id",
    "retrieved_at",
    "method",
    "sha256",
    "input_sha256",
    "output_sha256",
]

# Разрешённые PROV-activity (по DESIGN §4.2/§4.4).
ACTIVITIES = {"collect", "ocr", "digitize", "validate", "normalize", "publish"}


def record_sha256(data: bytes | str) -> str:
    """SHA-256 от байтов/строки (UTF-8). Детерминировано."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def file_sha256(path: str | Path) -> str:
    """SHA-256 содержимого файла (потоково, без загрузки целиком в память)."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


class ProvenanceWriter:
    """Append-only писатель журнала провенанса."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def append(
        self,
        *,
        activity: str,
        agent_role_id: str,
        retrieved_at: str,
        method: str,
        sha256: str = "",
        input_sha256: str = "",
        output_sha256: str = "",
    ) -> dict[str, Any]:
        """Добавить запись журнала. Возвращает записанный объект.

        ``sha256`` — хэш самого артефакта записи; ``input_sha256``/``output_sha256``
        — хэши входа/выхода шага. Все поля обязательны для трассируемости.
        """
        if activity not in ACTIVITIES:
            raise ValueError(
                f"activity недопустима: {activity!r} (ожидается одно из {sorted(ACTIVITIES)})"
            )
        entry: dict[str, Any] = {
            "activity": activity,
            "agent_role_id": agent_role_id,
            "retrieved_at": retrieved_at,
            "method": method,
            "sha256": sha256,
            "input_sha256": input_sha256,
            "output_sha256": output_sha256,
        }
        for key in REQUIRED_KEYS:
            if not isinstance(entry[key], str) or not entry[key]:
                raise ValueError(f"поле {key!r} должно быть непустой строкой")
        line = json.dumps(entry, ensure_ascii=False, sort_keys=False)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(line + "\n")
        return entry

    def read_all(self) -> list[dict[str, Any]]:
        """Прочитать весь журнал (для тестов/аудита)."""
        if not self.path.is_file():
            return []
        records: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(json.loads(line))
        return records
