# SPDX-License-Identifier: GPL-3.0-or-later
"""Классификатор авторских прав (decision tree, DESIGN §5.3)."""

from .classifier import classify, STATUSES

__all__ = ["classify", "STATUSES"]
