# SPDX-License-Identifier: GPL-3.0-or-later
"""Построение записей из спецификации (agent-first, без LLM-автоматизации).

:mod:`physics_ds.extract.autofill` собирает ЧЕРНОВУЮ спецификацию из
скачанного bronze-файла и строки манифеста (числа предлагаются регуляркой —
это предложение, не истина).
:mod:`physics_ds.extract.record_builder` собирает записи, conforming
``configs/schema/record.schema.json``, из спецификации. Ничего не выдумывает:
метаданные источника и хэш bronze берутся из спека/манифеста; эксперт обязан
проверить черновик.
"""

from . import autofill
from .record_builder import (
    build_record,
    build_records,
    deterministic_record_id,
    load_spec,
)

__all__ = [
    "autofill",
    "build_record",
    "build_records",
    "deterministic_record_id",
    "load_spec",
]
