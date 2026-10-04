# SPDX-License-Identifier: GPL-3.0-or-later
"""Клиент Crossref API (stdlib-only).

Запрос: ``https://api.crossref.org/works``. ``CROSSREF_MAILTO`` подставляется
только если задан в окружении.

ВАЖНО: Crossref отдаёт библиографические МЕТАДАННЫЕ. Наличие DOI/записи в
Crossref НЕ даёт права на скачивание полного текста. Поэтому ``license`` здесь
обычно пустой/``metadata-only``, и ``download.py`` такую строку отклонит как
не-redistributable.
"""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.parse import quote

from .http import get

BASE_URL = "https://api.crossref.org/works"
SERVICE = "crossref"


def _mailto() -> str | None:
    value = os.environ.get("CROSSREF_MAILTO", "").strip()
    return value or None


def _year(item: dict[str, Any]) -> int | None:
    for key in ("published-print", "published-online", "issued", "created"):
        block = item.get(key)
        if isinstance(block, dict):
            parts = block.get("date-parts")
            if parts and parts[0] and isinstance(parts[0][0], int):
                return parts[0][0]
    return None


def _title(item: dict[str, Any]) -> str | None:
    titles = item.get("title")
    if isinstance(titles, list) and titles:
        return titles[0]
    return None


def _license_id(item: dict[str, Any]) -> str | None:
    """Вернуть SPDX-подобный id только для явно свободных лицензий Crossref."""
    for entry in item.get("license") or []:
        url = str(entry.get("URL", "")).lower()
        if "creativecommons.org/publicdomain/zero" in url:
            return "cc0"
        if "creativecommons.org/licenses/by-sa" in url:
            return "cc-by-sa"
        if "creativecommons.org/licenses/by" in url:
            return "cc-by"
    return None


def normalize_item(item: dict[str, Any], *, domain: str, query: str) -> dict[str, Any]:
    """Преобразовать item из Crossref в канонического кандидата."""
    return {
        "service": SERVICE,
        "service_id": item.get("DOI"),
        "title": _title(item),
        "abstract": item.get("abstract"),
        "doi": item.get("DOI"),
        "year": _year(item),
        "oa_url": None,  # Crossref не отдаёт проверенный OA-URL
        "landing_url": item.get("URL"),
        "license": _license_id(item),
        "source_url": item.get("URL"),
        "publisher": item.get("publisher"),
        "is_oa": False,
        "domain": domain,
        "query": query,
        "provenance_service": "api.crossref.org",
    }


def search(
    query: str, *, domain: str, limit: int = 10, mailto: str | None = None
) -> list[dict[str, Any]]:
    """Найти работы в Crossref. Только метаданные; право на скачивание не даёт."""
    params: dict[str, Any] = {
        "query": query,
        "rows": max(1, min(int(limit), 100)),
    }
    contact = mailto or _mailto()
    if contact:
        params["mailto"] = contact
    body = get(BASE_URL, params=params)
    payload = json.loads(body.decode("utf-8"))
    items = (payload.get("message") or {}).get("items") or []
    return [normalize_item(item, domain=domain, query=query) for item in items[:limit]]


def canonical_query_url(query: str) -> str:
    return f"{BASE_URL}?query={quote(query)}"
