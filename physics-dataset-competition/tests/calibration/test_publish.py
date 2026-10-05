# SPDX-License-Identifier: GPL-3.0-or-later
"""Тесты HF-публикации калибровочных сессий (без сети)."""

import importlib
import json
import sys
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[2]
CALIBRATION = MODULE_ROOT / "calibration"
if str(CALIBRATION) not in sys.path:
    sys.path.insert(0, str(CALIBRATION))

from session import SessionWriter  # noqa: E402

TS = "2026-10-05T10:00:00Z"


def _source() -> dict:
    return {
        "source_type": "article",
        "title": "Wind tunnel tests",
        "rights": {"reusable": True, "redistributable": True, "basis": "public-domain"},
    }


def _publisher():
    return importlib.import_module("publish")


def _approved_session(path: Path) -> None:
    w = SessionWriter(path, "SESS-001")
    w.append(
        role="task",
        round=0,
        timestamp=TS,
        source=_source(),
        payload={"prompt": "extract"},
    )
    w.append(
        role="agent_answer",
        timestamp=TS,
        source=_source(),
        payload={"agent_answer": {"summary": "Cx=0.02"}},
    )
    w.append(
        role="expert_review",
        timestamp=TS,
        source=_source(),
        payload={"expert_analysis": "ok", "expert_approved": True},
    )
    w.append(
        role="final",
        timestamp=TS,
        source=_source(),
        payload={"expert_approved": True},
    )


def test_publish_dry_run_no_token(tmp_path: Path, monkeypatch, capsys) -> None:
    pub = _publisher()
    monkeypatch.delenv("HF_TOKEN", raising=False)
    session_file = tmp_path / "session.jsonl"
    _approved_session(session_file)

    code = pub.main(["--session-file", str(session_file), "--dry-run"])
    assert code == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["dry_run"] is True
    assert plan["repo_id"] == "top-papers/physics-agent-calibrations"
    assert plan["events"] == 4
    assert len(plan["sha256"]) == 64
    assert plan["path_in_repo"] == "calibrations/SESS-001/session.jsonl"


def test_publish_real_requires_token(tmp_path: Path, monkeypatch, capsys) -> None:
    pub = _publisher()
    monkeypatch.delenv("HF_TOKEN", raising=False)
    session_file = tmp_path / "session.jsonl"
    _approved_session(session_file)

    code = pub.main(["--session-file", str(session_file)])
    assert code == 2
    err = capsys.readouterr().err
    assert "HF_TOKEN" in err
    assert "hf_" not in err


def test_publish_rejects_unapproved_session(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    pub = _publisher()
    monkeypatch.delenv("HF_TOKEN", raising=False)
    session_file = tmp_path / "session.jsonl"
    w = SessionWriter(session_file, "SESS-001")
    w.append(
        role="task",
        round=0,
        timestamp=TS,
        source=_source(),
        payload={"prompt": "extract"},
    )

    code = pub.main(["--session-file", str(session_file), "--dry-run"])
    assert code == 1
    assert "errors" in capsys.readouterr().err


def test_publish_missing_file_returns_2(tmp_path: Path, capsys) -> None:
    pub = _publisher()
    code = pub.main(["--session-file", str(tmp_path / "nope.jsonl"), "--dry-run"])
    assert code == 2
