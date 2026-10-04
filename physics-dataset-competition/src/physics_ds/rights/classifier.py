# SPDX-License-Identifier: GPL-3.0-or-later
"""Классификатор авторских прав (decision tree, DESIGN §5.3).

Чистая детерминированная функция ``classify(source)`` без побочных эффектов.

Дерево решений (§5.3):
  1. Явная свободная лицензия (CC0/CC-BY/CC-BY-SA, PD, government work)
     → reusable/redistributable с атрибуцией.
  2. Есть письменное разрешение → permission-granted, reusable/redistributable.
  3. Охраняется, но нужны данные → metadata-only: reusable=true,
     redistributable=false (только метаданные/ссылки/извлечённые факты).
  4. Неизвестно → unknown, всё запрещено до экспертного ревью.
  5. Orphan works → не использовать (unknown/запрет).
"""

from __future__ import annotations

from typing import Any

# Статусы из enum schema (source.copyright_status).
STATUSES = {
    "public-domain",
    "cc-by",
    "cc-by-sa",
    "cc0",
    "permission-granted",
    "metadata-only",
    "unknown",
}

# Лицензии (SPDX-подобные) → copyright_status.
_FREE_LICENSE_STATUS = {
    "cc0": "cc0",
    "cc0-1.0": "cc0",
    "public-domain": "public-domain",
    "pd": "public-domain",
    "cc-by": "cc-by",
    "cc-by-4.0": "cc-by",
    "cc-by-sa": "cc-by-sa",
    "cc-by-sa-4.0": "cc-by-sa",
}

# source_type, трактуемые как government work (public domain).
_GOVERNMENT_SOURCE_TYPES = {"standard", "report"}


def _norm(value: Any) -> str:
    return str(value).strip().lower() if value is not None else ""


def classify(source: dict[str, Any]) -> dict[str, Any]:
    """Классифицировать источник по дереву решений §5.3.

    ``source`` — словарь с полями как в schema (``license``, ``copyright_status``,
    ``publisher``, ``source_type``, ``permission_ref``, ``orphan``).

    Возвращает ``{copyright_status, reusable, redistributable, basis}``.
    """
    if not isinstance(source, dict):
        return {
            "copyright_status": "unknown",
            "reusable": False,
            "redistributable": False,
            "basis": "§5.3(4): источник не задан — запрещено до ревью",
        }

    license_id = _norm(source.get("license"))
    declared = _norm(source.get("copyright_status"))
    publisher = _norm(source.get("publisher"))
    source_type = _norm(source.get("source_type"))

    # 1. Явная свободная лицензия.
    status: str | None = _FREE_LICENSE_STATUS.get(license_id)
    if status is None and declared in STATUSES:
        status = declared

    if status in ("public-domain", "cc0"):
        return {
            "copyright_status": status,
            "reusable": True,
            "redistributable": True,
            "basis": f"§5.3(1): свободная лицензия/статус '{status}' (атрибуция)",
        }

    if status in ("cc-by", "cc-by-sa"):
        return {
            "copyright_status": status,
            "reusable": True,
            "redistributable": True,
            "basis": f"§5.3(1): {status} — переиспользование с атрибуцией",
        }

    # government work → public domain.
    gov = publisher in {"nasa", "nasa ntrs", "us government", "dtic", "osti"} or (
        source_type in _GOVERNMENT_SOURCE_TYPES and "government" in publisher
    )
    if gov:
        return {
            "copyright_status": "public-domain",
            "reusable": True,
            "redistributable": True,
            "basis": "§5.3(1): government work — public domain",
        }

    # 5. Orphan works — не использовать.
    if source.get("orphan") is True:
        return {
            "copyright_status": "unknown",
            "reusable": False,
            "redistributable": False,
            "basis": "§5.3(5): orphan work — запрещено без юридической проверки",
        }

    # 2. Письменное разрешение.
    if source.get("permission_ref") or declared == "permission-granted":
        return {
            "copyright_status": "permission-granted",
            "reusable": True,
            "redistributable": True,
            "basis": "§5.3(2): письменное разрешение (доказательство в permission_ref)",
        }

    # 3. Охраняется, но нужны данные → metadata-only.
    if declared == "metadata-only" or license_id in {"metadata-only", "cite-only"}:
        return {
            "copyright_status": "metadata-only",
            "reusable": True,
            "redistributable": False,
            "basis": "§5.3(3): охраняется — только метаданные/ссылки/факты (redistributable=false)",
        }

    # 4. Неизвестно → запрет до экспертного ревью.
    return {
        "copyright_status": "unknown",
        "reusable": False,
        "redistributable": False,
        "basis": "§5.3(4): статус неизвестен — публикация запрещена до экспертного ревью",
    }
