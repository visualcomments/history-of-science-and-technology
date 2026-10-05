# SPDX-License-Identifier: GPL-3.0-or-later
"""Тесты автозаполнения спецификации: детерминизм, честность, отсутствие выдумки.

Сеть не используется: работаем с локальными фикстурами и подменой HTTP.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

MODULE_ROOT = Path(__file__).resolve().parents[1]
SRC = MODULE_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from physics_ds.extract import autofill  # noqa: E402
from physics_ds.extract.record_builder import build_records  # noqa: E402

FIXTURES = MODULE_ROOT / "tests" / "fixtures"


def _row_for_fixture(name: str, **overrides) -> dict:
    data = (FIXTURES / name).read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    row = {
        "status": "downloaded",
        "service_id": "2401.00001v1",
        "sha256": sha,
        "path": str(FIXTURES / name),
        "title": "Wind tunnel measurements of an airfoil",
        "oa_url": "https://arxiv.org/pdf/2401.00001v1",
        "license": "cc-by-4.0",
        "year": 2024,
        "service": "arxiv",
        "provenance_service": "export.arxiv.org",
        "authors": ["A. Researcher"],
    }
    row.update(overrides)
    return row


# --- числовые предложения -----------------------------------------------------


def test_extract_numbers_plausible() -> None:
    text = (FIXTURES / "bronze_sample.txt").read_text(encoding="utf-8")
    proposals = autofill.extract_numbers(text)
    pairs = {(p["name"], p["value"], p["unit"]) for p in proposals}
    assert ("speed", 40, "m/s") in pairs
    assert ("temperature", 293, "K") in pairs
    # у каждого предложения есть uncertainty_kind=unknown и контекст
    for p in proposals:
        assert p["uncertainty_kind"] == "unknown"
        assert "context" in p


def test_extract_numbers_ignores_unitless() -> None:
    # "Cx = 0.021" без единицы не должен становиться фактом с выдуманной единицей
    proposals = autofill.extract_numbers("The value Cx = 0.021 was measured.")
    assert all(p["unit"] for p in proposals)
    assert all(p["unit"] != "" for p in proposals)


def test_extract_conditions_recognised() -> None:
    text = "Tested at Re = 3000000 and Ma = 0.20, alpha = 4.0 deg."
    cond = autofill.extract_conditions(text)
    assert cond["Re"] == 3000000
    assert cond["Ma"] == 0.2
    assert cond["alpha"] == 4


# --- построение спека ---------------------------------------------------------


def test_build_spec_copies_source_metadata_verbatim() -> None:
    row = _row_for_fixture("bronze_sample.txt")
    spec, status = autofill.build_spec_from_row(
        row, domain="AERO", agent_role_id="agent", retrieved_at="2026-10-05T00:00:00Z"
    )
    assert status["status"] == "proposed"
    assert spec is not None
    # метаданные взяты ТОЛЬКО из строки манифеста
    assert spec["source"]["title"] == row["title"]
    assert spec["source"]["url"] == row["oa_url"]
    assert spec["source"]["license"] == row["license"]
    assert spec["source"]["year"] == row["year"]
    # doi в строке манифеста не задан → он не появляется
    assert "doi" not in spec["source"]


def test_build_spec_does_not_invent_missing_metadata() -> None:
    row = _row_for_fixture("bronze_sample.txt", title=None, year=None, doi=None)
    spec, _ = autofill.build_spec_from_row(
        row, domain="AERO", agent_role_id="agent", retrieved_at="2026-10-05T00:00:00Z"
    )
    # отсутствующие поля не появляются и не заменяются заглушками
    assert "title" not in spec["source"]
    assert "year" not in spec["source"]
    assert "doi" not in spec["source"]


def test_build_spec_bronze_from_manifest() -> None:
    row = _row_for_fixture("bronze_sample.txt")
    spec, _ = autofill.build_spec_from_row(
        row, domain="AERO", agent_role_id="agent", retrieved_at="2026-10-05T00:00:00Z"
    )
    assert spec["bronze"]["sha256"] == row["sha256"]
    assert spec["bronze"]["service_id"] == row["service_id"]
    assert spec["bronze"]["provenance_service"] == row["provenance_service"]


def test_build_spec_marks_unchecked_with_note() -> None:
    row = _row_for_fixture("bronze_sample.txt")
    spec, _ = autofill.build_spec_from_row(
        row, domain="AERO", agent_role_id="agent", retrieved_at="2026-10-05T00:00:00Z"
    )
    assert spec["validation"]["status"] == "unchecked"
    assert "провер" in spec["validation"]["notes"].lower()
    assert spec["provenance"]["activity"] == "auto-extract"
    assert spec["provenance"]["method"] == "script"


def test_build_spec_skips_numberless_with_reason() -> None:
    row = _row_for_fixture("bronze_numberless.txt")
    spec, status = autofill.build_spec_from_row(
        row, domain="AERO", agent_role_id="agent", retrieved_at="2026-10-05T00:00:00Z"
    )
    assert spec is None
    assert status["status"] == "skipped"
    assert "no numeric facts" in status["reason"]


def test_build_spec_skips_binary_and_marks_review() -> None:
    pdf = FIXTURES / "_tmp_probe.pdf"
    pdf.write_bytes(b"%PDF-1.4 binary content \x00\x01")
    try:
        data = pdf.read_bytes()
        row = _row_for_fixture(
            "bronze_sample.txt",
            path=str(pdf),
            sha256=hashlib.sha256(data).hexdigest(),
        )
        spec, status = autofill.build_spec_from_row(
            row,
            domain="AERO",
            agent_role_id="agent",
            retrieved_at="2026-10-05T00:00:00Z",
        )
        assert spec is not None
        assert status["status"] == "needs-agent-review"
        assert spec["values"] == []
        assert "вручную" in spec["validation"]["notes"]
    finally:
        pdf.unlink(missing_ok=True)


def test_build_spec_skips_not_downloaded() -> None:
    row = _row_for_fixture("bronze_sample.txt", status="skipped")
    spec, status = autofill.build_spec_from_row(
        row, domain="AERO", agent_role_id="agent", retrieved_at="2026-10-05T00:00:00Z"
    )
    assert spec is None
    assert status["status"] == "skipped"


def test_build_spec_skips_missing_file() -> None:
    row = _row_for_fixture("bronze_sample.txt", path="does/not/exist.txt")
    spec, status = autofill.build_spec_from_row(
        row, domain="AERO", agent_role_id="agent", retrieved_at="2026-10-05T00:00:00Z"
    )
    assert spec is None
    assert status["status"] == "skipped"
    assert "не найден" in status["reason"]


# --- retrieved_at -------------------------------------------------------------


def test_resolve_retrieved_at_requires_value(monkeypatch) -> None:
    monkeypatch.delenv("SOURCE_DATE_EPOCH", raising=False)
    with pytest.raises(ValueError):
        autofill.resolve_retrieved_at(None)


def test_resolve_retrieved_at_from_epoch(monkeypatch) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
    assert autofill.resolve_retrieved_at(None).startswith("2023-11-14")


def test_resolve_retrieved_at_explicit_wins(monkeypatch) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
    assert (
        autofill.resolve_retrieved_at("2026-10-05T00:00:00Z") == "2026-10-05T00:00:00Z"
    )


# --- интеграция с record_builder ---------------------------------------------


def test_spec_is_consumable_by_record_builder() -> None:
    row = _row_for_fixture("bronze_sample.txt")
    spec, _ = autofill.build_spec_from_row(
        row, domain="AERO", agent_role_id="agent", retrieved_at="2026-10-05T00:00:00Z"
    )
    # спеку одного источника оборачиваем как build_records(spec)
    records, errors = build_records(spec)
    assert errors == []
    assert records[0]["domain"] == "AERO"


def test_build_spec_multi_record_array() -> None:
    rows = [
        _row_for_fixture("bronze_sample.txt"),
        _row_for_fixture("bronze_sample.txt", service_id="2401.00002v1"),
    ]
    spec, statuses = autofill.build_spec(
        rows,
        domain="AERO",
        agent_role_id="agent",
        retrieved_at="2026-10-05T00:00:00Z",
    )
    assert len(spec["records"]) == 2
    assert len(statuses) == 2
    assert autofill.summarize(statuses)["proposed"] == 2
