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
│   ├── validation/sampling.py      # детерминированная выборка + отчёт
│   ├── provenance/writer.py        # append-only JSONL (PROV-O)
│   ├── rights/classifier.py        # decision tree §5.3
│   ├── collection/                 # OpenAlex/arXiv/Crossref + fetch (stdlib)
│   ├── extract/record_builder.py   # сборка записей из спека эксперта
│   ├── ml/metrics.py               # RMSE/MAE/MAPE/R²/violations
│   └── publish/hf.py               # HF Hub PR (lazy huggingface_hub)
├── scripts/
│   ├── collect.py                  # search (metadata) / fetch (lawful OA)
│   ├── extract.py                  # собрать записи из спека
│   ├── validate_sample.py          # выборочная проверка
│   └── correct.py                  # запись-исправление (append-only)
├── benchmark/run.py                # воспроизводимый harness
├── data/{bronze,silver,gold}/      # слои данных (в git только .gitkeep)
├── tests/                          # фикстуры и тесты
└── docs/
    ├── EXPERT-ASSIGNMENT.md        # первое задание эксперта (полная процедура)
    ├── OPENCODE-EXPERT-PROMPT.md   # copy-pastable промпт для агента
    ├── HF-DATASET.md               # формат HF-репозитория и PR
    ├── requirements-publish.txt    # опциональный huggingface_hub
    └── RUNBOOK.md                  # инциденты и восстановление
```

## Документация эксперта

- **[docs/EXPERT-ASSIGNMENT.md](docs/EXPERT-ASSIGNMENT.md)** — полная процедура
  первого задания: поиск, lawful-загрузка, извлечение, проверка, PR. Есть rubric
  и DoD.
- **[docs/OPENCODE-EXPERT-PROMPT.md](docs/OPENCODE-EXPERT-PROMPT.md)** —
  готовый промпт для OpenCode-агента (строгие правила: не выдумывать данные,
  не скачивать paywall, `blocked` при неизвестных правах).
- **[docs/HF-DATASET.md](docs/HF-DATASET.md)** — структура Hub-репозитория,
  dataset card, PR-конвенция, секрет `HF_TOKEN`, откат.
- **[docs/RUNBOOK.md](docs/RUNBOOK.md)** — классы инцидентов и восстановление.

## Быстрый старт

```bash
# 1. Проверить валидатор (доказывает, что он умеет падать)
python physics-dataset-competition/src/physics_ds/schema/validate.py --selftest

# 2. Провалидировать записи
python physics-dataset-competition/src/physics_ds/schema/validate.py \
    physics-dataset-competition/tests/fixtures/records.valid.jsonl --json

# 3. Запустить benchmark (встроенная фикстура)
python physics-dataset-competition/benchmark/run.py --json

# 4. Поиск (metadata-only) и lawful-загрузка OA
python physics-dataset-competition/scripts/collect.py search \
    --service openalex --domain AERO --query "airfoil drag" --limit 10 \
    --out .local/physics-bronze/candidates.jsonl
python physics-dataset-competition/scripts/collect.py fetch \
    --manifest .local/physics-bronze/candidates.jsonl \
    --out-dir .local/physics-bronze --max-items 5

# 5. Извлечение, проверка, публикация
python physics-dataset-competition/scripts/extract.py \
    --spec .local/physics-bronze/spec.aero.json \
    --out .local/physics-bronze/records.jsonl
python physics-dataset-competition/scripts/validate_sample.py \
    --records .local/physics-bronze/records.jsonl --sample 0.5 --seed 42
python physics-dataset-competition/src/physics_ds/publish/hf.py \
    --records .local/physics-bronze/records.jsonl --dry-run

# 6. Тесты
python -m pytest physics-dataset-competition/tests/ -q
```

### Локальное хранилище

Скачанные первоисточники (PDF/сканы) живут **только** в
`.local/physics-bronze/` и не коммитятся (см. `.gitignore` модуля). В git
допускаются только `.gitkeep`-заглушки в `data/` и `docs/reports/`.


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
