# SPDX-License-Identifier: GPL-3.0-or-later
"""Метрики регрессии и физическая согласованность (stdlib)."""

from .metrics import rmse, mae, mape, r2, physics_violations

__all__ = ["rmse", "mae", "mape", "r2", "physics_violations"]
