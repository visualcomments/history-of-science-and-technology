# SPDX-License-Identifier: GPL-3.0-or-later
"""Негативный тест: харнесс останавливается на несуществующем источнике.

Путь к первоисточнику приходит в спецификации извлечения (``bronze.path``).
Если файла нет, извлечение и запись результата начинаться не должны.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = MODULE_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import extract  # noqa: E402

FIXTURES = MODULE_ROOT / "tests" / "fixtures"


def _spec_with_missing_source(tmp_path: Path) -> Path:
    """Спецификация с валидным хэшем, но несуществующим файлом источника."""
    spec = json.loads((FIXTURES / "spec.aero.json").read_text(encoding="utf-8"))
    spec["bronze"]["path"] = str(FIXTURES / "missing-paper.pdf")
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(spec), encoding="utf-8")
    return path


def test_missing_source_stops_before_extraction(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    spec_path = _spec_with_missing_source(tmp_path)
    out_path = tmp_path / "records.jsonl"
    calls: list[dict] = []

    def _build_records(spec: dict):
        calls.append(spec)
        return [], []

    monkeypatch.setattr(extract, "build_records", _build_records)

    rc = extract.main(["--spec", str(spec_path), "--out", str(out_path)])

    assert rc == 2
    # Извлечение не началось и результат не создан.
    assert calls == []
    assert not out_path.exists()
    err = capsys.readouterr().err
    assert "файл источника не найден" in err
    assert "missing-paper.pdf" in err


def test_missing_spec_file_stops_with_clear_message(tmp_path: Path, capsys) -> None:
    missing_spec = tmp_path / "missing-paper.pdf"

    rc = extract.main(["--spec", str(missing_spec)])

    assert rc == 2
    err = capsys.readouterr().err
    assert "файл спецификации не найден" in err
    assert "missing-paper.pdf" in err
