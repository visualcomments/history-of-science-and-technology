# SPDX-License-Identifier: GPL-3.0-or-later
"""Метрики регрессии и физическая согласованность (stdlib, без numpy).

Реализованы: ``rmse``, ``mae``, ``mape``, ``r2`` и ``physics_violations``.
Все функции — чистые, детерминированные, работают с обычными списками чисел.
"""

from __future__ import annotations

import math
from typing import Any, Iterable

ArrayLike = Iterable[float]


def _pairs(y_true: ArrayLike, y_pred: ArrayLike) -> tuple[list[float], list[float]]:
    a = [float(x) for x in y_true]
    b = [float(x) for x in y_pred]
    if len(a) != len(b):
        raise ValueError(f"длины не совпадают: {len(a)} != {len(b)}")
    if not a:
        raise ValueError("пустые входные массивы")
    return a, b


def rmse(y_true: ArrayLike, y_pred: ArrayLike) -> float:
    """Корень из среднеквадратичной ошибки."""
    a, b = _pairs(y_true, y_pred)
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)) / len(a))


def mae(y_true: ArrayLike, y_pred: ArrayLike) -> float:
    """Средняя абсолютная ошибка."""
    a, b = _pairs(y_true, y_pred)
    return sum(abs(x - y) for x, y in zip(a, b)) / len(a)


def mape(y_true: ArrayLike, y_pred: ArrayLike) -> float:
    """Средняя абсолютная процентная ошибка (в %); нулевые y_true пропускаются."""
    a, b = _pairs(y_true, y_pred)
    terms = [abs((x - y) / x) for x, y in zip(a, b) if x != 0]
    if not terms:
        raise ValueError("mape: все эталонные значения равны нулю")
    return sum(terms) / len(terms) * 100.0


def r2(y_true: ArrayLike, y_pred: ArrayLike) -> float:
    """Коэффициент детерминации R² (1.0 — идеально)."""
    a, b = _pairs(y_true, y_pred)
    mean = sum(a) / len(a)
    sse = sum((x - y) ** 2 for x, y in zip(a, b))
    sst = sum((x - mean) ** 2 for x in a)
    if sst == 0:
        return 1.0 if sse == 0 else 0.0
    return 1.0 - sse / sst


def physics_violations(
    predictions: ArrayLike,
    bounds: list[tuple[float, float]],
) -> dict[str, Any]:
    """Посчитать выход предсказаний за физически допустимые границы.

    ``bounds[i]`` — ``(lo, hi)`` для i-го предсказания. Возвращает
    ``{"count": int, "total": int, "rate": float, "indices": [...]}``.
    """
    preds = [float(p) for p in predictions]
    if len(preds) != len(bounds):
        raise ValueError(
            f"число предсказаний ({len(preds)}) != число границ ({len(bounds)})"
        )
    indices: list[int] = []
    for i, (p, (lo, hi)) in enumerate(zip(preds, bounds)):
        if p < float(lo) or p > float(hi):
            indices.append(i)
    total = len(preds)
    return {
        "count": len(indices),
        "total": total,
        "rate": (len(indices) / total) if total else 0.0,
        "indices": indices,
    }
