# SPDX-License-Identifier: GPL-3.0-or-later
"""Негативный тест CLI харнесса: отсутствующий входной файл останавливает прогон.

Проверяется ``harness/run.py run``: путь к кейсам — это входной файл
харнесса. Если его нет, прогон не начинается, а отчёт и события не создаются.
"""

from __future__ import annotations

import sys
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[1]
HARNESS = MODULE_ROOT / "harness"
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

import run  # noqa: E402

FIXTURES = MODULE_ROOT / "tests" / "fixtures"


def test_missing_cases_file_stops_before_run(tmp_path: Path, capsys) -> None:
    missing_cases = FIXTURES / "missing-paper.pdf"
    report = tmp_path / "report.json"
    events = tmp_path / "events.jsonl"

    rc = run.main(
        [
            "run",
            str(missing_cases),
            "--command",
            "cat",
            "--report",
            str(report),
            "--events",
            str(events),
        ]
    )

    assert rc == 2
    assert not report.exists()
    assert not events.exists()
    err = capsys.readouterr().err
    assert "файл кейсов не найден" in err
    assert "missing-paper.pdf" in err
