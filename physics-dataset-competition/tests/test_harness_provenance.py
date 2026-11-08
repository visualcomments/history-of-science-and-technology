# SPDX-License-Identifier: GPL-3.0-or-later
"""P10: harness records require a document, a locator and an extraction method."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

MODULE_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from harness.core import check_answer_against_expected, validate_record  # noqa: E402


@pytest.fixture
def provenance_record() -> dict:
    fixture = MODULE_ROOT / "tests" / "fixtures" / "provenance_record.json"
    return json.loads(fixture.read_text(encoding="utf-8"))


def test_complete_provenance_is_accepted(provenance_record: dict) -> None:
    assert validate_record(provenance_record) == []
    assert check_answer_against_expected(
        {"records": [provenance_record]},
        {"records": [deepcopy(provenance_record)]},
    ) == []


@pytest.mark.parametrize(
    ("field_path", "error_field"),
    [
        (("source",), "source"),
        (("values", 0, "source_ref", "location"), "values[0].source_ref.location"),
        (("provenance", "method"), "method"),
    ],
    ids=["missing-document", "missing-location", "missing-method"],
)
def test_incomplete_provenance_is_rejected(
    provenance_record: dict, field_path: tuple, error_field: str
) -> None:
    expected = {"records": [deepcopy(provenance_record)]}
    parent = provenance_record
    for key in field_path[:-1]:
        parent = parent[key]
    del parent[field_path[-1]]

    errors = validate_record(provenance_record)
    assert any(error_field in error for error in errors), errors

    answer_errors = check_answer_against_expected(
        {"records": [provenance_record]}, expected
    )
    assert any(error_field in error for error in answer_errors), answer_errors
