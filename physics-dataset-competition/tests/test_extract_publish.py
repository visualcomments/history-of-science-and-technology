# SPDX-License-Identifier: GPL-3.0-or-later
"""Тесты извлечения, выборки, коррекции и HF-публикации (без сети)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[1]
SRC = MODULE_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from physics_ds.extract.record_builder import (  # noqa: E402
    build_records,
    deterministic_record_id,
    load_spec,
)
from physics_ds.schema.validate import RECORD_ID_RE, validate_record  # noqa: E402
from physics_ds.validation.sampling import check_records, sample  # noqa: E402

FIXTURES = MODULE_ROOT / "tests" / "fixtures"
SCRIPTS = MODULE_ROOT / "scripts"
PUBLISH = SRC / "physics_ds" / "publish"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


# --- extraction --------------------------------------------------------------


def test_deterministic_record_id_is_stable() -> None:
    sha = "a" * 64
    a = deterministic_record_id("AERO", sha, 0)
    b = deterministic_record_id("AERO", sha, 0)
    assert a == b
    assert RECORD_ID_RE.match(a)
    # разные индексы → разные id
    assert deterministic_record_id("AERO", sha, 1) != a


def test_build_records_from_spec() -> None:
    spec = _load("spec.aero.json")
    records, errors = build_records(spec)
    assert errors == []
    assert len(records) == 1
    record = records[0]
    assert validate_record(record) == []
    assert record["domain"] == "AERO"
    assert record["rights"]["redistributable"] is True
    assert record["provenance"]["sha256"] == spec["bronze"]["sha256"]
    assert record["source"]["copyright_status"] == "public-domain"


def test_build_records_rejects_missing_bronze_hash() -> None:
    spec = _load("spec.aero.json")
    spec = dict(spec)
    spec["bronze"] = {"path": ".local/x.pdf"}
    records, errors = build_records(spec)
    assert records == []
    assert any("sha256" in e for e in errors)


def test_build_records_reuses_spec_source_metadata() -> None:
    # не выдумываем: title/year берутся из спецификации
    spec = _load("spec.aero.json")
    records, _ = build_records(spec)
    assert records[0]["source"]["title"] == spec["source"]["title"]
    assert records[0]["source"]["year"] == spec["source"]["year"]


def test_load_spec_roundtrip() -> None:
    spec = load_spec(FIXTURES / "spec.aero.json")
    assert spec["domain"] == "AERO"


# --- sampling ----------------------------------------------------------------


def test_sample_is_deterministic() -> None:
    records = [{"record_id": f"AERO-{i:010X}"} for i in range(10)]
    a = sample(records, 0.3, 42)
    b = sample(records, 0.3, 42)
    assert a == b
    assert len(a) == 3


def test_sample_edge_rates() -> None:
    records = [{"record_id": f"AERO-{i:010X}"} for i in range(5)]
    assert sample(records, 0.0, 42) == []
    assert sample(records, 1.0, 42) == records


def test_check_records_detects_duplicate_and_bad_unit() -> None:
    good = _build_valid_record()
    duplicate = dict(good)
    bad_unit = dict(good)
    bad_unit["record_id"] = "AERO-0000000002"
    # alpha ожидается в градусах (deg); rad — неверная единица
    bad_unit["values"] = [{"name": "alpha", "value": 4.0, "unit": "rad"}]

    report = check_records([good, duplicate, bad_unit])
    assert report["ok"] is False
    assert report["counts"]["duplicates"] == 1
    assert any("дубликат" in str(e["errors"]) for e in report["errors"])
    assert any("unit" in str(e["errors"]) for e in report["errors"])


def test_check_records_detects_out_of_range() -> None:
    rec = _build_valid_record()
    rec["values"] = [{"name": "Cx", "value": 99.0, "unit": "-"}]
    report = check_records([rec])
    assert report["ok"] is False
    assert any("диапазона" in str(e["errors"]) for e in report["errors"])


def _build_valid_record() -> dict:
    records, errors = build_records(_load("spec.aero.json"))
    assert errors == []
    return records[0]


# --- correction --------------------------------------------------------------


def test_correction_emits_parent_record_id() -> None:
    sys.path.insert(0, str(SCRIPTS))
    import correct  # type: ignore

    record = _build_valid_record()
    parent = record["record_id"]
    corrected = correct.make_corrected(record, parent)
    assert corrected["record_id"] != parent
    assert corrected["provenance"]["parent_record_id"] == parent
    assert validate_record(corrected) == []


def test_correction_rejects_bad_parent() -> None:
    sys.path.insert(0, str(SCRIPTS))
    import correct  # type: ignore

    record = _build_valid_record()
    try:
        correct.make_corrected(record, "not-a-valid-id")
    except ValueError:
        return
    raise AssertionError("ожидалась ошибка для недопустимого parent id")


# --- HF publisher ------------------------------------------------------------


def _hf_module():
    sys.path.insert(0, str(PUBLISH))
    import importlib

    return importlib.import_module("hf")


def test_publish_dry_run_validates_and_no_token(monkeypatch, capsys) -> None:
    hf = _hf_module()
    monkeypatch.delenv("HF_TOKEN", raising=False)
    code = hf.main(["--records", str(FIXTURES / "records.valid.jsonl"), "--dry-run"])
    assert code == 0
    out = capsys.readouterr().out
    plan = json.loads(out)
    assert plan["dry_run"] is True
    assert plan["records"] == 2
    assert len(plan["sha256"]) == 64
    assert plan["path_in_repo"].startswith("submissions/")


def test_publish_rejects_non_redistributable_before_network(
    monkeypatch, capsys
) -> None:
    hf = _hf_module()
    monkeypatch.delenv("HF_TOKEN", raising=False)
    records = [
        {
            "record_id": "AERO-0000000001",
            "schema_version": "1.0.0",
            "domain": "AERO",
            "source": {
                "title": "t",
                "source_type": "article",
                "year": 1995,
                "language": "en",
                "url": "https://doi.org/x",
                "license": "metadata-only",
            },
            "rights": {"reusable": True, "redistributable": False, "basis": "§5.3(3)"},
            "conditions": {"Re": 1, "Ma": 0.1, "alpha": 1},
            "values": [{"name": "Cx", "value": 0.01, "unit": "-"}],
            "provenance": {
                "activity": "digitize",
                "agent_role_id": "R01",
                "retrieved_at": "2026-10-04T10:00:00Z",
                "method": "manual",
                "sha256": "a" * 64,
            },
            "validation": {
                "status": "unchecked",
                "checked_by_role_id": "R01",
                "checked_at": "2026-10-04T10:00:00Z",
            },
        }
    ]
    path = FIXTURES / "_tmp_nonredist.jsonl"
    path.write_text(json.dumps(records[0]) + "\n", encoding="utf-8")
    try:
        code = hf.main(["--records", str(path), "--dry-run"])
    finally:
        path.unlink(missing_ok=True)
    assert code == 1
    err = capsys.readouterr().err
    assert "redistributable" in err


def test_publish_requires_token_outside_dry_run(monkeypatch, capsys) -> None:
    hf = _hf_module()
    monkeypatch.delenv("HF_TOKEN", raising=False)
    code = hf.main(["--records", str(FIXTURES / "records.valid.jsonl")])
    assert code == 2
    err = capsys.readouterr().err
    assert "HF_TOKEN" in err
    # токен не должен попасть в вывод
    assert "hf_" not in err
