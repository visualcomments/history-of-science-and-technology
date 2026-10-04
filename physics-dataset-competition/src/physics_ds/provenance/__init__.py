# SPDX-License-Identifier: GPL-3.0-or-later
"""Append-only журнал происхождения данных (W3C PROV-O, DESIGN §4.4)."""

from .writer import ProvenanceWriter, record_sha256

__all__ = ["ProvenanceWriter", "record_sha256"]
