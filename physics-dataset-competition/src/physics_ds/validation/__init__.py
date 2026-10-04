# SPDX-License-Identifier: GPL-3.0-or-later
"""Доменные проверки, детерминированная выборка и отчёты."""

from .checks import (
    check_record_domain,
    load_domain_config,
    parse_simple_yaml,
)
from .sampling import check_records, sample

__all__ = [
    "check_record_domain",
    "load_domain_config",
    "parse_simple_yaml",
    "sample",
    "check_records",
]
