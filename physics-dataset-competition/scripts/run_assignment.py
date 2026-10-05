#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Оркестратор первого задания: один прогон от поиска до валидационного бандла.

Использование:
  python scripts/run_assignment.py \\
      --domain AERO --query "..." --slug <slug> \\
      --service all --limit 15 --target-records 3 \\
      --workdir .local/physics-bronze \\
      [--retrieved-at ISO] [--seed 42] [--publish] [--dry-run]

Агент выполняет почти всю работу автономно; эксперт только ВАЛИДИРУЕТ
результат: открывает ``validation-bundle.json`` и подтверждает/исправляет.

Шаги (после каждого печатается компактный JSON-прогресс):
  1. search (metadata-only) → candidates.jsonl
  2. авто-фильтр кандидатов: redistributable + https + allow-list
  3. fetch выбранных (право-гейт сохраняется)
  4. autofill → spec(s)
  5. extract → records.jsonl (нужно ≥ target-records, иначе exit 3)
  6. validate_sample (детерминированно, seed); при ошибках — STOP, exit 1
  7. schema validator + validation-bundle.json для эксперта
  8. HF publisher: dry-run (по умолчанию) или реальный PR (--publish)

Коды возврата: 0 успех, 1 ошибки валидации, 2 blocked (нет входа/секрета),
3 недостаточно redistributable-источников.

Инварианты безопасности: права проверяются до загрузки; секреты только из
окружения и никогда не печатаются; сырые файлы — только в workdir (вне git).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable

# UTF-8 вывод: русский текст не должен падать при перенаправлении stdout/stderr
# на консоли с не-UTF-8 кодировкой (Windows cp1251 и т.п.).
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass

MODULE_ROOT = Path(__file__).resolve().parent.parent
SRC = MODULE_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from physics_ds.collection import manifest as manifest_mod  # noqa: E402
from physics_ds.collection import arxiv, crossref, openalex  # noqa: E402
from physics_ds.collection.download import (  # noqa: E402
    fetch_candidate,
    is_allowed_url,
    write_fetch_manifest,
)
from physics_ds.extract.autofill import (  # noqa: E402
    build_spec,
    resolve_retrieved_at,
    write_spec,
)
from physics_ds.extract.record_builder import build_records  # noqa: E402
from physics_ds.rights.classifier import classify  # noqa: E402
from physics_ds.schema.validate import validate_file, validate_record  # noqa: E402
from physics_ds.validation.checks import (  # noqa: E402
    check_record_domain,
    load_domain_config,
)
from physics_ds.validation.sampling import check_records, sample  # noqa: E402

DOMAINS = ("AERO", "STR", "RADAR", "CTRL")
SERVICES = ("openalex", "arxiv", "crossref", "all")

# Статусы-коды.
EXIT_OK = 0
EXIT_VALIDATION = 1
EXIT_BLOCKED = 2
EXIT_INSUFFICIENT = 3


def _log(step: str, payload: dict[str, Any]) -> None:
    print(json.dumps({"step": step, **payload}, ensure_ascii=False), flush=True)


def _run_search(service: str, domain: str, query: str, limit: int) -> list[dict]:
    """Поиск метаданных. Отдельная функция — легко подменить в тестах."""
    if service == "openalex":
        return openalex.search(query, domain=domain, limit=limit)
    if service == "arxiv":
        return arxiv.search(query, domain=domain, limit=limit)
    if service == "crossref":
        return crossref.search(query, domain=domain, limit=limit)
    merged: list[dict] = []
    for fn in (
        openalex.search(query, domain=domain, limit=limit),
        arxiv.search(query, domain=domain, limit=limit),
        crossref.search(query, domain=domain, limit=limit),
    ):
        merged.extend(fn)
    return merged[:limit]


def filter_candidates(
    rows: list[dict],
) -> tuple[list[dict], list[dict[str, Any]]]:
    """Отфильтровать кандидатов до redistributable + https + allow-list.

    Возвращает ``(selected, skipped)``, где ``skipped`` — причины отказа.
    """
    selected: list[dict] = []
    skipped: list[dict[str, Any]] = []
    for row in rows:
        decision = classify(
            {
                "license": row.get("license"),
                "copyright_status": row.get("copyright_status"),
                "publisher": row.get("publisher"),
                "source_type": row.get("source_type"),
                "permission_ref": row.get("permission_ref"),
                "is_oa": row.get("is_oa"),
            }
        )
        if not decision["redistributable"]:
            skipped.append(
                {
                    "service_id": row.get("service_id"),
                    "reason": f"not redistributable: {decision['basis']}",
                }
            )
            continue
        url = row.get("oa_url") or row.get("source_url")
        ok, why = is_allowed_url(str(url or ""))
        if not ok:
            skipped.append({"service_id": row.get("service_id"), "reason": why})
            continue
        selected.append(row)
    return selected, skipped


def _read_records(path: Path) -> list[dict]:
    records: list[dict] = []
    if not path.is_file():
        return records
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def _write_records(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def _hf_main(argv: list[str]) -> int:
    """Ленивый вызов publisher'а (тяжёлых импортов на старте нет)."""
    import importlib.util

    hf_path = SRC / "physics_ds" / "publish" / "hf.py"
    spec = importlib.util.spec_from_file_location("physics_ds_hf_runner", hf_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.main(argv)


def _enumerate_expert_checks(records: list[dict]) -> list[dict[str, Any]]:
    """Перечислить ровно то, что эксперт обязан подтвердить по каждой записи."""
    checks: list[dict[str, Any]] = []
    for record in records:
        rid = record["record_id"]
        src = record.get("source") or {}
        prov = record.get("provenance") or {}
        rights = record.get("rights") or {}
        values = record.get("values") or []
        checks.append(
            {
                "record_id": rid,
                "source_coordinate": src.get("url"),
                "bronze_sha256": prov.get("sha256"),
                "confirm_rights_basis": rights.get("basis"),
                "confirm_units_and_values": [
                    {
                        "name": v.get("name"),
                        "value": v.get("value"),
                        "unit": v.get("unit"),
                    }
                    for v in values
                ],
            }
        )
    return checks


def _build_bundle(
    *,
    domain: str,
    query: str,
    slug: str,
    counts: dict[str, Any],
    per_source: list[dict[str, Any]],
    sample_report: dict[str, Any],
    records: list[dict],
) -> dict[str, Any]:
    return {
        "domain": domain,
        "query": query,
        "slug": slug,
        "counts": counts,
        "per_source_provenance": per_source,
        "sample_report": sample_report,
        "requires_expert_validation": True,
        "expert_must_confirm": _enumerate_expert_checks(records),
        "note": (
            "Числа предложены регуляркой (auto-extract). Эксперт обязан сверить "
            "каждое значение с первоисточником, подтвердить единицы и основание прав."
        ),
    }


def run(
    args: argparse.Namespace,
    *,
    search_fn: Callable[..., list[dict]] = _run_search,
    fetch_fn: Callable[..., Any] = fetch_candidate,
) -> int:
    workdir = Path(args.workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    candidates_path = workdir / "candidates.jsonl"
    fetch_path = workdir / "fetch-manifest.jsonl"
    spec_path = workdir / "spec.json"
    records_path = workdir / "records.jsonl"
    bundle_path = workdir / "validation-bundle.json"

    try:
        retrieved_at = resolve_retrieved_at(args.retrieved_at)
    except ValueError as exc:
        _log("error", {"code": EXIT_BLOCKED, "error": str(exc)})
        return EXIT_BLOCKED

    # Шаг 1: поиск (metadata-only).
    try:
        rows = search_fn(args.service, args.domain, args.query, args.limit)
    except Exception as exc:  # сеть/парсинг — без секретов
        _log("search", {"status": "error", "error": str(exc)})
        return EXIT_BLOCKED
    manifest_mod.write(candidates_path, rows)
    _log(
        "search", {"status": "ok", "candidates": len(rows), "out": str(candidates_path)}
    )

    # Шаг 2: авто-фильтр.
    selected, skipped = filter_candidates(rows)
    _log(
        "filter",
        {
            "selected": len(selected),
            "skipped": len(skipped),
            "skip_reasons": skipped,
        },
    )

    # Шаг 3: загрузка выбранных.
    outcomes = []
    for row in selected[: args.max_items] if args.max_items > 0 else selected:
        outcomes.append(fetch_fn(row, out_dir=workdir))
    write_fetch_manifest(fetch_path, outcomes)
    downloaded = [o for o in outcomes if o.status == "downloaded"]
    _log(
        "fetch",
        {
            "requested": len(outcomes),
            "downloaded": len(downloaded),
            "skipped": len(outcomes) - len(downloaded),
            "manifest": str(fetch_path),
        },
    )

    # Шаг 4: autofill.
    # Обогащаем строки fetch-манифеста метаданными исходного кандидата (join по
    # service_id): download.py намеренно пишет только хэш/путь, а autofill
    # обязан копировать метаданные источника ИЗ манифеста — не выдумывать.
    candidate_by_id = {str(c.get("service_id")): c for c in selected}
    fetch_rows = manifest_mod.read(fetch_path)
    for frow in fetch_rows:
        cand = candidate_by_id.get(str(frow.get("service_id")))
        if cand:
            merged = dict(cand)
            merged.update({k: v for k, v in frow.items() if v is not None})
            frow.update(merged)
    spec, statuses = build_spec(
        fetch_rows,
        domain=args.domain,
        agent_role_id=args.agent_role_id,
        retrieved_at=retrieved_at,
        bronze_dir=workdir,
        query=args.query,
        target_records=args.target_records,
    )
    write_spec(spec_path, spec)
    _log("autofill", {"records": len(spec["records"]), "spec": str(spec_path)})

    # Шаг 5: extract (с доменными проверками).
    records, errors = build_records(spec)
    domain_errors: list[str] = []
    for i, record in enumerate(records):
        config = load_domain_config(record["domain"])
        for err in check_record_domain(record, config):
            domain_errors.append(f"records[{i}]: {err}")
    if errors or domain_errors:
        _log(
            "extract",
            {"status": "error", "errors": (errors + domain_errors)[:20]},
        )
        return EXIT_VALIDATION
    _write_records(records_path, records)
    _log("extract", {"status": "ok", "records": len(records), "out": str(records_path)})

    if len(records) < args.target_records:
        _log(
            "insufficient",
            {
                "target_records": args.target_records,
                "records": len(records),
                "reason": "insufficient redistributable sources",
            },
        )
        return EXIT_INSUFFICIENT

    # Шаг 6: выборочная проверка (детерминированно); при ошибках — STOP.
    selected_sample = sample(records, args.sample, args.seed)
    sample_report = check_records(selected_sample)
    sample_report["input"] = {
        "sample": args.sample,
        "seed": args.seed,
        "selected": len(selected_sample),
    }
    _log(
        "validate_sample",
        {"ok": sample_report["ok"], "counts": sample_report["counts"]},
    )
    if not sample_report["ok"]:
        _log("stop", {"reason": "validation errors; auto-correction is unsafe"})
        return EXIT_VALIDATION

    # Шаг 7: schema validator + бандл.
    n_records, n_errors, failed = validate_file(records_path)
    if n_errors:
        _log("schema_validate", {"errors": n_errors, "failed": failed[:10]})
        return EXIT_VALIDATION
    _log("schema_validate", {"status": "ok", "records": n_records})

    per_source = []
    for record in records:
        prov = record.get("provenance") or {}
        rights = record.get("rights") or {}
        src = record.get("source") or {}
        per_source.append(
            {
                "record_id": record["record_id"],
                "service_id": prov.get("sha256"),
                "url": src.get("url"),
                "license": src.get("license"),
                "copyright_status": src.get("copyright_status"),
                "redistributable": rights.get("redistributable"),
                "rights_basis": rights.get("basis"),
                "sha256": prov.get("sha256"),
            }
        )

    bundle = _build_bundle(
        domain=args.domain,
        query=args.query,
        slug=args.slug,
        counts={
            "candidates": len(rows),
            "selected": len(selected),
            "skipped": len(skipped),
            "downloaded": len(downloaded),
            "records": len(records),
        },
        per_source=per_source,
        sample_report=sample_report,
        records=records,
    )
    bundle_path.write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    _log(
        "bundle",
        {
            "status": "ok",
            "path": str(bundle_path),
            "requires_expert_validation": True,
            "expert_checks": len(bundle["expert_must_confirm"]),
        },
    )

    # Шаг 8: публикация (dry-run по умолчанию).
    hf_args = [
        "--records",
        str(records_path),
        "--revision",
        f"expert/{args.slug}",
        "--title",
        f"{args.domain}: {len(records)} записей",
    ]
    if args.publish:
        import os

        if not os.environ.get("HF_TOKEN", "").strip():
            _log("publish", {"status": "blocked", "reason": "HF_TOKEN not set"})
            return EXIT_BLOCKED
        _log("publish", {"status": "attempting", "mode": "real"})
        rc = _hf_main(hf_args)
        _log("publish", {"status": "ok" if rc == 0 else "error", "rc": rc})
        return rc if rc == 0 else EXIT_VALIDATION

    rc = _hf_main(hf_args + ["--dry-run"])
    _log("publish", {"status": "dry-run", "rc": rc})

    _log("done", {"status": "success", "bundle": str(bundle_path)})
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Оркестратор первого задания: поиск -> загрузка -> извлечение -> бандл."
    )
    ap.add_argument("--domain", choices=DOMAINS, required=True, help="Домен датасета.")
    ap.add_argument("--query", required=True, help="Поисковый запрос.")
    ap.add_argument(
        "--slug", required=True, help="Слаг для ревизии/PR (expert/<slug>)."
    )
    ap.add_argument("--service", choices=SERVICES, default="all", help="API-сервис.")
    ap.add_argument(
        "--limit", type=int, default=15, help="Кандидатов на поиск (1..20)."
    )
    ap.add_argument("--target-records", type=int, default=3, help="Нужно записей.")
    ap.add_argument(
        "--workdir", default=".local/physics-bronze", help="Рабочий каталог."
    )
    ap.add_argument(
        "--retrieved-at",
        default=None,
        help="Время в ISO-8601 (иначе SOURCE_DATE_EPOCH).",
    )
    ap.add_argument("--seed", type=int, default=42, help="Seed выборочной проверки.")
    ap.add_argument("--sample", type=float, default=1.0, help="Доля выборки 0..1.")
    ap.add_argument(
        "--max-items", type=int, default=0, help="Макс. загрузок (0 = все)."
    )
    ap.add_argument(
        "--agent-role-id", default="agent", help="Роль агента для provenance."
    )
    ap.add_argument(
        "--publish", action="store_true", help="Реальная публикация (нужен HF_TOKEN)."
    )
    ap.add_argument(
        "--dry-run", action="store_true", help="Только dry-run (по умолчанию)."
    )
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not (1 <= args.limit <= 20):
        _log("error", {"error": "--limit должен быть 1..20"})
        return EXIT_BLOCKED
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
