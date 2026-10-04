#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Воспроизводимый benchmark-харнесс (DESIGN §14.2, §18.2).

Читает ``configs/metrics.yaml`` и ``configs/splits.yaml``, строит grouped+temporal
разбиение 60/20/20 с embargo и считает метрики на встроенной мини-фикстуре
(или на ``--records PATH``). Без сети, без внешних зависимостей.

Использование:
  python run.py                 # встроенная фикстура
  python run.py --records data/gold/records.jsonl
  python run.py --json
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any

# Самодостаточность: добавляем <repo>/physics-dataset-competition/src в sys.path.
MODULE_ROOT = Path(__file__).resolve().parent.parent
SRC = MODULE_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from physics_ds.ml.metrics import mae, rmse  # noqa: E402
from physics_ds.validation.checks import parse_simple_yaml  # noqa: E402


def load_config(name: str) -> dict[str, Any]:
    path = MODULE_ROOT / "configs" / name
    if path.suffix == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    return parse_simple_yaml(path.read_text(encoding="utf-8"))


def split_records(
    records: list[dict[str, Any]],
    splits_cfg: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    """Детерминированное grouped+temporal разбиение 60/20/20 с embargo.

    Алгоритм: сортируем по ``(year, group, record_id)``, режем по накопленному
    числу групп (source.id), а не записей, чтобы группы не пересекались. Между
    train и val/test действует embargo по годам (группы, чей год ближе
    ``embargo_years`` к границе, исключаются).
    """
    seed = int(splits_cfg.get("seed", 42))
    ratios = splits_cfg.get("ratios") or {"train": 0.6, "val": 0.2, "test": 0.2}
    embargo = int(splits_cfg.get("embargo_years", 0))
    del seed  # seed фиксирует порядок; здесь сортировка детерминирована

    # group_by = source.id; year = period -> year.
    def year_of(rec: dict[str, Any]) -> int:
        src = rec.get("source") or {}
        y = src.get("year")
        if isinstance(y, int):
            return y
        period = str(rec.get("period") or "")
        if "-" in period:
            try:
                return int(period.split("-")[0])
            except ValueError:
                return 0
        return 0

    def group_of(rec: dict[str, Any]) -> str:
        src = rec.get("source") or {}
        return str(src.get("id") or src.get("title") or rec.get("record_id") or "?")

    grouped: dict[str, list[dict[str, Any]]] = {}
    for rec in records:
        grouped.setdefault(group_of(rec), []).append(rec)

    ordered_groups = sorted(
        grouped.items(),
        key=lambda kv: (min(year_of(r) for r in kv[1]), kv[0]),
    )

    n_groups = len(ordered_groups)
    n_train = max(1, round(n_groups * float(ratios.get("train", 0.6))))
    n_val = max(1, round(n_groups * float(ratios.get("val", 0.2))))
    # остаток — test; при малом n гарантируем хотя бы одну группу.
    if n_train + n_val >= n_groups:
        n_train = max(1, n_groups - 2)
        n_val = 1

    train_groups = ordered_groups[:n_train]
    val_groups = ordered_groups[n_train : n_train + n_val]
    test_groups = ordered_groups[n_train + n_val :]

    def collect(groups: list[tuple[str, list[dict[str, Any]]]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for _, recs in groups:
            out.extend(recs)
        return sorted(
            out, key=lambda r: (year_of(r), group_of(r), r.get("record_id", ""))
        )

    train = collect(train_groups)
    val = collect(val_groups)
    test = collect(test_groups)

    # Embargo: убираем из train группы, чей год слишком близок к test.
    if embargo and test:
        test_min_year = min(year_of(r) for r in test)
        train = [r for r in train if year_of(r) <= test_min_year - embargo]

    return {"train": train, "val": val, "test": test}


def evaluate(
    records: list[dict[str, Any]],
    metrics_cfg: dict[str, Any],
) -> dict[str, Any]:
    """Посчитать метрики по доменам на записях, где есть target/prediction."""
    del metrics_cfg
    per_domain: dict[str, dict[str, float]] = {}
    for rec in records:
        domain = str(rec.get("domain") or "?")
        target = rec.get("target")
        pred = rec.get("prediction")
        if target is None or pred is None:
            continue
        bucket = per_domain.setdefault(domain, {})
        bucket.setdefault("_y", []).append(float(target))  # type: ignore[arg-type]
        bucket.setdefault("_p", []).append(float(pred))  # type: ignore[arg-type]

    result: dict[str, Any] = {}
    for domain, data in sorted(per_domain.items()):
        ys, ps = data["_y"], data["_p"]
        result[domain] = {"rmse": rmse(ys, ps), "mae": mae(ys, ps), "n": len(ys)}
    if result:
        domain_scores = [v["rmse"] for v in result.values()]
        result["normalized_rmse"] = sum(domain_scores) / len(domain_scores)
    return result


def _fixture() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Встроенная мини-фикстура: 3 группы источников, 6 записей, 4 домена."""
    records = [
        {
            "record_id": "AERO-00000001",
            "domain": "AERO",
            "source": {"id": "src-a", "year": 1935},
            "target": 0.10,
            "prediction": 0.12,
        },
        {
            "record_id": "AERO-00000002",
            "domain": "AERO",
            "source": {"id": "src-a", "year": 1936},
            "target": 0.30,
            "prediction": 0.28,
        },
        {
            "record_id": "STR-00000001",
            "domain": "STR",
            "source": {"id": "src-b", "year": 1955},
            "target": 250.0,
            "prediction": 245.0,
        },
        {
            "record_id": "STR-00000002",
            "domain": "STR",
            "source": {"id": "src-b", "year": 1956},
            "target": 300.0,
            "prediction": 310.0,
        },
        {
            "record_id": "RADAR-0000001",
            "domain": "RADAR",
            "source": {"id": "src-c", "year": 1980},
            "target": -10.0,
            "prediction": -9.0,
        },
        {
            "record_id": "CTRL-00000001",
            "domain": "CTRL",
            "source": {"id": "src-c", "year": 1981},
            "target": 45.0,
            "prediction": 47.0,
        },
    ]
    metrics = {"primary": "normalized_rmse", "per_domain": {"AERO": "rmse"}}
    return records, metrics


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Benchmark physical-dataset harness (DESIGN §14.2)"
    )
    ap.add_argument(
        "--records", help="JSONL с записями (по умолчанию встроенная фикстура)"
    )
    ap.add_argument("--json", action="store_true", help="печать полного JSON")
    args = ap.parse_args(argv)

    metrics_cfg = load_config("metrics.yaml")
    splits_cfg = load_config("splits.yaml")

    if args.records:
        path = Path(args.records)
        if not path.is_file():
            print(f"ошибка: файл не найден: {path}", file=sys.stderr)
            return 2
        records = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        metrics_cfg = metrics_cfg
    else:
        records, metrics_cfg = _fixture()

    splits = split_records(records, splits_cfg)
    report: dict[str, Any] = {
        "dataset_version": "v1.0.0",
        "splits_version": splits_cfg.get("splits_version", "splits-v1"),
        "seed": splits_cfg.get("seed", 42),
        "sizes": {k: len(v) for k, v in splits.items()},
        "metrics": evaluate(splits["test"], metrics_cfg),
    }
    report["metrics"]["mean_absolute_deviation_probe"] = round(
        statistics.fmean([float(r.get("target", 0.0)) for r in splits["test"]])
        if splits["test"]
        else 0.0,
        6,
    )

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
