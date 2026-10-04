# SPDX-License-Identifier: GPL-3.0-or-later
"""Валидация записей по канонической схеме (DESIGN §4.2)."""

from .validate import validate_record, validate_file, load_schema, REPO_ROOT

__all__ = ["validate_record", "validate_file", "load_schema", "REPO_ROOT"]
