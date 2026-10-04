# SPDX-License-Identifier: GPL-3.0-or-later
"""Тесты сбора: парсинг API, право-гейт загрузки, манифест.

Сеть не используется: клиенты парсят фикстурные payload'ы, а ``download.fetch_candidate``
проверяется на отклонение не-redistributable / не-https входов.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[1]
SRC = MODULE_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from physics_ds.collection import arxiv, crossref, manifest, openalex  # noqa: E402
from physics_ds.collection.download import (  # noqa: E402
    FetchOutcome,
    fetch_candidate,
    is_allowed_url,
    write_fetch_manifest,
)

FIXTURES = MODULE_ROOT / "tests" / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


# --- openalex ----------------------------------------------------------------


def test_openalex_normalizes_work() -> None:
    payload = _load("openalex_works.json")
    work = payload["results"][0]
    cand = openalex.normalize_work(work, domain="AERO", query="airfoil")
    assert cand["service"] == "openalex"
    assert cand["title"].startswith("Wind tunnel")
    assert cand["year"] == 1935
    assert cand["oa_url"] == "https://arxiv.org/pdf/2401.00001"
    assert cand["license"] == "cc-by"  # канонический SPDX-id
    assert cand["is_oa"] is True
    assert cand["provenance_service"] == "openalex.org"
    assert cand["abstract"].startswith("Measured drag")


# --- arxiv -------------------------------------------------------------------


def test_arxiv_parses_atom_feed() -> None:
    xml = (FIXTURES / "arxiv_feed.xml").read_bytes()
    rows = arxiv.parse_feed(xml, domain="AERO", query="airfoil")
    assert len(rows) == 2
    first = rows[0]
    assert first["service_id"] == "2401.00001v1"
    assert first["oa_url"] == "http://arxiv.org/pdf/2401.00001v1"
    assert first["license"] == "cc-by-4.0"
    assert first["year"] == 2024
    assert first["doi"] == "10.1234/arxiv.example"
    # без элемента лицензии права неизвестны
    assert rows[1]["license"] is None


def test_arxiv_single_request_does_not_sleep() -> None:
    slept: list[float] = []

    from physics_ds.collection import http as http_mod

    original = http_mod.get

    def fake_get(url, **kwargs):  # noqa: ARG001
        return (FIXTURES / "arxiv_feed.xml").read_bytes()

    http_mod.get = fake_get  # type: ignore[assignment]
    try:
        rows = arxiv.search("airfoil", domain="AERO", limit=2, sleep=slept.append)
    finally:
        http_mod.get = original  # type: ignore[assignment]
    assert len(rows) == 2
    assert slept == []  # одиночный запрос не спит


def test_arxiv_pagination_sleeps_three_seconds() -> None:
    slept: list[float] = []
    pages = [
        (FIXTURES / "arxiv_feed.xml").read_bytes(),
        (FIXTURES / "arxiv_feed.xml").read_bytes(),
    ]
    calls = {"n": 0}

    from physics_ds.collection import http as http_mod

    original = http_mod.get

    def fake_get(url, **kwargs):  # noqa: ARG001
        body = pages[min(calls["n"], len(pages) - 1)]
        calls["n"] += 1
        return body

    http_mod.get = fake_get  # type: ignore[assignment]
    try:
        # page_size=2 => две страницы по 2 записи
        arxiv.search("airfoil", domain="AERO", limit=4, page_size=2, sleep=slept.append)
    finally:
        http_mod.get = original  # type: ignore[assignment]
    assert slept == [arxiv.POLITE_DELAY_SECONDS]


# --- crossref ----------------------------------------------------------------


def test_crossref_metadata_only() -> None:
    payload = _load("crossref_works.json")
    items = payload["message"]["items"]
    closed = crossref.normalize_item(items[0], domain="STR", query="fatigue")
    assert closed["oa_url"] is None
    assert closed["is_oa"] is False
    assert closed["license"] is None  # нет свободной лицензии
    assert closed["year"] == 1995

    oa = crossref.normalize_item(items[1], domain="STR", query="fatigue")
    assert oa["license"] == "cc-by"
    assert oa["oa_url"] is None  # Crossref не даёт проверенный URL загрузки


def test_crossref_metadata_is_not_redistributable() -> None:
    payload = _load("crossref_works.json")
    item = crossref.normalize_item(
        payload["message"]["items"][0], domain="STR", query="q"
    )
    outcome = fetch_candidate(item, out_dir=Path("__unused__"))
    assert outcome.status == "skipped"
    assert "redistributable" in outcome.reason


# --- download gating ---------------------------------------------------------


def test_download_rejects_non_https() -> None:
    cand = {
        "service_id": "x",
        "title": "t",
        "license": "cc-by-4.0",
        "is_oa": True,
        "oa_url": "http://arxiv.org/pdf/1",
    }
    outcome = fetch_candidate(cand, out_dir=Path("__unused__"))
    assert outcome.status == "skipped"
    assert "https" in outcome.reason


def test_download_rejects_non_allowlisted_host() -> None:
    cand = {
        "service_id": "x",
        "title": "t",
        "license": "cc-by-4.0",
        "is_oa": True,
        "oa_url": "https://evil.example.com/paper.pdf",
    }
    outcome = fetch_candidate(cand, out_dir=Path("__unused__"))
    assert outcome.status == "skipped"
    assert "allow-list" in outcome.reason


def test_is_allowed_url() -> None:
    assert is_allowed_url("https://arxiv.org/pdf/1")[0] is True
    assert is_allowed_url("http://arxiv.org/pdf/1")[0] is False
    assert is_allowed_url("https://example.org/x.pdf")[0] is False
    assert is_allowed_url("")[0] is False


def test_download_writes_bytes_and_hashes(tmp_path: Path, monkeypatch) -> None:
    from physics_ds.collection import download as dl

    def fake_get(url, **kwargs):  # noqa: ARG001
        return b"%PDF-1.4 test-body"

    monkeypatch.setattr(dl.http, "get", fake_get)
    cand = {
        "service_id": "2401.00001v1",
        "title": "t",
        "license": "cc-by-4.0",
        "is_oa": True,
        "oa_url": "https://arxiv.org/pdf/2401.00001v1",
        "provenance_service": "export.arxiv.org",
    }
    outcome = fetch_candidate(cand, out_dir=tmp_path)
    assert outcome.status == "downloaded"
    assert outcome.sha256 is not None and len(outcome.sha256) == 64
    assert Path(outcome.path).read_bytes() == b"%PDF-1.4 test-body"


# --- manifest ----------------------------------------------------------------


def test_manifest_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "cand.jsonl"
    count = manifest.write(
        path, [{"service": "openalex", "title": "a"}, {"service": "arxiv"}]
    )
    assert count == 2
    rows = manifest.read(path)
    assert rows[0]["service"] == "openalex"
    assert rows[0]["title"] == "a"
    # канонический набор полей присутствует (даже если None)
    assert "oa_url" in rows[0]


def test_fetch_manifest_writer(tmp_path: Path) -> None:
    path = tmp_path / "fetch.jsonl"
    n = write_fetch_manifest(
        path,
        [FetchOutcome(service_id="x", status="skipped", reason="r")],
    )
    assert n == 1
    assert json.loads(path.read_text(encoding="utf-8"))["status"] == "skipped"
