# SPDX-License-Identifier: GPL-3.0-or-later
"""Адаптеры сбора данных из официальных API (stdlib-only).

Модули:
  * :mod:`physics_ds.collection.http`      — GET с таймаутом/ретраями/лимитом;
  * :mod:`physics_ds.collection.openalex`  — OpenAlex works (метаданные);
  * :mod:`physics_ds.collection.arxiv`     — arXiv Atom API (метаданные+PDF-ссылка);
  * :mod:`physics_ds.collection.crossref`  — Crossref works (только метаданные);
  * :mod:`physics_ds.collection.download`  — право-гейтированная загрузка OA;
  * :mod:`physics_ds.collection.manifest`  — JSONL-манифест кандидатов.

Поиск — всегда metadata-only. Загрузка файлов разрешена только при
``rights.classifier.classify(...)['redistributable'] is True``, только по https
и только с хостов из allow-list. Скачанные артефакты хранятся ЛОКАЛЬНО
(рекомендуется ``.local/physics-bronze/``, вне git) и сопровождаются sha256.
"""

from . import arxiv, crossref, download, http, manifest, openalex

__all__ = ["arxiv", "crossref", "download", "http", "manifest", "openalex"]
