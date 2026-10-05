# SPDX-License-Identifier: GPL-3.0-or-later
"""Тесты оркестратора run_assignment: полный прогон на заглушках, без сети.

HTTP и HF подменяются: ``search_fn`` и ``fetch_fn`` передаются явно, а вызов
publisher'а подменяется на заглушку, пишущую план в stdout без сети.
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
SCRIPTS = MODULE_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import run_assignment  # noqa: E402
from physics_ds.collection.download import FetchOutcome  # noqa: E402

FIXTURES = MODULE_ROOT / "tests" / "fixtures"


def _candidate(name: str, **overrides) -> dict:
    data = (FIXTURES / name).read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    cand = {
        "service": "arxiv",
        "service_id": f"2401.{abs(hash(name)) % 100000:05d}v1",
        "title": f"Fixture {name}",
        "oa_url": "https://arxiv.org/pdf/2401.00001v1",
        "source_url": "https://arxiv.org/abs/2401.00001v1",
        "license": "cc-by-4.0",
        "year": 2024,
        "provenance_service": "export.arxiv.org",
        "_fixture": name,
        "_sha": sha,
    }
    cand.update(overrides)
    return cand


def _fake_fetch(row, *, out_dir, max_bytes=None):  # noqa: ARG001
    """Заглушка загрузки: «скачивает» фикстуру в workdir и возвращает хэш."""
    name = row.get("_fixture")
    if not name:
        return FetchOutcome(
            service_id=row.get("service_id"), status="skipped", reason="no fixture"
        )
    dest = Path(out_dir) / name
    body = (FIXTURES / name).read_bytes()
    dest.write_bytes(body)
    return FetchOutcome(
        service_id=row.get("service_id"),
        status="downloaded",
        path=str(dest),
        sha256=hashlib.sha256(body).hexdigest(),
        bytes=len(body),
        extra={"url": row.get("oa_url"), "license": row.get("license")},
    )


def _namespace(tmp_path: Path, **overrides):
    import argparse

    values = dict(
        domain="AERO",
        query="wind tunnel airfoil drag",
        slug="test-slug",
        service="all",
        limit=15,
        target_records=1,
        workdir="",
        retrieved_at="2026-10-05T00:00:00Z",
        seed=42,
        sample=1.0,
        max_items=0,
        agent_role_id="agent",
        publish=False,
        dry_run=True,
    )
    values.update(overrides)
    values["workdir"] = str(tmp_path)
    return argparse.Namespace(**values)


def test_run_reaches_bundle(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(run_assignment, "_hf_main", lambda argv: 0)
    args = _namespace(tmp_path)
    rc = run_assignment.run(
        args,
        search_fn=lambda service, domain, query, limit: [
            _candidate("bronze_sample.txt")
        ],
        fetch_fn=_fake_fetch,
    )
    assert rc == run_assignment.EXIT_OK
    bundle = json.loads(
        (tmp_path / "validation-bundle.json").read_text(encoding="utf-8")
    )
    assert bundle["requires_expert_validation"] is True
    assert bundle["counts"]["records"] >= 1
    assert bundle["expert_must_confirm"]
    # прогресс-лог печатается построчно JSON
    lines = [
        json.loads(line)
        for line in capsys.readouterr().out.splitlines()
        if line.strip().startswith("{")
    ]
    steps = {entry.get("step") for entry in lines}
    assert {
        "search",
        "filter",
        "fetch",
        "autofill",
        "extract",
        "validate_sample",
        "bundle",
    } <= steps


def test_run_exits_insufficient_when_too_few_sources(
    tmp_path, monkeypatch, capsys
) -> None:
    monkeypatch.setattr(run_assignment, "_hf_main", lambda argv: 0)
    args = _namespace(tmp_path, target_records=3)
    rc = run_assignment.run(
        args,
        search_fn=lambda service, domain, query, limit: [
            _candidate("bronze_sample.txt")
        ],
        fetch_fn=_fake_fetch,
    )
    assert rc == run_assignment.EXIT_INSUFFICIENT
    err = capsys.readouterr().out
    assert "insufficient redistributable sources" in err


def test_run_blocked_when_no_redistributable(tmp_path, capsys) -> None:
    def _no_fetch(row, *, out_dir, max_bytes=None):  # noqa: ARG001
        return FetchOutcome(
            service_id=row.get("service_id"), status="skipped", reason="x"
        )

    args = _namespace(tmp_path)
    rc = run_assignment.run(
        args,
        search_fn=lambda service, domain, query, limit: [
            _candidate("bronze_sample.txt", license=None)
        ],
        fetch_fn=_no_fetch,
    )
    assert rc == run_assignment.EXIT_INSUFFICIENT


def test_filter_candidates_rejects_non_redistributable_and_bad_host() -> None:
    rows = [
        _candidate("bronze_sample.txt"),  # ok
        _candidate("bronze_sample.txt", license=None),  # not redistributable
        _candidate("bronze_sample.txt", oa_url="http://arxiv.org/pdf/1"),  # not https
        _candidate(
            "bronze_sample.txt", oa_url="https://evil.example.org/x.pdf"
        ),  # bad host
    ]
    selected, skipped = run_assignment.filter_candidates(rows)
    assert len(selected) == 1
    assert len(skipped) == 3
    reasons = " ".join(str(s["reason"]) for s in skipped)
    assert "redistributable" in reasons
    assert "https" in reasons
    assert "allow-list" in reasons


def test_run_does_not_print_token(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("HF_TOKEN", "hf_supersecrettokenvalue1234567890")
    monkeypatch.setattr(run_assignment, "_hf_main", lambda argv: 0)
    args = _namespace(tmp_path, publish=True, dry_run=False)
    rc = run_assignment.run(
        args,
        search_fn=lambda service, domain, query, limit: [
            _candidate("bronze_sample.txt")
        ],
        fetch_fn=_fake_fetch,
    )
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "hf_supersecrettokenvalue1234567890" not in combined
    assert rc == run_assignment.EXIT_OK


def test_run_publish_blocked_without_token(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.delenv("HF_TOKEN", raising=False)
    args = _namespace(tmp_path, publish=True, dry_run=False)
    rc = run_assignment.run(
        args,
        search_fn=lambda service, domain, query, limit: [
            _candidate("bronze_sample.txt")
        ],
        fetch_fn=_fake_fetch,
    )
    assert rc == run_assignment.EXIT_BLOCKED
    assert "HF_TOKEN not set" in capsys.readouterr().out
