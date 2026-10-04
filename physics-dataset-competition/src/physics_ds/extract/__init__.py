# SPDX-License-Identifier: GPL-3.0-or-later
"""Построение записей из спецификации эксперта (без LLM-автоматизации).

:mod:`physics_ds.extract.record_builder` собирает записи, conforming
``configs/schema/record.schema.json``, из JSON-спека, который подготовил
эксперт/агент. Ничего не выдумывает: метаданные источника и хэш bronze берутся
из спека/манифеста. OpenCode помогает извлечь, эксперт обязан проверить.
"""

from .record_builder import (
    build_record,
    build_records,
    deterministic_record_id,
    load_spec,
)

__all__ = [
    "build_record",
    "build_records",
    "deterministic_record_id",
    "load_spec",
]
