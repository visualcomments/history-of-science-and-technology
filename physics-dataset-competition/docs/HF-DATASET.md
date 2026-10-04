# Публичный датасет на Hugging Face Hub

Целевой репозиторий: **`chaotic-good-project/physics-experiment-records`** (dataset).

## Ожидаемая структура репозитория

```
chaotic-good-project/physics-experiment-records/
├── README.md                      # dataset card (см. ниже)
├── submissions/
│   └── <slug>/                    # по одной папке на эксперта/ветку
│       └── records.jsonl          # записи в канонической схеме v1
├── data/                          # (по мере наполнения) агрегаты
│   └── all-records.jsonl
├── CITATION.cff
└── LICENSE
```

- **`submissions/<slug>/records.jsonl`** — единственный путь, который пишет
  publisher (`src/physics_ds/publish/hf.py`), где `<slug>` — часть ревизии
  после `/` (например, ревизия `expert/ivan-aero` → `submissions/ivan-aero/`).
- Агрегацию `data/all-records.jsonl` и обновление dataset card выполняет
  сопровождающий/CI после ревью; publisher по умолчанию их **не трогает**.

## Dataset card (`README.md`) — разделы

1. **Название и назначение** — датасет экспериментальных физических измерений.
2. **Домены** — AERO / STR / RADAR / CTRL.
3. **Схема** — ссылка на `configs/schema/record.schema.json`, версия схемы.
4. **Происхождение и права** — описание `rights`/`provenance`; отдельно
   перечислить использованные OA-платформы и лицензии.
5. **Сборка и валидация** — как воспроизвести (`scripts/collect.py`,
   `scripts/extract.py`, `scripts/validate_sample.py`).
6. **Ограничения и этика** — только свободные лицензии; нет PII; нет сканов
   охраняемых работ.
7. **CITATION** — как цитировать; `CITATION.cff` в репозитории.

## PR-конвенция

1. Ревизия (ветка) — `expert/<slug>`; slug — латиница/цифры/`._-`.
2. Файл — `submissions/<slug>/records.jsonl`.
3. Заголовок PR — `<ДОМЕН>: <N> записей (<год/источник>)`.
4. В описании — provenance-сводка и результат выборочной проверки.
5. Ревьюер проверяет: `rights.redistributable=true`, `validation.status=accepted`,
   0 ошибок выборочной проверки, отсутствие сырых источников.
6. Publisher создаёт PR (`create_pr=True`) и **не** выполняет merge.

Команда публикации:

```bash
# dry-run (без сети): число записей, sha256, ревизия, пути
python physics-dataset-competition/src/physics_ds/publish/hf.py \
  --records .local/physics-bronze/records.jsonl --dry-run

# реальный PR (HF_TOKEN только из окружения)
python physics-dataset-competition/src/physics_ds/publish/hf.py \
  --records .local/physics-bronze/records.jsonl \
  --repo-id chaotic-good-project/physics-experiment-records \
  --revision expert/<slug> \
  --title "AERO: 3 записи (1935, NASA)"
```

## Настройка секрета

- Секрет: **только** `HF_TOKEN` в переменной окружения.
- Токен — fine-grained, права `write` **только** на целевой dataset-репозиторий
  (least privilege, DESIGN §8).
- **Никогда** не коммитить токен, не печатать его и не передавать в аргументах
  CLI; publisher читает его из окружения и не логирует.
- Локальная установка опциональной зависимости:

```bash
python -m pip install -r physics-dataset-competition/docs/requirements-publish.txt
```

(`huggingface_hub` используется лениво только в не-dry-run ветке.)

## Откат / отзыв публикации

- **Отозвать файл:** закрыть PR, не мержить, либо отдельным PR удалить
  `submissions/<slug>/records.jsonl`.
- **Откат ревизии:** в Hub вернуться к предыдущему коммиту (revert через
  интерфейс/`create_commit`), затем при необходимости пересобрать агрегат.
- **При инциденте прав (`copyright-breach`):** немедленно снять артефакт,
  зафиксировать в incident-логе, переклассифицировать запись через
  `rights.classifier`, при необходимости выпустить новую запись со ссылкой
  `parent_record_id` (см. `docs/RUNBOOK.md`).
- Все действия фиксировать в отчёте; merge в `main` до завершения разбирательства
  не выполнять.
