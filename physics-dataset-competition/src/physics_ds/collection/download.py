# SPDX-License-Identifier: GPL-3.0-or-later
"""Право-гейтированная загрузка OA-источников (stdlib-only).

Загрузка разрешена ТОЛЬКО когда выполняются все условия:
  1. ``rights.classifier.classify(source)['redistributable'] is True``;
  2. URL — ``https://`` (ни http, ни file, ни data);
  3. хост входит в allow-list исследовательских/OA-платформ, для которых
     допустим прямой возврат файла официальным API.

Модуль НЕ краулит по ссылкам, НЕ обходит robots.txt/paywall и НЕ подставляет
credentials. Скачанные байты кладутся в пользовательскую output-директорию
(по умолчанию её предлагается держать в ``.local/physics-bronze/``, вне git).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from ..rights.classifier import classify
from . import http

# Хосты официальных OA-платформ, отдающих файл напрямую.
ALLOWED_HOSTS = {
    "arxiv.org",
    "export.arxiv.org",
    "www.arxiv.org",
    "zenodo.org",
    "www.zenodo.org",
    "api.openalex.org",
    "openalex.org",
    "ntrs.nasa.gov",
    "www.osti.gov",
    "osti.gov",
    "archive.org",
    "ia.us.archive.org",
    "journals.plos.org",
    "www.mdpi.com",
    "mdpi.com",
}

DEFAULT_MAX_BYTES = 25 * 1024 * 1024


@dataclass
class FetchOutcome:
    """Результат попытки загрузки одной строки манифеста."""

    service_id: Any
    status: str  # "downloaded" | "skipped"
    reason: str = ""
    path: str | None = None
    sha256: str | None = None
    bytes: int = 0
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "service_id": self.service_id,
            "status": self.status,
            "reason": self.reason,
        }
        if self.path is not None:
            out["path"] = self.path
        if self.sha256 is not None:
            out["sha256"] = self.sha256
        if self.bytes:
            out["bytes"] = self.bytes
        out.update(self.extra)
        return out


def is_allowed_url(url: str) -> tuple[bool, str]:
    """Проверить схему https и allow-list хоста."""
    if not url:
        return False, "URL отсутствует"
    parts = urlsplit(url)
    if parts.scheme != "https":
        return False, f"разрешён только https, получено {parts.scheme!r}"
    host = (parts.hostname or "").lower()
    if host not in ALLOWED_HOSTS:
        return False, f"хост {host!r} не входит в allow-list OA-платформ"
    return True, ""


def _safe_filename(candidate: dict[str, Any], url: str) -> str:
    """Детерминированное безопасное имя: <service_id>.<ext>."""
    service_id = str(candidate.get("service_id") or "item")
    slug = "".join(c if (c.isalnum() or c in "-_.") else "_" for c in service_id)
    suffix = Path(urlsplit(url).path).suffix or ".bin"
    return f"{slug}{suffix}"


def fetch_candidate(
    candidate: dict[str, Any],
    *,
    out_dir: str | Path,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> FetchOutcome:
    """Загрузить одного кандидата при соблюдении прав/схемы/хоста."""
    source = {
        "license": candidate.get("license"),
        "copyright_status": candidate.get("copyright_status"),
        "publisher": candidate.get("publisher"),
        "source_type": candidate.get("source_type"),
        "permission_ref": candidate.get("permission_ref"),
        "is_oa": candidate.get("is_oa"),
    }
    decision = classify(source)
    if not decision["redistributable"]:
        return FetchOutcome(
            service_id=candidate.get("service_id"),
            status="skipped",
            reason=f"не redistributable: {decision['basis']}",
        )

    url = candidate.get("oa_url") or candidate.get("source_url")
    ok, why = is_allowed_url(str(url or ""))
    if not ok:
        return FetchOutcome(
            service_id=candidate.get("service_id"),
            status="skipped",
            reason=why,
        )

    try:
        body = http.get(str(url), max_bytes=max_bytes)
    except http.HttpError as exc:
        return FetchOutcome(
            service_id=candidate.get("service_id"),
            status="skipped",
            reason=str(exc),
        )

    sha = hashlib.sha256(body).hexdigest()
    out_root = Path(out_dir)
    out_root.mkdir(parents=True, exist_ok=True)
    target = out_root / _safe_filename(candidate, str(url))
    # Никогда не перезаписываем иным содержимым: добавляем суффикс хэша.
    if target.exists() and target.read_bytes() != body:
        target = out_root / f"{target.stem}-{sha[:8]}{target.suffix}"
    target.write_bytes(body)

    return FetchOutcome(
        service_id=candidate.get("service_id"),
        status="downloaded",
        path=str(target),
        sha256=sha,
        bytes=len(body),
        extra={
            "url": str(url),
            "license": candidate.get("license"),
            "copyright_status": decision["copyright_status"],
            "provenance_service": candidate.get("provenance_service"),
        },
    )


def write_fetch_manifest(path: str | Path, outcomes: list[FetchOutcome]) -> int:
    """Записать JSONL-манифест результатов загрузки. Возвращает число строк."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as fh:
        for outcome in outcomes:
            fh.write(json.dumps(outcome.to_dict(), ensure_ascii=False) + "\n")
    return len(outcomes)
