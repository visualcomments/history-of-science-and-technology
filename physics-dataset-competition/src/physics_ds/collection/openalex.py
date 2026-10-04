# SPDX-License-Identifier: GPL-3.0-or-later
"""Клиент OpenAlex API (stdlib-only).

Поиск работ: ``https://api.openalex.org/works``. ``OPENALEX_MAILTO``
подставляется только если задан в окружении (вежливый пул, не секрет).

Кандидат нормализуется в общий формат манифеста (см. ``manifest.py``):
title, DOI, year, ``oa_url`` (best_oa_location), license, source URL.

Метаданные, а не полный текст: этот модуль НИЧЕГО не скачивает. Решение о
загрузке принимает ``download.py`` через ``rights.classifier``.
"""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.parse import quote

from .http import get

BASE_URL = "https://api.openalex.org/works"
SERVICE = "openalex"

# Лицензии OpenAlex → SPDX-подобные идентификаторы, которые понимает classifier.
_LICENSE_MAP = {
    "cc0": "cc0",
    "cc-by": "cc-by",
    "cc-by-4.0": "cc-by",
    "cc-by-sa": "cc-by-sa",
    "cc-by-sa-4.0": "cc-by-sa",
    "public-domain": "public-domain",
}


def _mailto() -> str | None:
    value = os.environ.get("OPENALEX_MAILTO", "").strip()
    return value or None


def _invert_abstract(inv: Any) -> str | None:
    if not isinstance(inv, dict):
        return None
    positions: list[tuple[int, str]] = []
    for word, idxs in inv.items():
        for i in idxs:
            positions.append((i, word))
    if not positions:
        return None
    positions.sort()
    return " ".join(w for _, w in positions)


def _license_from_work(
    work: dict[str, Any], location: dict[str, Any] | None
) -> str | None:
    if location:
        lic = location.get("license")
        if lic:
            return _LICENSE_MAP.get(str(lic).lower(), str(lic))
    return None


def normalize_work(work: dict[str, Any], *, domain: str, query: str) -> dict[str, Any]:
    """Преобразовать work из OpenAlex в канонического кандидата."""
    primary = work.get("primary_location") or {}
    best_oa = work.get("best_oa_location") or primary
    source = (best_oa or {}).get("source") or {}
    oa_url = best_oa.get("pdf_url") or best_oa.get("landing_page_url")
    license_id = _license_from_work(work, best_oa) or _license_from_work(work, primary)
    return {
        "service": SERVICE,
        "service_id": work.get("id"),
        "title": work.get("title") or work.get("display_name"),
        "abstract": _invert_abstract(work.get("abstract_inverted_index")),
        "doi": work.get("doi"),
        "year": work.get("publication_year"),
        "oa_url": oa_url,
        "landing_url": (best_oa or {}).get("landing_page_url")
        or primary.get("landing_page_url"),
        "license": license_id,
        "source_url": source.get("homepage_url")
        or (work.get("primary_location") or {}).get("landing_page_url"),
        "publisher": source.get("display_name")
        or (work.get("host_venue") or {}).get("display_name"),
        "is_oa": bool(work.get("open_access", {}).get("is_oa")),
        "domain": domain,
        "query": query,
        "provenance_service": "openalex.org",
    }


def search(
    query: str, *, domain: str, limit: int = 10, mailto: str | None = None
) -> list[dict[str, Any]]:
    """Найти работы в OpenAlex. Метаданные only; сеть — один GET."""
    params: dict[str, Any] = {
        "search": query,
        "per-page": max(1, min(int(limit), 200)),
    }
    contact = mailto or _mailto()
    if contact:
        params["mailto"] = contact
    body = get(BASE_URL, params=params)
    payload = json.loads(body.decode("utf-8"))
    results = payload.get("results") or []
    out: list[dict[str, Any]] = []
    for work in results:
        out.append(normalize_work(work, domain=domain, query=query))
    return out[:limit]


def canonical_query_url(query: str) -> str:
    """URL запроса для отображения (без секретов)."""
    return f"{BASE_URL}?search={quote(query)}"
