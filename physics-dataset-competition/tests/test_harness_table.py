# SPDX-License-Identifier: GPL-3.0-or-later
"""Replay a table extraction and check the quantity, value and original unit."""

import json
import subprocess
import sys
from pathlib import Path

import pytest


MODULE_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = MODULE_ROOT / "tests" / "fixtures" / "harness_table_case.json"


@pytest.mark.parametrize(
    ("overrides", "expected_error"),
    [
        ({}, None),
        ({"name": "Air temperature"}, "Air speed"),
        ({"value": 20}, ".value"),
        ({"unit": "km/h"}, ".unit"),
    ],
    ids=["matching-row", "wrong-quantity", "wrong-value", "wrong-unit"],
)
def test_harness_table_extraction(
    tmp_path: Path, overrides: dict[str, float | str], expected_error: str | None
) -> None:
    case = json.loads(FIXTURE.read_text(encoding="utf-8"))
    name, value, unit = case["source"]["excerpt"].splitlines()[2].split(" | ")
    location = f"{FIXTURE.relative_to(MODULE_ROOT.parent).as_posix()}#source.excerpt:line-3"
    extracted_value = {
        "name": name,
        "value": float(value),
        "unit": unit,
        "source_ref": {"location": location},
    }
    assert case["expected"]["constraints"] == [extracted_value]

    cases = tmp_path / "cases.jsonl"
    cases.write_text(json.dumps(case) + "\n", encoding="utf-8")
    responses = tmp_path / "responses.jsonl"
    response = {"values": [extracted_value | overrides]}
    responses.write_text(json.dumps(response) + "\n", encoding="utf-8")
    report = tmp_path / "report.json"
    events = tmp_path / "events.jsonl"
    completed = subprocess.run(
        [
            sys.executable,
            str(MODULE_ROOT / "harness" / "run.py"),
            "run",
            str(cases),
            "--responses", str(responses),
            "--max-rounds", "1",
            "--report", str(report),
            "--events", str(events),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    passed = expected_error is None
    assert completed.returncode == (0 if passed else 1), completed.stderr
    (result,) = json.loads(report.read_text(encoding="utf-8"))["cases"]
    assert result["passed"] is passed
    assert result["needs_expert_approval"] is passed
    if passed:
        assert result["errors"] == []
        event_log = map(json.loads, events.read_text(encoding="utf-8").splitlines())
        round_event = next(event for event in event_log if event["kind"] == "round")
        assert round_event["answer"]["values"][0]["source_ref"]["location"] == location
    else:
        assert any(expected_error in error for error in result["errors"]), result["errors"]
