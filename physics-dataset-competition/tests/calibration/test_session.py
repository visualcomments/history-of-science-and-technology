# SPDX-License-Identifier: GPL-3.0-or-later
"""Тесты сессий экспертной калибровки (stdlib + pytest, без сети)."""

import sys
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[2]
CALIBRATION = MODULE_ROOT / "calibration"
SCRIPTS = MODULE_ROOT / "scripts"
for _p in (str(CALIBRATION), str(SCRIPTS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from calibration_session import main as cli_main  # noqa: E402
from session import (  # noqa: E402
    SessionWriter,
    check_sequence,
    deterministic_event_id,
    export_publishable,
    redact_text,
    summarize,
    validate_event,
    validate_session,
)

TS = "2026-10-05T10:00:00Z"


def _source() -> dict:
    return {
        "source_type": "article",
        "title": "Wind tunnel tests",
        "year": 1935,
        "language": "en",
        "url": "https://example.org/a",
        "rights": {"reusable": True, "redistributable": True, "basis": "public-domain"},
    }


def _task_event(session_id: str = "SESS-001") -> dict:
    event = {
        "session_id": session_id,
        "round": 0,
        "role": "task",
        "timestamp": TS,
        "source": _source(),
        "payload": {"prompt": "extract Cx(alpha) table"},
    }
    event["event_id"] = deterministic_event_id(event)
    return event


def _build_approved_session(path: Path, session_id: str = "SESS-001") -> None:
    """task -> answer -> review(errors) -> correction -> answer -> review(ok) -> final."""
    w = SessionWriter(path, session_id)
    w.append(
        role="task",
        round=0,
        timestamp=TS,
        source=_source(),
        payload={"prompt": "extract"},
    )
    w.append(
        role="agent_answer",
        timestamp="2026-10-05T10:05:00Z",
        source=_source(),
        payload={
            "agent_answer": {
                "summary": "Cx=0.02",
                "values": [{"name": "Cx", "value": 0.02, "unit": "-"}],
            }
        },
    )
    w.append(
        role="expert_review",
        timestamp="2026-10-05T10:10:00Z",
        source=_source(),
        payload={
            "expert_analysis": "wrong value",
            "errors_found": [
                {
                    "field": "Cx",
                    "problem": "should be 0.021",
                    "expected": 0.021,
                    "actual": 0.02,
                }
            ],
            "expert_approved": False,
        },
    )
    w.append(
        role="correction",
        timestamp="2026-10-05T10:15:00Z",
        source=_source(),
        payload={
            "corrected_answer": {
                "summary": "Cx=0.021",
                "values": [{"name": "Cx", "value": 0.021, "unit": "-"}],
            }
        },
    )
    w.append(
        role="agent_answer",
        timestamp="2026-10-05T10:20:00Z",
        source=_source(),
        payload={
            "agent_answer": {
                "summary": "Cx=0.021",
                "values": [{"name": "Cx", "value": 0.021, "unit": "-"}],
            }
        },
    )
    w.append(
        role="expert_review",
        timestamp="2026-10-05T10:25:00Z",
        source=_source(),
        payload={"expert_analysis": "correct now", "expert_approved": True},
    )
    w.append(
        role="final",
        timestamp="2026-10-05T10:30:00Z",
        source=_source(),
        payload={"expert_approved": True, "approval_note": "approved"},
    )


# --- schema / event validation ----------------------------------------------


def test_valid_task_event() -> None:
    assert validate_event(_task_event()) == []


def test_missing_required_field_rejected() -> None:
    event = _task_event()
    del event["round"]
    errors = validate_event(event)
    assert any("round" in e for e in errors)


def test_final_requires_explicit_approval() -> None:
    event = _task_event()
    event["role"] = "final"
    event["payload"] = {"expert_approved": False}
    event["event_id"] = deterministic_event_id(event)
    errors = validate_event(event)
    assert any("expert_approved" in e for e in errors)


def test_payload_role_requirements() -> None:
    for role, key in (
        ("task", "prompt"),
        ("agent_answer", "agent_answer"),
        ("expert_review", "expert_analysis"),
        ("correction", "corrected_answer"),
    ):
        event = _task_event()
        event["role"] = role
        event["payload"] = {}
        event["event_id"] = deterministic_event_id(event)
        errors = validate_event(event)
        assert any(key in e for e in errors), f"{role} должен требовать {key}"


def test_source_rejects_raw_binary_url() -> None:
    event = _task_event()
    event["source"] = dict(_source(), url="https://example.org/paper.pdf")
    event["event_id"] = deterministic_event_id(event)
    errors = validate_event(event)
    assert any("бинарник" in e for e in errors)


# --- sequence ---------------------------------------------------------------


def test_sequence_rejects_wrong_order() -> None:
    events = [
        _task_event(),
        {**_task_event(), "role": "final", "payload": {"expert_approved": True}},
    ]
    errors = check_sequence(events)
    assert any("порядок" in e for e in errors)


def test_sequence_requires_final() -> None:
    events = [
        _task_event(),
        {**_task_event(), "role": "agent_answer", "payload": {"agent_answer": {}}},
    ]
    errors = check_sequence(events)
    assert any("не завершена" in e for e in errors)


def test_sequence_rejects_unapproved_final() -> None:
    events = [
        _task_event(),
        {**_task_event(), "role": "agent_answer", "payload": {"agent_answer": {}}},
        {
            **_task_event(),
            "role": "expert_review",
            "payload": {"expert_analysis": "ok", "expert_approved": True},
        },
        {**_task_event(), "role": "final", "payload": {"expert_approved": False}},
    ]
    errors = check_sequence(events)
    assert any("expert_approved" in e for e in errors)


def test_full_approved_session_validates(tmp_path: Path) -> None:
    path = tmp_path / "session.jsonl"
    _build_approved_session(path)
    report = validate_session(SessionWriter(path, "SESS-001").events)
    assert report["ok"] is True
    assert report["events"] == 7


# --- append-only / determinism ----------------------------------------------


def test_append_only_preserves_previous_content(tmp_path: Path) -> None:
    path = tmp_path / "session.jsonl"
    w = SessionWriter(path, "SESS-001")
    w.append(
        role="task", round=0, timestamp=TS, source=_source(), payload={"prompt": "p"}
    )
    first = path.read_text(encoding="utf-8")
    w.append(
        role="agent_answer",
        timestamp=TS,
        source=_source(),
        payload={"agent_answer": {"summary": "x"}},
    )
    assert path.read_text(encoding="utf-8").startswith(first)


def test_deterministic_event_ids_are_stable(tmp_path: Path) -> None:
    path_a = tmp_path / "a.jsonl"
    path_b = tmp_path / "b.jsonl"
    _build_approved_session(path_a)
    _build_approved_session(path_b)
    assert path_a.read_text(encoding="utf-8") == path_b.read_text(encoding="utf-8")


def test_duplicate_event_id_rejected(tmp_path: Path) -> None:
    path = tmp_path / "session.jsonl"
    w = SessionWriter(path, "SESS-001")
    w.append(
        role="task", round=0, timestamp=TS, source=_source(), payload={"prompt": "p"}
    )
    # попытка вставить task повторно — отклоняется (и по order, и как повтор)
    try:
        w.append(
            role="task",
            round=0,
            timestamp=TS,
            source=_source(),
            payload={"prompt": "p"},
        )
    except ValueError:
        return
    raise AssertionError("ожидалось отклонение повторного task")


def test_cannot_append_after_final(tmp_path: Path) -> None:
    path = tmp_path / "session.jsonl"
    _build_approved_session(path)
    w = SessionWriter(path, "SESS-001")
    try:
        w.append(
            role="agent_answer",
            timestamp=TS,
            source=_source(),
            payload={"agent_answer": {"summary": "late"}},
        )
    except ValueError as exc:
        assert "завершена" in str(exc)
        return
    raise AssertionError("ожидалось отклонение записи после final")


def test_writer_rejects_foreign_session_file(tmp_path: Path) -> None:
    path = tmp_path / "session.jsonl"
    SessionWriter(path, "SESS-001").append(
        role="task", round=0, timestamp=TS, source=_source(), payload={"prompt": "p"}
    )
    try:
        SessionWriter(path, "OTHER-999")
    except ValueError:
        return
    raise AssertionError("ожидалось отклонение чужого session_id")


# --- secret redaction -------------------------------------------------------


def test_redact_obvious_tokens() -> None:
    text = "token hf_abcd1234efgh Bearer sk-ant-abcdefgh1234 ghp_abcdefgh1234"
    cleaned = redact_text(text)
    assert "hf_" not in cleaned
    assert "sk-ant-" not in cleaned
    assert "ghp_" not in cleaned
    assert "[REDACTED]" in cleaned


def test_writer_redacts_secrets_before_write(tmp_path: Path) -> None:
    path = tmp_path / "session.jsonl"
    w = SessionWriter(path, "SESS-001")
    w.append(
        role="task",
        round=0,
        timestamp=TS,
        source=_source(),
        payload={"prompt": "use key hf_abcd1234efgh to fetch"},
    )
    raw = path.read_text(encoding="utf-8")
    assert "hf_abcd1234efgh" not in raw
    assert "[REDACTED]" in raw


def test_export_strips_local_paths_and_truncates_excerpt(tmp_path: Path) -> None:
    path = tmp_path / "session.jsonl"
    w = SessionWriter(path, "SESS-001")
    source = _source()
    source["local_path"] = r"C:\Users\secret\paper.pdf"
    source["excerpt"] = "x" * 500
    w.append(role="task", round=0, timestamp=TS, source=source, payload={"prompt": "p"})
    clean = export_publishable(w.events, max_excerpt=100)
    assert "local_path" not in clean[0]["source"]
    assert len(clean[0]["source"]["excerpt"]) <= 101


# --- summary ----------------------------------------------------------------


def test_summarize_reports_approval(tmp_path: Path) -> None:
    path = tmp_path / "session.jsonl"
    _build_approved_session(path)
    report = summarize(SessionWriter(path, "SESS-001").events)
    assert report["expert_approved"] is True
    assert report["complete"] is True
    assert report["corrections"] == 1
    assert report["rounds"] == 3


# --- CLI --------------------------------------------------------------------


def test_cli_init_append_validate_summary_export(tmp_path: Path, capsys) -> None:
    import json

    session_file = tmp_path / "session.jsonl"
    task = tmp_path / "task.json"
    task.write_text(
        json.dumps({"prompt": "extract", "source": _source()}, ensure_ascii=False),
        encoding="utf-8",
    )
    code = cli_main(
        [
            "init",
            "--session",
            "SESS-001",
            "--session-file",
            str(session_file),
            "--task",
            str(task),
            "--timestamp",
            TS,
        ]
    )
    assert code == 0
    capsys.readouterr()

    for role, payload, ts in (
        ("agent_answer", {"agent_answer": {"summary": "x"}}, "2026-10-05T10:05:00Z"),
        (
            "expert_review",
            {"expert_analysis": "ok", "expert_approved": True},
            "2026-10-05T10:10:00Z",
        ),
        ("final", {"expert_approved": True}, "2026-10-05T10:15:00Z"),
    ):
        event_file = tmp_path / f"{role}.json"
        event_file.write_text(
            json.dumps(
                {
                    "role": role,
                    "timestamp": ts,
                    "source": _source(),
                    "payload": payload,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        assert (
            cli_main(
                [
                    "append",
                    "--session-file",
                    str(session_file),
                    "--event",
                    str(event_file),
                ]
            )
            == 0
        )
        capsys.readouterr()

    assert cli_main(["validate", "--session-file", str(session_file), "--json"]) == 0
    out = capsys.readouterr().out
    assert json.loads(out)["ok"] is True

    assert cli_main(["summary", "--session-file", str(session_file), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["expert_approved"] is True

    out_file = tmp_path / "publishable.jsonl"
    assert (
        cli_main(
            ["export", "--session-file", str(session_file), "--out", str(out_file)]
        )
        == 0
    )
    assert out_file.is_file()


def test_cli_validate_rejects_unapproved_session(tmp_path: Path, capsys) -> None:
    session_file = tmp_path / "session.jsonl"
    w = SessionWriter(session_file, "SESS-001")
    w.append(
        role="task", round=0, timestamp=TS, source=_source(), payload={"prompt": "p"}
    )
    code = cli_main(["validate", "--session-file", str(session_file), "--json"])
    assert code == 1
    assert "errors" in capsys.readouterr().out


def test_cli_missing_file_returns_2(tmp_path: Path, capsys) -> None:
    code = cli_main(["validate", "--session-file", str(tmp_path / "nope.jsonl")])
    assert code == 2
