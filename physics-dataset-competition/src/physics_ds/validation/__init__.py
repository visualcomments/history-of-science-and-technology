# SPDX-License-Identifier: GPL-3.0-or-later
"""Доменные проверки диапазонов, единиц и обязательных условий."""

from .checks import (
    load_domain_config,
    parse_simple_yaml,
    check_record_domain,
)

__all__ = ["load_domain_config", "parse_simple_yaml", "check_record_domain"]
