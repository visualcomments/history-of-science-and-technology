# SPDX-License-Identifier: GPL-3.0-or-later
"""Доменные проверки: диапазоны, единицы, обязательные условия (DESIGN §18.2/§18.5).

Модуль читает ``configs/domains/<domain>.yaml`` и проверяет:
  * присутствие ``required_conditions`` среди ключей ``conditions`` записи;
  * соответствие ``values[].unit`` карте ``units``;
  * попадание значений ``values[]`` в ``ranges``.

Ограничение мини-парсера: ``parse_simple_yaml`` поддерживает только подмножество
YAML — скаляры, inline-списки ``[a, b]``, inline-словари ``{k: v}`` и один
уровень вложенности. Он НЕ является полноценным YAML-парсером (нет якорей,
многострочных блоков, комментариев в конце значения). Конфиги домена намеренно
держатся в этом подмножестве. Для богатых файлов используйте ``json.loads``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

MODULE_ROOT = Path(__file__).resolve().parents[3]
DOMAINS_DIR = MODULE_ROOT / "configs" / "domains"


def _parse_scalar(token: str) -> Any:
    token = token.strip()
    if not token:
        return ""
    if token == "null":
        return None
    if token == "true":
        return True
    if token == "false":
        return False
    if (token.startswith("[") and token.endswith("]")) or (
        token.startswith("{") and token.endswith("}")
    ):
        # inline-структуры приводим к JSON и отдаём json.loads
        normalised = token.replace("'", '"')
        try:
            return json.loads(normalised)
        except json.JSONDecodeError:
            # список/словарь скаляров без кавычек: {Cx: "-", Cy: "-"}
            inner = token[1:-1].strip()
            if token.startswith("{"):
                out: dict[str, Any] = {}
                for part in _split_top(inner, ","):
                    if ":" not in part:
                        continue
                    k, v = part.split(":", 1)
                    out[_unquote(k)] = _parse_scalar(v)
                return out
            return [_parse_scalar(p) for p in _split_top(inner, ",") if p.strip()]
    if (token.startswith('"') and token.endswith('"')) or (
        token.startswith("'") and token.endswith("'")
    ):
        return token[1:-1]
    if re.fullmatch(r"-?\d+", token):
        return int(token)
    if re.fullmatch(r"-?\d+\.\d+", token):
        return float(token)
    return token


def _unquote(s: str) -> str:
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        return s[1:-1]
    return s


def _split_top(text: str, sep: str) -> list[str]:
    """Разбить по sep вне вложенных [...]/{}. Один уровень вложенности."""
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for ch in text:
        if ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
        if ch == sep and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    if current:
        parts.append("".join(current))
    return parts


def parse_simple_yaml(text: str) -> dict[str, Any]:
    """Разобрать подмножество YAML (см. docstring модуля). Детерминировано."""
    result: dict[str, Any] = {}
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        if indent != 0:
            # вложенность блоками не поддерживаем: допускаем только inline
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        result[_unquote(key)] = _parse_scalar(value)
    return result


def load_domain_config(domain: str, domains_dir: Path | None = None) -> dict[str, Any]:
    """Загрузить конфиг домена из ``configs/domains/<domain>.yaml``."""
    base = domains_dir or DOMAINS_DIR
    path = base / f"{domain.lower()}.yaml"
    return parse_simple_yaml(path.read_text(encoding="utf-8"))


def _as_number(v: Any) -> float | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    return None


def check_record_domain(
    rec: dict[str, Any],
    config: dict[str, Any],
) -> list[str]:
    """Проверить запись против конфига домена. Возвращает список ошибок."""
    errors: list[str] = []

    conditions = rec.get("conditions")
    if conditions is None:
        conditions = {}
    if not isinstance(conditions, dict):
        errors.append("conditions: должен быть объектом")
        conditions = {}

    required = config.get("required_conditions") or []
    for name in required:
        if name not in conditions:
            errors.append(f"conditions: отсутствует обязательное условие '{name}'")

    units_map = config.get("units") or {}
    ranges_map = config.get("ranges") or {}

    values = rec.get("values")
    if not isinstance(values, list):
        errors.append("values: должен быть массивом")
        return errors

    for i, v in enumerate(values):
        if not isinstance(v, dict):
            errors.append(f"values[{i}]: должен быть объектом")
            continue
        name = v.get("name")
        unit = v.get("unit")
        if name in units_map:
            expected = units_map[name]
            if expected != "-" and unit != expected:
                errors.append(
                    f"values[{i}].unit не совпадает с units['{name}']: "
                    f"ожидается {expected!r}, получено {unit!r}"
                )
        if name in ranges_map:
            bounds = ranges_map[name]
            val = _as_number(v.get("value"))
            if val is not None and isinstance(bounds, list) and len(bounds) == 2:
                lo, hi = _as_number(bounds[0]), _as_number(bounds[1])
                if lo is not None and hi is not None and not (lo <= val <= hi):
                    errors.append(
                        f"values[{i}].value={val} вне диапазона [{lo}, {hi}] "
                        f"для '{name}'"
                    )

    return errors
