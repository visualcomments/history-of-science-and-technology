#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Тонкий шим: делает тесты модуля physics-dataset-competition видимыми
для шага CI ``python -m pytest tests/ -q``.

Тесты физического датасета лежат в самом модуле
(``physics-dataset-competition/tests/test_physics_ds.py``); здесь лишь
добавляется ``src`` на ``sys.path`` и выполняется импорт модуля тестов.
"""

from __future__ import annotations

import sys
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parent.parent / "physics-dataset-competition"
SRC = MODULE_ROOT / "src"
TESTS = MODULE_ROOT / "tests"

for p in (str(SRC), str(TESTS)):
    if p not in sys.path:
        sys.path.insert(0, p)

# noqa: F401 — импорт ради регистрации pytest-тестов.
from test_physics_ds import *  # noqa: E402,F401,F403
