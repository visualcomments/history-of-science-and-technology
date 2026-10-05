# Калибровочные сессии эксперта (calibration)

Слой **отдельного экспертного задания**: эксперт скармливает агенту
статью/книгу, агент извлекает данные эксперимента, эксперт указывает **явные
ошибки**, агент повторяет, пока не получит **полное одобрение**. Каждый ход
сохраняется как событие JSONL и публикуется в **отдельный** Hugging Face
dataset цепочек калибровки.

Этот слой хранит **цепочки сессий калибровки**, а не финальные записи
эксперимента. Финальные записи живут в основном датасете
`chaotic-good-project/physics-experiment-records` (см. `docs/HF-DATASET.md`);
калибровки — в `top-papers/physics-agent-calibrations`.

## Формат сессии

Одна сессия — один append-only JSONL-файл. Событие соответствует
`calibration/schema/session.schema.json`:

| Поле | Тип | Описание |
|---|---|---|
| `session_id` | string | Идентификатор сессии (`[A-Za-z0-9._-]{4,64}`). |
| `event_id` | string | Детерминированный hex-id события (SHA-256 от содержимого без `event_id`). |
| `round` | int | Раунд: `0` — постановка задачи, далее `1..N` (ответ + разбор). |
| `role` | enum | `task`, `agent_answer`, `expert_review`, `correction`, `final`. |
| `timestamp` | string | ISO-8601 UTC. Передаётся **явно** (детерминизм, без системных часов). |
| `source` | object | Метаданные/провенанс источника + короткая `excerpt` (≤ 2000). Сырые бинарники запрещены. |
| `payload` | object | `prompt` / `agent_answer` / `expert_analysis` / `errors_found` / `corrected_answer` / `expert_approved`. |

Требуемая последовательность ролей::

```
task -> agent_answer -> expert_review -> (correction -> agent_answer -> expert_review)* -> final
```

* `expert_review` с `expert_approved=false` **обязан** вести к `correction`;
* `final` допустим только сразу после `expert_review` с `expert_approved=true`
  и сам содержит `payload.expert_approved=true`;
* сессия без одобренного `final` невалидна и не экспортируется.

## CLI

```bash
# 1. Создать сессию и первое событие task (JSON-файл: prompt + source)
python physics-dataset-competition/scripts/calibration_session.py init \
  --session SESS-001 --session-file .local/calib/SESS-001.jsonl \
  --task .local/calib/task.json --timestamp 2026-10-05T10:00:00Z

# 2. Дописать одно событие (JSON-файл: role/timestamp/source/payload)
python physics-dataset-competition/scripts/calibration_session.py append \
  --session-file .local/calib/SESS-001.jsonl --event .local/calib/agent-answer.json

# 3. Проверить схему, порядок и одобренный final
python physics-dataset-competition/scripts/calibration_session.py validate \
  --session-file .local/calib/SESS-001.jsonl --json

# 4. Показать прогресс
python physics-dataset-competition/scripts/calibration_session.py summary \
  --session-file .local/calib/SESS-001.jsonl

# 5. Экспорт публикуемого JSONL (без локальных путей, короткие выдержки)
python physics-dataset-competition/scripts/calibration_session.py export \
  --session-file .local/calib/SESS-001.jsonl --out .local/calib/publishable.jsonl
```

Коды возврата: `0` — успех, `1` — невалидные данные/сессия, `2` — нельзя
выполнить (нет файла/аргументов/зависимости). Russian help: `--help`.

## Публикация

```bash
# dry-run: план без сети (число событий, sha256, путь в репозитории)
python physics-dataset-competition/calibration/publish.py \
  --session-file .local/calib/publishable.jsonl --dry-run

# реальный PR (HF_TOKEN только из окружения; create_pr=True, merge не делается)
python physics-dataset-competition/calibration/publish.py \
  --session-file .local/calib/publishable.jsonl \
  --revision expert/sess-001 --title "SESS-001: калибровка AERO"
```

Путь в Hub: `calibrations/<session_id>/session.jsonl` в датасете
`top-papers/physics-agent-calibrations`. `huggingface_hub`
импортируется лениво; токен читается **только** из `HF_TOKEN` и не печатается.

## Инварианты безопасности

* журнал **только дополняется** — файл никогда не перезаписывается, повтор
  `event_id` и запись после `final` отклоняются;
* очевидные токены (`hf_…`, `sk-…`, `ghp_…`, `Bearer …`, `api_key=…`, PEM)
  вырезаются из строковых полей до записи;
* `export` убирает поля с локальными путями и усекает `source.excerpt`;
* сырые тексты/сканы/PDF не хранятся — только метаданные и короткая выдержка.

## Связь с финальным датасетом эксперимента

| | Калибровки (этот слой) | Финальные записи |
|---|---|---|
| Датасет | `top-papers/physics-agent-calibrations` | `chaotic-good-project/physics-experiment-records` |
| Единица | цепочка сессии (task → … → final) | запись по `record.schema.json` |
| Назначение | обучить/оценить агента-экстрактора и зафиксировать путь правок | итоговые физические измерения |
| Валидация | `calibration/session.py` (порядок + одобренный `final`) | `physics_ds.schema.validate` |

Калибровочная сессия — это **журнал того, как получалась** запись: задача,
ответ агента, явные ошибки эксперта, исправления и итоговое одобрение. После
одобрения итоговые числа проверяются по первоисточнику и попадают в основной
датасет отдельным пайплайном (`record_builder` + `rights.classifier`).

## Тесты

```bash
python -m pytest physics-dataset-competition/tests/calibration -q
```

Тесты без сети: валидация последовательности, append-only, отклонение
невалидных/неупорядоченных/с секретами/неодобренных сессий, детерминизм
`event_id`, dry-run публикации без токена.
