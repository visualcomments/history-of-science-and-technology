# SPDX-License-Identifier: GPL-3.0-or-later
"""Клиент arXiv API (stdlib-only, Atom XML через ElementTree).

Запрос: ``https://export.arxiv.org/api/query``. Ответ — Atom XML; разбирается
стандартным ``xml.etree.ElementTree``.

Вежливость arXiv: минимум 3 секунды между ПОСЛЕДОВАТЕЛЬНЫМИ запросами
(мульти-страничный поиск). Одиночный запрос НЕ спит. Пагинация — по
``start``/``max_results``; задержка вставляется только перед запросами
со смещением ``start > 0``.

Метаданные, а не полный текст: возвращаем PDF-ссылку, но решение о загрузке
принимает ``download.py`` через ``rights.classifier``.
"""

from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import quote

from .http import get

BASE_URL = "https://export.arxiv.org/api/query"
PDF_BASE = "https://arxiv.org/pdf"
SERVICE = "arxiv"
POLITE_DELAY_SECONDS = 3.0

ATOM = "{http://www.w3.org/2005/Atom}"
ARXIV = "{http://arxiv.org/schemas/atom}"

# arXiv по умолчанию не отдаёт SPDX-лицензию. Если ``arxiv:license`` есть —
# маппим; иначе None (права неизвестны → metadata-only).
_LICENSE_MAP = {
    "http://creativecommons.org/publicdomain/zero/1.0/": "cc0",
    "http://creativecommons.org/licenses/by/4.0/": "cc-by-4.0",
    "http://creativecommons.org/licenses/by-sa/4.0/": "cc-by-sa-4.0",
    "http://creativecommons.org/licenses/by-nc-sa/4.0/": None,
    "http://creativecommons.org/licenses/by-nc-nd/4.0/": None,
}


def _text(node: ET.Element | None) -> str | None:
    if node is None or node.text is None:
        return None
    return " ".join(node.text.split()) or None


def _entry_id(entry: ET.Element) -> str | None:
    raw = _text(entry.find(f"{ATOM}id"))
    if not raw:
        return None
    # http://arxiv.org/abs/2401.00001v1 -> 2401.00001v1
    return raw.rstrip("/").rsplit("/", 1)[-1]


def _pdf_url(entry: ET.Element) -> str | None:
    for link in entry.findall(f"{ATOM}link"):
        if link.get("title") == "pdf" or link.get("type") == "application/pdf":
            href = link.get("href")
            if href:
                return href
    ident = _entry_id(entry)
    return f"{PDF_BASE}/{ident}" if ident else None


def _license(entry: ET.Element) -> str | None:
    node = entry.find(f"{ARXIV}license")
    href = node.get("href") if node is not None else None
    if href:
        return _LICENSE_MAP.get(href, None)
    text = _text(node)
    if text:
        lowered = text.lower()
        if "public domain" in lowered or "cc0" in lowered:
            return "cc0"
        if "by-sa" in lowered:
            return "cc-by-sa"
        if "by" in lowered:
            return "cc-by"
    return None


def _year(entry: ET.Element) -> int | None:
    published = _text(entry.find(f"{ATOM}published")) or _text(
        entry.find(f"{ATOM}updated")
    )
    if published and len(published) >= 4 and published[:4].isdigit():
        return int(published[:4])
    return None


def _authors(entry: ET.Element) -> list[str]:
    names = []
    for author in entry.findall(f"{ATOM}author"):
        name = _text(author.find(f"{ATOM}name"))
        if name:
            names.append(name)
    return names


def normalize_entry(entry: ET.Element, *, domain: str, query: str) -> dict[str, Any]:
    """Преобразовать Atom ``<entry>`` в канонического кандидата."""
    ident = _entry_id(entry)
    return {
        "service": SERVICE,
        "service_id": ident,
        "title": _text(entry.find(f"{ATOM}title")),
        "abstract": _text(entry.find(f"{ATOM}summary")),
        "doi": _text(entry.find(f"{ARXIV}doi")),
        "year": _year(entry),
        "oa_url": _pdf_url(entry),
        "landing_url": _text(entry.find(f"{ATOM}id")),
        "license": _license(entry),
        "source_url": "https://arxiv.org",
        "publisher": "arXiv",
        "is_oa": True,
        "authors": _authors(entry),
        "domain": domain,
        "query": query,
        "provenance_service": "export.arxiv.org",
    }


def parse_feed(xml_bytes: bytes, *, domain: str, query: str) -> list[dict[str, Any]]:
    """Разобрать Atom-фид в список кандидатов (без сети)."""
    root = ET.fromstring(xml_bytes)
    return [
        normalize_entry(entry, domain=domain, query=query)
        for entry in root.findall(f"{ATOM}entry")
    ]


def search(
    query: str,
    *,
    domain: str,
    limit: int = 10,
    page_size: int = 20,
    sleep: Any = time.sleep,
) -> list[dict[str, Any]]:
    """Найти работы в arXiv.

    Поддерживает пагинацию: между страницами (``start > 0``) спит
    ``POLITE_DELAY_SECONDS``. Одиночный запрос не спит.
    """
    out: list[dict[str, Any]] = []
    start = 0
    page = max(1, min(page_size, 100))
    while len(out) < limit:
        params = {
            "search_query": f"all:{query}",
            "start": start,
            "max_results": page,
        }
        if start > 0:
            sleep(POLITE_DELAY_SECONDS)
        body = get(BASE_URL, params=params)
        page_results = parse_feed(body, domain=domain, query=query)
        if not page_results:
            break
        out.extend(page_results)
        if len(page_results) < page:
            break
        start += page
    return out[:limit]


def canonical_query_url(query: str) -> str:
    return f"{BASE_URL}?search_query=all:{quote(query)}"
