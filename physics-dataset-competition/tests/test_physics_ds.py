# SPDX-License-Identifier: GPL-3.0-or-later
"""Тесты валидатора, journal, классификатора прав, метрик и split-логики.

Запуск из корня репозитория:
    python -m pytest physics-dataset-competition/tests/test_physics_ds.py -q
    python -m pytest tests/test_physics_dataset.py -q    # тонкий шим
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

MODULE_ROOT = Path(__file__).resolve().parents[1]
SRC = MODULE_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from physics_ds.ml.metrics import mae, mape, physics_violations, r2, rmse  # noqa: E402
from physics_ds.provenance.writer import ProvenanceWriter, record_sha256  # noqa: E402
from physics_ds.rights.classifier import classify  # noqa: E402
from physics_ds.schema.validate import validate_file, validate_record  # noqa: E402
from physics_ds.validation.checks import (  # noqa: E402
    check_record_domain,
    load_domain_config,
    parse_simple_yaml,
)

FIXTURES = MODULE_ROOT / "tests" / "fixtures"


def _read_jsonl(name: str) -> list[dict]:
    text = (FIXTURES / name).read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


# --- validator ---------------------------------------------------------------


def test_valid_fixture_passes_validator() -> None:
    records = _read_jsonl("records.valid.jsonl")
    assert len(records) == 2
    for rec in records:
        assert validate_record(rec) == []


def test_validate_file_counts_errors() -> None:
    records, errors, failed = validate_file(FIXTURES / "records.valid.jsonl")
    assert records == 2 and errors == 0 and failed == []


def test_broken_fixture_is_rejected() -> None:
    records, errors, failed = validate_file(FIXTURES / "records.invalid.jsonl")
    assert records == 1 and errors == 1
    joined = " ".join(failed[0]["errors"])
    assert "record_id" in joined and "domain" in joined


def test_selftest_exits_zero() -> None:
    from physics_ds.schema.validate import _selftest

    assert _selftest() == 0


# --- provenance writer -------------------------------------------------------


def test_provenance_writer_appends(tmp_path: Path) -> None:
    journal = tmp_path / "prov.jsonl"
    w = ProvenanceWriter(journal)
    w.append(
        activity="collect",
        agent_role_id="R01",
        retrieved_at="2026-10-04T10:00:00Z",
        method="manual",
        sha256=record_sha256("x"),
        input_sha256=record_sha256("in-1"),
        output_sha256=record_sha256("out-1"),
    )
    w.append(
        activity="validate",
        agent_role_id="R13",
        retrieved_at="2026-10-04T11:00:00Z",
        method="manual",
        sha256=record_sha256("y"),
        input_sha256=record_sha256("in-2"),
        output_sha256=record_sha256("out-2"),
    )
    rows = w.read_all()
    assert len(rows) == 2
    assert [r["activity"] for r in rows] == ["collect", "validate"]


def test_provenance_writer_is_deterministic(tmp_path: Path) -> None:
    a, b = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    kwargs = dict(
        activity="ocr",
        agent_role_id="R06",
        retrieved_at="2026-10-04T09:00:00Z",
        method="ocr",
        sha256=record_sha256("payload"),
        input_sha256=record_sha256("in"),
        output_sha256=record_sha256("out"),
    )
    ProvenanceWriter(a).append(**kwargs)
    ProvenanceWriter(b).append(**kwargs)
    assert a.read_text(encoding="utf-8") == b.read_text(encoding="utf-8")


def test_provenance_writer_rejects_bad_activity(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        ProvenanceWriter(tmp_path / "p.jsonl").append(
            activity="nope",
            agent_role_id="R01",
            retrieved_at="2026-10-04T10:00:00Z",
            method="manual",
            sha256="a" * 64,
        )


# --- rights classifier -------------------------------------------------------


def test_rights_free_license_branch() -> None:
    out = classify({"license": "cc-by-4.0"})
    assert out["copyright_status"] == "cc-by"
    assert out["reusable"] and out["redistributable"]


def test_rights_permission_branch() -> None:
    out = classify({"permission_ref": "email-2026-01", "license": "proprietary"})
    assert out["copyright_status"] == "permission-granted"


def test_rights_metadata_only_branch() -> None:
    out = classify({"copyright_status": "metadata-only"})
    assert out["copyright_status"] == "metadata-only"
    assert out["reusable"] and not out["redistributable"]


def test_rights_unknown_branch() -> None:
    out = classify({"license": "unknown"})
    assert out["copyright_status"] == "unknown"
    assert not out["reusable"] and not out["redistributable"]


def test_rights_orphan_branch() -> None:
    out = classify({"orphan": True, "license": "unknown"})
    assert out["copyright_status"] == "unknown"
    assert not out["redistributable"] and "orphan" in out["basis"].lower()


def test_rights_government_branch() -> None:
    out = classify({"publisher": "NASA", "source_type": "report"})
    assert out["copyright_status"] == "public-domain"


# --- metrics -----------------------------------------------------------------


def test_metrics_values() -> None:
    y, p = [1.0, 2.0, 3.0], [1.0, 2.0, 4.0]
    assert rmse(y, p) == pytest.approx((1 / 3) ** 0.5)
    assert mae(y, p) == pytest.approx(1 / 3)
    assert r2(y, p) == pytest.approx(0.5)


def test_mape_skips_zero_targets() -> None:
    assert mape([1.0, 0.0], [2.0, 5.0]) == pytest.approx(100.0)


def test_physics_violations() -> None:
    out = physics_violations([0.5, 5.0, -1.0], [(-3, 3), (-3, 3), (-3, 3)])
    assert out["count"] == 1 and out["total"] == 3
    assert out["indices"] == [1]


# --- domain checks + yaml parser --------------------------------------------


def test_parse_simple_yaml_inline() -> None:
    cfg = parse_simple_yaml(
        'domain: AERO\nunits: {Cx: "-", Cy: "-"}\nranges: {Cx: [-1, 3]}'
    )
    assert cfg["domain"] == "AERO"
    assert cfg["units"]["Cx"] == "-"
    assert cfg["ranges"]["Cx"] == [-1, 3]


def test_load_aero_config_and_check() -> None:
    cfg = load_domain_config("AERO", MODULE_ROOT / "configs" / "domains")
    assert cfg["domain"] == "AERO"
    good = {
        "conditions": {"Re": 1, "Ma": 0.1, "alpha": 2},
        "values": [{"name": "Cx", "value": 0.1, "unit": "-"}],
    }
    assert check_record_domain(good, cfg) == []

    bad = {
        "conditions": {"Re": 1},
        "values": [{"name": "Cx", "value": 99.0, "unit": "-"}],
    }
    errs = check_record_domain(bad, cfg)
    assert any("Ma" in e for e in errs)
    assert any("диапазона" in e or "range" in e for e in errs)


# --- split logic -------------------------------------------------------------


def test_splits_deterministic_and_ratio() -> None:
    sys.path.insert(0, str(MODULE_ROOT))
    from benchmark.run import split_records  # type: ignore

    cfg = {
        "seed": 42,
        "ratios": {"train": 0.6, "val": 0.2, "test": 0.2},
        "embargo_years": 0,
    }
    records = [
        {
            "record_id": f"R-{i:07X}",
            "domain": "AERO",
            "source": {"id": f"src-{i}", "year": 1900 + i},
        }
        for i in range(10)
    ]
    first = split_records(records, cfg)
    second = split_records(records, cfg)
    assert [r["record_id"] for r in first["train"]] == [
        r["record_id"] for r in second["train"]
    ]
    assert len(first["train"]) == 6
    assert len(first["val"]) == 2
    assert len(first["test"]) == 2


def test_splits_embargo_excludes_recent_train() -> None:
    sys.path.insert(0, str(MODULE_ROOT))
    from benchmark.run import split_records  # type: ignore

    cfg = {
        "seed": 42,
        "ratios": {"train": 0.6, "val": 0.2, "test": 0.2},
        "embargo_years": 1,
    }
    records = [
        {
            "record_id": f"R-{i:07X}",
            "domain": "AERO",
            "source": {"id": f"src-{i}", "year": 1900 + i},
        }
        for i in range(10)
    ]
    out = split_records(records, cfg)
    if out["test"]:
        test_min = min(r["source"]["year"] for r in out["test"])
        assert all(r["source"]["year"] <= test_min - 1 for r in out["train"])
