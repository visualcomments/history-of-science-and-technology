#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Адаптеры агента для harness калибровки (stdlib-only, без скрытой сети).

Контракт: ``respond(prompt, context) -> dict`` (см. ``harness.core.AgentAdapter``).

* :class:`RecordingAdapter` — детерминированный playback заготовленных
  ответов из JSONL (для тестов и ``run --responses``); без сети и процессов.
* :class:`OpenCodeAdapter` — вызывает **локальную команду/процесс**, только
  если это явно сконфигурировано вызывающим. Никаких скрытых сетевых/API
  вызовов; токены из окружения не передаются ни в промпт, ни в аргументы
  процесса, ни в вывод. Есть таймаут и лимит размера вывода.

Ошибки исполнения → :class:`harness.core.HarnessError` с kind
``adapter``/``timeout``/``size``/``config``.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from core import HarnessError, redact_text, redact_tree

# Лимиты по умолчанию (переопределяются в конструкторе OpenCodeAdapter).
DEFAULT_TIMEOUT_S = 30.0
DEFAULT_MAX_OUTPUT_BYTES = 512 * 1024


class RecordingAdapter:
    """Проигрывает заготовленные ответы по порядку (детерминированный playback).

    ``responses`` — список JSON-объектов (например, строки JSONL-файла).
    Если ответов меньше, чем обращений, или объект невалиден → HarnessError
    (kind ``adapter``/``config``). Опционально проверяет, что присланный
    промпт совпадает с ожидаемым (``expect_prompts``).
    """

    def __init__(
        self,
        responses: list[dict[str, Any]] | None = None,
        *,
        responses_path: str | Path | None = None,
        expect_prompts: list[str] | None = None,
    ) -> None:
        if responses is None and responses_path is None:
            raise HarnessError(
                "RecordingAdapter: нужен responses или responses_path", kind="config"
            )
        if responses is None:
            p = Path(responses_path)  # type: ignore[arg-type]
            if not p.is_file():
                raise HarnessError(f"файл ответов не найден: {p}", kind="config")
            responses = []
            for lineno, line in enumerate(
                p.read_text(encoding="utf-8-sig").splitlines(), 1
            ):
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise HarnessError(
                        f"файл ответов, строка {lineno}: невалидный JSON: {exc}",
                        kind="config",
                    ) from exc
                if not isinstance(obj, dict):
                    raise HarnessError(
                        f"файл ответов, строка {lineno}: должен быть JSON-объектом",
                        kind="config",
                    )
                responses.append(obj)
        self._responses: list[dict[str, Any]] = list(responses)
        self._expect_prompts = list(expect_prompts) if expect_prompts else None
        self._index = 0
        self.calls: list[dict[str, Any]] = []

    def respond(self, prompt: str, context: dict[str, Any]) -> dict[str, Any]:
        if self._index >= len(self._responses):
            raise HarnessError(
                f"RecordingAdapter: ответы закончились (запрошен #{self._index + 1})",
                kind="adapter",
            )
        if self._expect_prompts is not None:
            want = (
                self._expect_prompts[self._index]
                if self._index < len(self._expect_prompts)
                else self._expect_prompts[-1]
            )
            if redact_text(prompt) != redact_text(want):
                raise HarnessError(
                    f"RecordingAdapter: промпт #{self._index + 1} не совпал с ожидаемым",
                    kind="adapter",
                )
        answer = self._responses[self._index]
        self._index += 1
        self.calls.append({"prompt": prompt, "context": context, "answer": answer})
        return answer

    @property
    def calls_made(self) -> int:
        return self._index


class OpenCodeAdapter:
    """Вызывает явно сконфигурированную локальную команду (без сети).

    Промпт и контекст передаются процессу **только через stdin** как
    канонический JSON-документ::

        {"prompt": "...", "context": {...}}

    Процесс обязан напечатать в stdout один JSON-объект.

    Границы безопасности:
      * никакой сети из самого адаптера; что делает дочерний процесс —
        ответственность того, кто его сконфигурировал;
      * переменные окружения **не** пробрасываются: дочерний процесс получает
        пустое окружение, если ``env_whitelist`` не задан явно; значения с
        чувствительными именами (``*TOKEN*``, ``*KEY*``, ``*SECRET*`` …)
        не передаются никогда;
      * промпт/контекст проходят редактирование секретов перед записью в stdin;
      * таймаут (``timeout_s``) и лимит размера вывода (``max_output_bytes``)
        обрезают зависшие/раздутые процессы.

    Args:
        command: список аргументов локальной команды (обязателен явно).
        cwd: рабочая директория процесса (по умолчанию — текущая).
        timeout_s: таймаут в секундах.
        max_output_bytes: максимальный размер stdout.
        env_whitelist: явный белый список имён переменных окружения для
            передачи дочернему процессу (чувствительные имена игнорируются).
    """

    _SENSITIVE_ENV = ("token", "key", "secret", "password", "passwd", "pwd", "auth")

    def __init__(
        self,
        command: list[str],
        *,
        cwd: str | Path | None = None,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
        env_whitelist: list[str] | None = None,
    ) -> None:
        if not command or not all(isinstance(a, str) and a for a in command):
            raise HarnessError(
                "OpenCodeAdapter: command должен быть непустым списком строк",
                kind="config",
            )
        if timeout_s <= 0:
            raise HarnessError(
                "OpenCodeAdapter: timeout_s должен быть > 0", kind="config"
            )
        if max_output_bytes <= 0:
            raise HarnessError(
                "OpenCodeAdapter: max_output_bytes должен быть > 0", kind="config"
            )
        self._command = list(command)
        self._cwd = str(cwd) if cwd is not None else None
        self._timeout_s = float(timeout_s)
        self._max_output_bytes = int(max_output_bytes)
        self._env_whitelist = list(env_whitelist) if env_whitelist else None
        self.calls: list[dict[str, Any]] = []

    def _child_env(self) -> dict[str, str] | None:
        if self._env_whitelist is None:
            return None
        env: dict[str, str] = {}
        for name in self._env_whitelist:
            if not isinstance(name, str):
                continue
            low = name.lower()
            if any(s in low for s in self._SENSITIVE_ENV):
                continue  # чувствительные имена не пробрасываются никогда
            value = _env_get(name)
            if value is not None:
                env[name] = value
        return env

    def respond(self, prompt: str, context: dict[str, Any]) -> dict[str, Any]:
        payload = json.dumps(
            {"prompt": redact_text(prompt), "context": redact_tree(context)},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        payload_bytes = payload.encode("utf-8")
        try:
            proc = subprocess.run(
                self._command,
                input=payload_bytes,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=self._timeout_s,
                cwd=self._cwd,
                env=self._child_env(),
            )
        except subprocess.TimeoutExpired as exc:
            raise HarnessError(
                f"команда превысила таймаут {self._timeout_s}s: {self._command!r}",
                kind="timeout",
            ) from exc
        except FileNotFoundError as exc:
            raise HarnessError(
                f"команда не найдена: {self._command!r}", kind="config"
            ) from exc
        except OSError as exc:
            raise HarnessError(
                f"ошибка запуска команды {self._command!r}: {exc}", kind="config"
            ) from exc

        if proc.returncode != 0:
            stderr_tail = proc.stderr.decode("utf-8", "replace")[:500]
            raise HarnessError(
                f"команда вернула код {proc.returncode}: {stderr_tail}",
                kind="adapter",
            )

        stdout = proc.stdout
        if len(stdout) > self._max_output_bytes:
            raise HarnessError(
                f"вывод команды превышает лимит ({len(stdout)} байт > "
                f"{self._max_output_bytes})",
                kind="size",
            )
        try:
            text = stdout.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise HarnessError(
                f"вывод команды не UTF-8: {exc}", kind="adapter"
            ) from exc
        try:
            answer = json.loads(text)
        except json.JSONDecodeError as exc:
            raise HarnessError(
                f"вывод команды не является одним JSON-документом: {exc}",
                kind="adapter",
            ) from exc
        if not isinstance(answer, dict):
            raise HarnessError(
                "вывод команды должен быть JSON-объектом", kind="adapter"
            )
        self.calls.append(
            {"command": self._command, "prompt": prompt, "answer": answer}
        )
        return answer


def _env_get(name: str) -> str | None:
    import os

    value = os.environ.get(name)
    return value if value else None


def adapter_from_config(config: dict[str, Any]) -> RecordingAdapter | OpenCodeAdapter:
    """Собрать адаптер из JSON-конфига (для CLI ``run``).

    Поддерживаемые виды:
      * ``{"kind": "recording", "responses_path": "..."}`` — playback JSONL;
      * ``{"kind": "command", "command": [...], "timeout_s": 30,
           "max_output_bytes": 524288, "cwd": "...", "env_whitelist": [...]}``
        — явный локальный процесс (по умолчанию окружение не передаётся).
    """
    if not isinstance(config, dict):
        raise HarnessError("конфиг адаптера должен быть JSON-объектом", kind="config")
    kind = config.get("kind")
    if kind == "recording":
        return RecordingAdapter(responses_path=config.get("responses_path"))
    if kind == "command":
        return OpenCodeAdapter(
            list(config.get("command") or []),
            cwd=config.get("cwd"),
            timeout_s=float(config.get("timeout_s", DEFAULT_TIMEOUT_S)),
            max_output_bytes=int(
                config.get("max_output_bytes", DEFAULT_MAX_OUTPUT_BYTES)
            ),
            env_whitelist=config.get("env_whitelist"),
        )
    raise HarnessError(
        f"неизвестный kind адаптера: {kind!r} (ожидается recording|command)",
        kind="config",
    )


def load_responses_jsonl(path: str | Path) -> list[dict[str, Any]]:
    """Прочитать JSONL-файл ответов (каждая строка — JSON-объект)."""
    adapter = RecordingAdapter(responses_path=path)
    return list(adapter._responses)


if __name__ == "__main__":  # pragma: no cover - ручная утилита
    print(
        "Это библиотека адаптеров; используйте harness/run.py",
        file=sys.stderr,
    )
    raise SystemExit(2)
