# physics-dataset-competition — физический датасет и соревнование

Отдельный модуль открытого курса «История России: история и философия науки и
технологий». Реализует конвейер «поиск → сбор → оцифровка → схема → валидация →
публикация → соревнование» для четырёх физических доменов (DESIGN §1, §3).

## Домены

| Домен | Что собираем | Типичные поля |
|---|---|---|
| **AERO** | аэродинамика: поляры, Cx/Cy(α), распределение давления | `Re`, `Ma`, `alpha`, `Cx`, `Cy`, `Cm` |
| **STR** | теория прочности: σ–ε, пределы прочности/текучести, усталость | `E`, `sigma`, `epsilon`, `N` |
| **RADAR** | радиолокация: RCS(θ, f), диаграммы, SNR | `theta`, `f`, `RCS`, `SNR` |
| **CTRL** | системы управления: переходные процессы, АЧХ/ФЧХ, запасы | `Kp`, `Ki`, `Kd`, `T`, `gain_margin`, `phase_margin` |

## Структура

```
physics-dataset-competition/
├── configs/
│   ├── schema/record.schema.json   # каноническая схема v1 (DESIGN §4.2)
│   ├── domains/{aero,str,radar,ctrl}.yaml
│   ├── splits.yaml                 # grouped+temporal 60/20/20, embargo
│   ├── metrics.yaml                # основная метрика и tie-break
│   └── sources.yaml                # реестр источников по периодам (§5.1)
├── src/physics_ds/
│   ├── schema/validate.py          # stdlib-валидатор JSONL
│   ├── validation/checks.py        # диапазоны, единицы, conditions
│   ├── provenance/writer.py        # append-only JSONL (PROV-O)
│   ├── rights/classifier.py        # decision tree §5.3
│   ├── collection/                 # адаптеры сбора (заглушка)
│   ├── ml/metrics.py               # RMSE/MAE/MAPE/R²/violations
│   └── publish/                    # HF/Kaggle (заглушка)
├── benchmark/run.py                # воспроизводимый harness
├── data/{bronze,silver,gold}/      # слои данных
├── tests/                          # фикстуры и тесты
└── docs/RUNBOOK.md                 # инциденты и восстановление
```

## Быстрый старт

```bash
# 1. Проверить валидатор (доказывает, что он умеет падать)
python physics-dataset-competition/src/physics_ds/schema/validate.py --selftest

# 2. Провалидировать записи
python physics-dataset-competition/src/physics_ds/schema/validate.py \
    physics-dataset-competition/tests/fixtures/records.valid.jsonl --json

# 3. Запустить benchmark (встроенная фикстура)
python physics-dataset-competition/benchmark/run.py --json

# 4. Тесты
python -m pytest tests/test_physics_dataset.py -q
```

## Слои данных (DESIGN §4.1)

- **bronze** — сырые артефакты: ссылки и хэши; сами охраняемые файлы не хранятся.
- **silver** — нормализованные таблицы по схеме v1.
- **gold** — вручную проверенный golden set и splits для benchmark.

## Права и провенанс

- Каждая запись содержит `rights` и `provenance` (W3C PROV-O).
- Классификация прав — дерево решений §5.3 (`physics_ds.rights.classify`).
- Все шаги пайплайна пишутся append-only в JSONL с SHA-256 входа/выхода.
- **Запрещено** коммитить сканы/PDF охраняемых работ, обходить paywall или
  нарушать ToS/robots.txt.

## Ограничения реализации

Конвейер CI обязан оставаться stdlib-only. Там, где DESIGN §18.1 упоминает
`jsonschema`, `pydantic`, `pandera`, здесь реализованы эквивалентные
структурные/диапазонные проверки на стандартной библиотеке — тяжёлые
зависимости в CI не добавляются.

## Инциденты

Классы инцидентов (`data-corruption`, `copyright-breach`, `pii-leak`,
`ci-outage`, `api-outage`, `cost-overrun`) и шаги восстановления — в
`docs/RUNBOOK.md`.
