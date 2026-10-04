# SPDX-License-Identifier: GPL-3.0-or-later
"""Публикация на Hugging Face Hub (с Kaggle/прочими — по мере надобности).

:mod:`physics_ds.publish.hf` — CLI публикации записей через pull request в
публичный dataset-репозиторий. Публикуются только ``redistributable=True``
записи; схема и домены проверяются до сети; токен — только из ``HF_TOKEN``;
``--dry-run`` не делает сети.

``huggingface_hub`` — опциональная зависимость, импортируется лениво только в
не-dry-run ветке (см. ``docs/requirements-publish.txt``).
"""

__all__ = ["hf"]
