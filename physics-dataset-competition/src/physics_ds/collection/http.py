# SPDX-License-Identifier: GPL-3.0-or-later
"""Небольшой HTTP-клиент на urllib (stdlib-only).

Только GET, таймаут, вежливый User-Agent, ограничение размера ответа и
повтор при транзиентных 429/5xx с учётом ``Retry-After``.

Жёсткие границы (DESIGN §5.3, §8):
  * никаких заголовков с credentials/токенами;
  * никакого обхода robots.txt, paywall или капчи;
  * только https для загрузки тела (проверяется вызывающим кодом);
  * ограничение размера защищает от случайной выкачки гигантских файлов.

Модуль не логирует URL с параметрами авторизации (их тут и не бывает) и не
печатает тела ответов.
"""

from __future__ import annotations

import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

USER_AGENT = "physics-ds-collect/1.0 (+https://github.com/visualcomments; educational; contact via OPENALEX_MAILTO)"

DEFAULT_TIMEOUT = 30.0
DEFAULT_MAX_BYTES = 8 * 1024 * 1024  # 8 MiB
DEFAULT_RETRIES = 3
RETRY_STATUSES = {429, 500, 502, 503, 504}


class HttpError(RuntimeError):
    """Ошибка HTTP-запроса (без утечки секретов)."""


def _sleep(seconds: float) -> None:
    if seconds > 0:
        time.sleep(seconds)


def get(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    max_bytes: int = DEFAULT_MAX_BYTES,
    retries: int = DEFAULT_RETRIES,
    max_retry_after: float = 30.0,
    extra_headers: dict[str, str] | None = None,
    sleep: Any = _sleep,
) -> bytes:
    """Выполнить GET и вернуть тело как bytes.

    ``sleep`` можно подменить в тестах, чтобы не ждать реально.
    Повторяет только транзиентные статусы (429/5xx), honor ``Retry-After``.
    Кидает :class:`HttpError` при неудаче (с кодом статуса, без тела).
    """
    if params:
        query = urllib.parse.urlencode(params)
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}{query}"

    headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    if extra_headers:
        # Разрешаем только безвредные заголовки; credentials сюда не попадают.
        headers.update(extra_headers)

    last_status: int | None = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
                status = getattr(resp, "status", 200)
                if status in RETRY_STATUSES and attempt < retries:
                    last_status = status
                    _sleep(_retry_delay(resp, attempt, max_retry_after, sleep))
                    continue
                data = resp.read(max_bytes + 1)
                if len(data) > max_bytes:
                    raise HttpError(
                        f"ответ превышает лимит {max_bytes} байт (size-limit)"
                    )
                return data
        except urllib.error.HTTPError as exc:
            last_status = exc.code
            if exc.code in RETRY_STATUSES and attempt < retries:
                _sleep(_retry_delay(exc, attempt, max_retry_after, sleep))
                continue
            raise HttpError(f"HTTP {exc.code} для {_redact(url)}") from None
        except urllib.error.URLError as exc:
            if attempt < retries:
                _sleep(sleep(min(2.0**attempt, max_retry_after)))
                continue
            raise HttpError(
                f"сетевая ошибка для {_redact(url)}: {exc.reason}"
            ) from None

    raise HttpError(
        f"не удалось получить {_redact(url)} (последний статус {last_status})"
    )


def _retry_delay(resp: Any, attempt: int, max_retry_after: float, sleep: Any) -> float:
    retry_after = None
    headers = getattr(resp, "headers", None)
    if headers is not None:
        retry_after = headers.get("Retry-After")
    if retry_after:
        try:
            return sleep(min(float(retry_after), max_retry_after))
        except ValueError:
            pass
    return sleep(min(2.0**attempt, max_retry_after))


def _redact(url: str) -> str:
    """Убрать query-строку из URL для безопасного сообщения об ошибке."""
    parsed = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
