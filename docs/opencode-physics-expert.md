# OpenCode: первое экспертное задание физического модуля (маршрутизация)

Из корня репозитория задание запускается командой **`/phys-expert`** или
фразой **«начинайте выполнение первого задания для эксперта»** — агент
`phys-expert` настроен в репозитории (`.opencode/agent/phys-expert.md`,
`.opencode/command/phys-expert.md`, `opencode.json`). После первого появления
этих файлов перезапустите OpenCode, чтобы он их подхватил.

Краткий документ-маршрутизатор для агента OpenCode, сопровождающего
участника в первом экспертном задании модуля
`physics-dataset-competition`. Полные инструкции — в модуле; здесь —
роль, границы, порядок команд и правила безопасности.

## Роль агента и согласие участника

- Режим — **«агент делает работу, эксперт валидирует результат»**: агент сам
  проходит весь конвейер (официальные API → право-гейт → lawful-загрузка →
  авто-извлечение → сборка → выборочная проверка → пакет для проверки), а
  участник **подтверждает** итоговые числа по первоисточнику. Агент не
  выдумывает данные и метаданные.
- Задание предлагается **только с явного согласия** участника
  (consent-gate, как и первое задание курса): «хотите выполнить
  исследовательское задание по физическим данным? Домен — один из
  AERO/STR/RADAR/CTRL». Без согласия — не начинать конвейер.
- Исследовательский трек использует **физическую схему** модуля, а не
  универсальную схему первого вклада `assignments/00-first-contribution/`.

## Полные документы (источник истины)

- **Пошаговая инструкция целиком —
  `physics-dataset-competition/docs/EXPERT-GUIDE.md`** (начать здесь).
- Краткая версия задания —
  `physics-dataset-competition/docs/EXPERT-ASSIGNMENT.md`.
- Жёсткие правила и промпт агента —
  `physics-dataset-competition/docs/OPENCODE-EXPERT-PROMPT.md`.
- Формат Hub-репозитория — `physics-dataset-competition/docs/HF-DATASET.md`.
- Схема записи — `physics-dataset-competition/configs/schema/record.schema.json`.
- Пример спецификации извлечения —
  `physics-dataset-competition/tests/fixtures/spec.aero.json`.

## Порядок команд (из корня репозитория)

Режим — **«агент делает работу, эксперт валидирует результат»**: один запуск
оркестратора вместо ручных шагов.

```bash
# Один запуск: поиск → авто-фильтр прав → lawful-загрузка → авто-извлечение →
# сборка записей → выборочная проверка → схемный валидатор → validation-bundle.json
python physics-dataset-competition/scripts/run_assignment.py \
  --domain AERO --query "wind tunnel airfoil drag coefficient" --slug aero-2026-10 \
  --service all --limit 15 --target-records 3 \
  --workdir .local/physics-bronze \
  --retrieved-at "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
#   → .local/physics-bronze/validation-bundle.json  (пакет для эксперта)

# Эксперт проверяет числа по первоисточнику; при замечаниях — append-only фикс:
python physics-dataset-competition/scripts/correct.py \
  --record corrected.json --parent-record-id AERO-XXXXXXXXXX \
  --records .local/physics-bronze/records.jsonl \
  --out .local/physics-bronze/records.jsonl
python physics-dataset-competition/scripts/validate_sample.py \
  --records .local/physics-bronze/records.jsonl --sample 0.5 --seed 42 \
  --report .local/physics-bronze/sample-report.json

# Публикация: dry-run по умолчанию; реальный PR — --publish (HF_TOKEN из окружения)
python physics-dataset-competition/scripts/run_assignment.py \
  --domain AERO --query "..." --slug aero-2026-10 --publish \
  --retrieved-at "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
# Целевой датасет: https://huggingface.co/datasets/chaotic-good-project/physics-experiment-records
```

Коды возврата оркестратора: `0` успех (пакет готов), `1` ошибки валидации,
`2` blocked (нет входа/секрета), `3` недостаточно разрешённых источников.

Тесты модуля перед публикацией: `python -m pytest physics-dataset-competition/tests/ -q`.

Отдельные шаги (если нужны по одному): `make physics-search`,
`make physics-extract`, `make physics-sample-check`, `make physics-hf-pr`; а также
`scripts/collect.py`, `scripts/autofill.py`, `scripts/extract.py`,
`scripts/validate_sample.py`, `scripts/correct.py`.

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
2. Отчёт выборочной проверки с **0 ошибок** (в пакете
   `validation-bundle.json`; `run_assignment.py` → exit 0).
3. Эксперт **подтвердил** числа по первоисточнику (единицы, знаки, условия) —
   в отчёте указано, что именно он проверил.
4. URL созданного Hub-PR записан в отчёт участника (для зачёта достаточно
   dry-run только при объективной невозможности сети; полный балл — PR).
5. В отчёте указано, где использовался ИИ (раскрытие, `CONTRIBUTING.md`).
