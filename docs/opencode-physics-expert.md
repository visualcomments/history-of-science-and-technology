# OpenCode: первое экспертное задание физического модуля (маршрутизация)

Краткий документ-маршрутизатор для агента OpenCode, сопровождающего
участника в первом экспертном задании модуля
`physics-dataset-competition`. Полные инструкции — в модуле; здесь —
роль, границы, порядок команд и правила безопасности.

## Роль агента и согласие участника

- Агент — **ассистент эксперта**: помогает искать источники в официальных
  API, готовить спецификации извлечения, запускать проверки и публикацию.
  Решения о правах принимает эксперт; агент не выдумывает данные и
  метаданные.
- Задание предлагается **только с явного согласия** участника
  (consent-gate, как и первое задание курса): «хотите выполнить
  исследовательское задание по физическим данным? Домен — один из
  AERO/STR/RADAR/CTRL». Без согласия — не начинать конвейер.
- Исследовательский трек использует **физическую схему** модуля, а не
  универсальную схему первого вклада `assignments/00-first-contribution/`.

## Полные документы (источник истины)

- Процедура целиком — `physics-dataset-competition/docs/EXPERT-ASSIGNMENT.md`.
- Жёсткие правила и промпт агента —
  `physics-dataset-competition/docs/OPENCODE-EXPERT-PROMPT.md`.
- Формат Hub-репозитория — `physics-dataset-competition/docs/HF-DATASET.md`.
- Схема записи — `physics-dataset-competition/configs/schema/record.schema.json`.
- Пример спецификации извлечения —
  `physics-dataset-competition/tests/fixtures/spec.aero.json`.

## Порядок команд (из корня репозитория)

```bash
# 1. Поиск метаданных (metadata-only, ничего не скачивает)
make physics-search QUERY="wind tunnel airfoil drag coefficient" DOMAIN=AERO
#   → .local/physics-bronze/candidates.jsonl

# 2. Право-гейт: показать кандидатов эксперту (is_oa/license/service);
#    загрузка — только после явного одобрения, только redistributable.
python physics-dataset-competition/scripts/collect.py fetch \
  --manifest .local/physics-bronze/candidates.jsonl \
  --out-dir .local/physics-bronze --max-items 5

# 3. Спецификация извлечения (эксперт/агент) → сбор записей
make physics-extract SPEC=.local/physics-bronze/spec.aero.json \
  MANIFEST=.local/physics-bronze/candidates.jsonl DOMAIN=AERO
#   → .local/physics-bronze/records.jsonl

# 4. Детерминированная выборочная проверка (критерий — 0 ошибок)
make physics-sample-check RECORDS=.local/physics-bronze/records.jsonl

# 5. Исправления — append-only (новая запись с parent_record_id)
python physics-dataset-competition/scripts/correct.py \
  --record corrected.json --parent-record-id AERO-XXXXXXXXXX \
  --records .local/physics-bronze/records.jsonl \
  --out .local/physics-bronze/records.jsonl

# 6. Публикация: сначала dry-run, затем реальный PR (PUBLISH=1)
make physics-hf-pr RECORDS=.local/physics-bronze/records.jsonl
make physics-hf-pr RECORDS=.local/physics-bronze/records.jsonl \
  PUBLISH=1 REVISION=expert/<slug> TITLE="<домен>: N записей"
# Целевой датасет: https://huggingface.co/datasets/chaotic-good-project/physics-experiment-records
```

Тесты модуля перед публикацией: `python -m pytest physics-dataset-competition/tests/ -q`.

## Права, безопасность, секреты

- Скачанные первоисточники — **только** в `.local/physics-bronze/`
  (каталог вне git); raw-файлы в репозиторий не попадают.
- Токен Hugging Face — **только** через переменную окружения `HF_TOKEN`;
  не печатать, не писать в файлы/логи, не передавать в командной строке.
- Загрузка — только через `collect.py fetch` (отклоняет не-redistributable,
  не-https и хосты вне allow-list). Обход paywall/robots.txt/ToS запрещён;
  статус `skipped`/`metadata-only` — корректный исход, а не ошибка.
- Права не угадываются: `rights.basis` — только реальное основание;
  при неясности — пометить `blocked` и спросить эксперта.
- Исправления — append-only (`correct.py`), историю записей не переписывать.
- Агент не коммитит и не публикует за участника.

## Доказательство выполнения

1. `≥ 3` принятых записей из `≥ 2` источников выбранного домена
   (`validation.status = accepted`).
2. Отчёт выборочной проверки с **0 ошибок** (`make physics-sample-check`
   → exit 0).
3. URL созданного Hub-PR записан в отчёт участника (для зачёта достаточно
   dry-run только при объективной невозможности сети; полный балл — PR).
4. В отчёте указано, где использовался ИИ (раскрытие, `CONTRIBUTING.md`).
