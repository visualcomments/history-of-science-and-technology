# SPDX-License-Identifier: GPL-3.0-or-later
"""physics_ds — stdlib-only инструментарий учебного физического датасета.

Модули:
  * ``schema``      — валидатор записей по ``configs/schema/record.schema.json``;
  * ``validation``  — диапазоны, единицы, обязательные условия по домену;
  * ``provenance``  — append-only JSONL-журнал PROV-O;
  * ``rights``      — классификатор авторских прав (DESIGN §5.3);
  * ``collection``  — адаптеры сбора (заглушка, см. docstring пакета);
  * ``ml``          — метрики регрессии и физические нарушения;
  * ``publish``     — публикация HF/Kaggle (заглушка).

Все модули детерминированы и не требуют внешних зависимостей.
"""

__all__ = [
    "schema",
    "validation",
    "provenance",
    "rights",
    "collection",
    "ml",
    "publish",
]
