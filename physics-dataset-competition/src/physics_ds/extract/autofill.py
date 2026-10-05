# SPDX-License-Identifier: GPL-3.0-or-later
"""Автоматическая сборка черновой спецификации извлечения (stdlib-only).

Модуль делает **первый черновик** спецификации для ``record_builder`` из уже
скачанного bronze-артефакта и строки манифеста, чтобы эксперту не пришлось
писать JSON вручную. Это НЕ источник истины: числа предлагаются регулярными
выражениями и обязаны быть проверены экспертом.

Жёсткие инварианты (сохраняют safety-контур пайплайна):
  * метаданные источника копируются ТОЛЬКО из строки манифеста — ничего не
    выдумывается; отсутствующие поля остаются отсутствующими;
  * ``bronze.sha256``/``path``/``service_id``/``provenance_service`` берутся
    из строки манифеста;
  * права не задаются здесь — их выставляет ``rights.classifier`` при сборке;
  * ``retrieved_at`` обязателен (ISO-8601): берётся из переданного параметра
    или из ``SOURCE_DATE_EPOCH``; фиксированное «1970-…» запрещено;
  * числа без единицы не выдаются за факты: если чисел в тексте нет —
    источник помечается ``skipped: no numeric facts``;
  * ``validation.status = "unchecked"`` и ``validation.notes`` прямо говорят,
    что числа предложены регуляркой и требуют проверки эксперта.

Разбор содержимого: только текстовые форматы (``.txt``, ``.md``, ``.csv``,
``.json``, ``.yaml``, ``.yml``). Бинарные (``.pdf`` и прочее) НЕ парсятся —
новые зависимости не устанавливаются, а запись помечается как требующая
проверки агентом.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

# Текстовые форматы, которые безопасно и детерминированно читаем stdlib.
TEXT_SUFFIXES = {".txt", ".md", ".csv", ".json", ".yaml", ".yml", ".text"}

# Единицы, которые распознаём как «токен единицы» после числа.
UNIT_TOKENS = {
    "deg",
    "rad",
    "m/s",
    "km/h",
    "kn",
    "hz",
    "khz",
    "mhz",
    "ghz",
    "pa",
    "kpa",
    "mpa",
    "gpa",
    "n",
    "kn",
    "nm",
    "kg",
    "s",
    "ms",
    "us",
    "db",
    "dbsm",
    "dbm",
    "v",
    "mv",
    "a",
    "ma",
    "w",
    "kw",
    "j",
    "k",
    "c",
    "%",
    "-",
}

# Число с опциональным знаком, десятичной частью и экспонентой.
_NUM = r"[-+]?(?:\d+\.\d+|\d+|\.\d+)(?:[eE][-+]?\d+)?"
_NUM_UNIT_RE = re.compile(rf"(?<![\w.])({_NUM})\s*([A-Za-zА-Яа-я%°][\w/µ°%]*|-)")

# Условия эксперимента, которые ищем прямо в тексте.
_CONDITION_PATTERNS = {
    "Re": re.compile(r"\bRe\b\s*[=:]?\s*(" + _NUM + r")", re.IGNORECASE),
    "Ma": re.compile(r"\bM(?:a|ach)\b\s*[=:]?\s*(" + _NUM + r")", re.IGNORECASE),
    "alpha": re.compile(r"\balpha\b\s*[=:]?\s*(" + _NUM + r")", re.IGNORECASE),
    "theta": re.compile(r"\btheta\b\s*[=:]?\s*(" + _NUM + r")", re.IGNORECASE),
    "f": re.compile(r"\bf\b\s*[=:]?\s*(" + _NUM + r")", re.IGNORECASE),
    "T": re.compile(r"\bT\b\s*[=:]?\s*(" + _NUM + r")"),
}

# Слова-контекст, из которых берём имя переменной рядом с числом.
_CONTEXT_WORD_RE = re.compile(r"[A-Za-zА-Яа-я][A-Za-zА-Яа-я0-9_]{1,20}")


def resolve_retrieved_at(explicit: str | None) -> str:
    """Определить ``retrieved_at`` для провенанса.

    Приоритет: явный ISO-параметр → ``SOURCE_DATE_EPOCH`` (unix-время → ISO UTC).
    Фиксированное значение по умолчанию недопустимо: без обоих источников —
    явная ошибка (детерминизм без выдумывания времени).
    """
    if explicit:
        return explicit
    epoch = os.environ.get("SOURCE_DATE_EPOCH", "").strip()
    if epoch:
        try:
            ts = int(epoch)
        except ValueError as exc:
            raise ValueError(f"SOURCE_DATE_EPOCH не целое: {epoch!r}") from exc
        import datetime

        return (
            datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )
    raise ValueError(
        "не задан --retrieved-at и отсутствует SOURCE_DATE_EPOCH; "
        "укажите время получения явно (фиксированное 1970-01-01 недопустимо)"
    )


def _context_name(match_start: int, text: str) -> str:
    """Предложить имя переменной по ближайшему слову перед числом."""
    window = text[max(0, match_start - 40) : match_start]
    words = _CONTEXT_WORD_RE.findall(window)
    if words:
        return words[-1]
    return "value"


def _normalize_unit(raw: str) -> str:
    unit = raw.strip()
    if unit == "-":
        return "-"
    return unit


def extract_numbers(text: str) -> list[dict[str, Any]]:
    """Детерминированно предложить числовые факты из текста.

    Возвращает список ``{name, value, unit, uncertainty_kind, context}``.
    Это ПРЕДЛОЖЕНИЕ регулярки, а не проверенный факт.
    """
    proposals: list[dict[str, Any]] = []
    for match in _NUM_UNIT_RE.finditer(text):
        num_raw, unit_raw = match.group(1), match.group(2)
        unit = _normalize_unit(unit_raw)
        if unit.lower() not in UNIT_TOKENS:
            # единица не распознана — число без явной единицы не предлагаем
            continue
        try:
            value: float | int = float(num_raw)
        except ValueError:
            continue
        if value.is_integer():
            value = int(value)
        proposals.append(
            {
                "name": _context_name(match.start(), text),
                "value": value,
                "unit": unit,
                "uncertainty_kind": "unknown",
                "context": text[max(0, match.start() - 30) : match.end() + 30].strip(),
            }
        )
    return proposals


def extract_conditions(text: str) -> dict[str, Any]:
    """Найти узнаваемые условия эксперимента прямо в тексте."""
    conditions: dict[str, Any] = {}
    for name, pattern in _CONDITION_PATTERNS.items():
        match = pattern.search(text)
        if not match:
            continue
        try:
            value: float | int = float(match.group(1))
        except ValueError:
            continue
        if float(value).is_integer():
            value = int(value)
        conditions[name] = value
    return conditions


def _read_text(path: Path) -> tuple[str | None, str]:
    """Прочитать текстовый файл. Возвращает ``(text | None, reason)``.

    ``None`` + причина означает, что содержимое не парсилось (бинарный формат
    или ошибка чтения), но это не ошибка пайплайна.
    """
    if path.suffix.lower() not in TEXT_SUFFIXES:
        return (
            None,
            f"бинарный/неподдерживаемый формат {path.suffix!r}: разбор отложен на агента",
        )
    try:
        return path.read_text(encoding="utf-8", errors="replace"), ""
    except OSError as exc:
        return None, f"не удалось прочитать файл: {exc}"


def _safe_str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def build_spec_from_row(
    row: dict[str, Any],
    *,
    domain: str,
    agent_role_id: str,
    retrieved_at: str,
    bronze_dir: str | Path | None = None,
    query: str | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Построить черновую спецификацию из одной строки манифеста.

    Возвращает ``(spec | None, status)``. ``status`` — отчёт вида
    ``{service_id, status, reason, values, conditions}``. ``spec`` равен
    ``None`` для пропущенных источников.
    """
    service_id = row.get("service_id")
    status_row: dict[str, Any] = {"service_id": service_id}

    if row.get("status") != "downloaded":
        return None, {**status_row, "status": "skipped", "reason": "не downloaded"}
    sha256 = _safe_str(row.get("sha256"))
    path_val = _safe_str(row.get("path"))
    if not sha256 or not path_val:
        return None, {
            **status_row,
            "status": "skipped",
            "reason": "нет sha256/path в манифесте",
        }

    file_path = Path(path_val)
    if not file_path.is_file() and bronze_dir is not None:
        candidate = Path(bronze_dir) / file_path.name
        if candidate.is_file():
            file_path = candidate
    if not file_path.is_file():
        return None, {
            **status_row,
            "status": "skipped",
            "reason": f"файл bronze не найден: {file_path}",
        }

    text, read_reason = _read_text(file_path)
    values: list[dict[str, Any]] = []
    conditions: dict[str, Any] = {}
    note = "числа предложены регуляркой (auto-extract) и требуют проверки эксперта"

    if text is None:
        note = f"{read_reason}; values пуст — заполните вручную по первоисточнику"
        status = "needs-agent-review"
    else:
        values = extract_numbers(text)
        conditions = extract_conditions(text)
        if not values:
            return None, {
                **status_row,
                "status": "skipped",
                "reason": "no numeric facts",
            }
        status = "proposed"

    # source: ТОЛЬКО из строки манифеста, ничего не выдумываем.
    source: dict[str, Any] = {}
    title = _safe_str(row.get("title"))
    if title:
        source["title"] = title
    url = _safe_str(row.get("oa_url")) or _safe_str(row.get("source_url"))
    if url:
        source["url"] = url
    license_id = _safe_str(row.get("license"))
    if license_id:
        source["license"] = license_id
    year = row.get("year")
    if isinstance(year, int):
        source["year"] = year
    if _safe_str(row.get("publisher")):
        source["publisher"] = row["publisher"]
    if _safe_str(row.get("doi")):
        source["doi"] = row["doi"]
    if row.get("service") == "arxiv":
        source.setdefault("source_type", "article")
        source.setdefault("language", "en")
    elif row.get("service") == "crossref":
        source.setdefault("source_type", "article")
    elif row.get("service") == "openalex":
        source.setdefault("source_type", "article")
    if row.get("authors"):
        source["authors"] = row["authors"]

    spec: dict[str, Any] = {
        "domain": domain,
        "source": source,
        "bronze": {
            "sha256": sha256,
            "path": str(file_path),
            "service_id": service_id,
            "provenance_service": row.get("provenance_service"),
        },
        "conditions": conditions,
        "values": values,
        "provenance": {
            "activity": "auto-extract",
            "agent_role_id": agent_role_id,
            "retrieved_at": retrieved_at,
            "method": "script",
        },
        "validation": {
            "status": "unchecked",
            "checked_by_role_id": agent_role_id,
            "checked_at": retrieved_at,
            "notes": note,
        },
    }
    if query:
        spec["query"] = query
    status_row.update(
        {
            "status": status,
            "values": len(values),
            "conditions": sorted(conditions),
            "note": note,
        }
    )
    return spec, status_row


def build_spec(
    rows: list[dict[str, Any]],
    *,
    domain: str,
    agent_role_id: str,
    retrieved_at: str,
    bronze_dir: str | Path | None = None,
    query: str | None = None,
    target_records: int = 3,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Собрать спеку с массивом ``records`` из строк манифеста.

    Возвращает ``(spec, statuses)``. ``spec["records"]`` содержит только
    источники, из которых удалось предложить числа; общие поля (domain,
    provenance, validation) лежат на верхнем уровне и переопределяются
    поэлементно записями.
    """
    records: list[dict[str, Any]] = []
    statuses: list[dict[str, Any]] = []
    for row in rows:
        spec_one, status = build_spec_from_row(
            row,
            domain=domain,
            agent_role_id=agent_role_id,
            retrieved_at=retrieved_at,
            bronze_dir=bronze_dir,
            query=query,
        )
        statuses.append(status)
        if spec_one is not None:
            records.append(spec_one)
        if target_records > 0 and len(records) >= target_records:
            # продолжаем собирать статусы, но записи ограничиваем
            continue

    top = {
        "domain": domain,
        "provenance": {
            "activity": "auto-extract",
            "agent_role_id": agent_role_id,
            "retrieved_at": retrieved_at,
            "method": "script",
        },
        "validation": {
            "status": "unchecked",
            "checked_by_role_id": agent_role_id,
            "checked_at": retrieved_at,
            "notes": "числа предложены регуляркой (auto-extract) и требуют проверки эксперта",
        },
        "records": records,
    }
    if query:
        top["query"] = query
    return top, statuses


def summarize(statuses: list[dict[str, Any]]) -> dict[str, Any]:
    """Сводка по статусам автозаполнения."""
    skipped = [s for s in statuses if s.get("status") == "skipped"]
    proposed = [s for s in statuses if s.get("status") == "proposed"]
    needs_review = [s for s in statuses if s.get("status") == "needs-agent-review"]
    return {
        "sources": len(statuses),
        "proposed": len(proposed),
        "needs_agent_review": len(needs_review),
        "skipped": len(skipped),
        "skipped_reasons": [s.get("reason", "") for s in skipped],
    }


def write_spec(path: str | Path, spec: dict[str, Any]) -> None:
    """Записать спеку в JSON (UTF-8, стабильный порядок ключей вложенных dict-ов)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
