# SPDX-License-Identifier: GPL-3.0-or-later
"""Адаптеры сбора данных (crawlers/OCR/digitize) — заглушка.

Пакет намеренно оставлен без логики на этапе P0 (DESIGN §17, эпик E-03).
Реальные адаптеры (Crossref/OpenAlex/arXiv/Internet Archive, OCR, WebPlotDigitizer)
подключаются на этапе A1 «Collection Sprint» и обязаны соблюдать ToS/robots.txt
и политику прав из ``physics_ds.rights``.

Всё, что кладётся в ``data/bronze``, должно сопровождаться записью в
append-only журнале ``physics_ds.provenance.writer`` (sha256 входа/выхода).
"""
