# Пошаговая инструкция эксперту и агенту: первое задание

Подробное руководство по выполнению первого задания в модуле
`physics-dataset-competition`: полный цикл «поиск → lawful-загрузка →
извлечение → проверка → исправления → Hub PR». Документ рассчитан на две
аудитории одновременно:

- **Эксперт** (роль EXP/DOMAIN) — принимает решения о правах, физической
  корректности и исправлениях;
- **OpenCode-агент** — выполняет механическую работу по точным командам,
  но ничего не выдумывает и не решает за эксперта.

Краткая версия задания — `EXPERT-ASSIGNMENT.md`; готовый промпт для агента —
`OPENCODE-EXPERT-PROMPT.md`; формат Hub-репозитория — `HF-DATASET.md`.
Этот документ — самая полная версия: выполнйте его построчно.

## Запуск с агентом OpenCode

Задание можно выполнить вместе с агентом, который уже настроен в репозитории.
Из корня репозитория в OpenCode:

- команда **`/phys-expert`** — запускает агента `phys-expert`; или
- фраза **«начинайте выполнение первого задания для эксперта»** — агент
  распознаёт её и начинает с consent-gate.

Агент задаст те же шаги, что и ниже: домен и запрос → поиск → право-гейт →
lawful-загрузка → извлечение → выборочная проверка → исправления → тесты →
Hub PR. Конфигурация лежит в репозитории: `.opencode/agent/phys-expert.md`,
`.opencode/command/phys-expert.md`, `opencode.json`. После первого добавления
этих файлов нужно один раз перезапустить OpenCode, чтобы он их подхватил.

Если предпочитаете вести всё вручную — выполняйте шаги ниже без агента.

---

## Содержание

1. [Что получится в итоге (DoD)](#1-что-получится-в-итоге-dod)
2. [Подготовка окружения](#2-подготовка-окружения)
3. [Шаг 1. Выбор домена и поискового запроса](#шаг-1-выбор-домена-и-поискового-запроса)
4. [Шаг 2. Поиск по официальным API](#шаг-2-поиск-по-официальным-api)
5. [Шаг 3. Право-гейт: разбор кандидатов](#шаг-3-право-гейт-разбор-кандидатов)
6. [Шаг 4. Lawful-загрузка источников](#шаг-4-lawful-загрузка-источников)
7. [Шаг 5. Извлечение записей](#шаг-5-извлечение-записей)
8. [Шаг 6. Выборочная проверка](#шаг-6-выборочная-проверка)
9. [Шаг 7. Исправления (append-only)](#шаг-7-исправления-append-only)
10. [Шаг 8. Финальные тесты](#шаг-8-финальные-тесты)
11. [Шаг 9. Публикация Hub PR](#шаг-9-публикация-hub-pr)
12. [Шаг 10. Отчёт о выполнении](#шаг-10-отчёт-о-выполнении)
13. [Частые ошибки и как их не допустить](#13-частые-ошибки-и-как-их-не-допустить)
14. [Rubric](#rubric-100-баллов)

---

## 1. Что получится в итоге (DoD)

Работа считается выполненной, когда одновременно верно всё:

1. **≥ 3 записи** (`validation.status = accepted`) из **≥ 2 разных
   источников** по выбранному домену.
2. У каждой записи **воспроизводимые права**: `rights.redistributable = true`,
   а `rights.basis` объясняет основание по дереву §5.3.
3. Выборочная проверка даёт **0 ошибок** (`validate_sample.py` → код 0).
4. Открыт **Hub PR**, и его URL записан в отчёт. Эксперт **не** выполняет
   merge.
5. Скачанные первоисточники лежат **только** в `.local/physics-bronze/`
   (этот каталог в `.gitignore`; в git его нет).

Домены: `AERO`, `STR`, `RADAR`, `CTRL`.

---

## 2. Подготовка окружения

Все команды выполняются **из корня репозитория**.

```bash
# Проверить, что инструменты модуля работают (ничего не скачивает, сети нет):
python -m pytest physics-dataset-competition/tests/ -q
```

Ожидается `passed` без ошибок. Если тесты падают — сначала восстановите
окружение, а не начинайте сбор.

Рабочий каталог для локальных артефактов:

```bash
mkdir -p .local/physics-bronze
```

> **Почему `.local/physics-bronze/`.** Здесь живут скачанные файлы, манифесты,
> спецификации и отчёты. Каталог `.local/` игнорируется git: сырые сканы и PDF
> охраняемых работ не должны попадать в репозиторий ни при каких условиях.

Необязательные, но полезные переменные окружения (вежливый пул API; это **не**
секреты):

```bash
export OPENALEX_MAILTO="you@example.org"    # OpenAlex polite pool
export CROSSREF_MAILTO="you@example.org"    # Crossref polite pool
```

Секрет `HF_TOKEN` понадобится только на шаге 9 (публикация). Не задавайте его
заранее и не передавайте в аргументах CLI.

---

## Шаг 1. Выбор домена и поискового запроса

Выберите **один** домен, в котором вы готовы отвечать за физическую
корректность. Сформулируйте 1–2 запроса на английском (язык arXiv/OpenAlex/
Crossref); для исторических периодов допустимы русский/немецкий/французский.

| Домен | Пример запроса |
|---|---|
| AERO | `wind tunnel airfoil drag coefficient` |
| STR | `fatigue test stress strain curve` |
| RADAR | `monostatic RCS measurement` |
| CTRL | `frequency response PID controller` |

Сверьтесь с реестром `configs/sources.yaml`: он сопоставляет период
(до 1900 / 1900–1950 / 1950–2000 / 2000+) с приоритетными платформами и
**ожидаемым** правовым статусом. Например, период 1950–2000 — это чаще всего
`metadata-only` (переиспользуемы метаданные и извлечённые факты, но не полный
текст).

**Результат шага:** выбран домен `DOMAIN` и запрос `QUERY` (сохраните их — они
нужны в каждой команде).

---

## Шаг 2. Поиск по официальным API

Поиск **только метаданные** — ничего не скачивает.

```bash
# Один сервис:
python physics-dataset-competition/scripts/collect.py search \
  --service openalex --domain AERO \
  --query "wind tunnel airfoil drag coefficient" --limit 10 \
  --out .local/physics-bronze/candidates.jsonl

# Несколько сервисов сразу (результаты объединяются):
python physics-dataset-competition/scripts/collect.py search \
  --service all --domain STR \
  --query "fatigue test stress strain" --limit 15 \
  --out .local/physics-bronze/candidates.jsonl
```

Поддерживаются `--service openalex|arxiv|crossref|all`; `--limit` — целое
**1..20** (иначе код 2). Команда печатает JSON-сводку со числом кандидатов.

Что происходит под капотом:

- **OpenAlex** — `api.openalex.org/works`; метаданные CC0. `OPENALEX_MAILTO`
  добавляется только если задан.
- **arXiv** — `export.arxiv.org/api/query`; пауза 3 с соблюдается **между
  страницами**, одиночный запрос не спит.
- **Crossref** — `api.crossref.org/works`; кандидаты почти всегда
  `metadata-only`, потому что Crossref не даёт права на полный текст — их
  `fetch` отклонит.

**Результат шага:** `candidates.jsonl` со списком кандидатов и их метаданными.

---

## Шаг 3. Право-гейт: разбор кандидатов

Просмотрите `candidates.jsonl` (строковый JSONL: по кандидату на строку).
Для каждого кандидата важны поля:

- `license` — лицензия источника;
- `copyright_status` — правовой статус;
- `is_oa` — есть ли открытый полный текст;
- `oa_url` — прямой https-адрес открытой версии;
- `provenance_service` — из какого API пришёл кандидат.

Загрузке подлежит кандидат, который **одновременно**:

1. классифицируется как `redistributable` — свободная лицензия, public domain
   или government work (см. `src/physics_ds/rights/classifier.py`);
2. указывает **прямой `https://` URL** на официальный хост из allow-list:
   `arxiv.org`, `export.arxiv.org`, `zenodo.org`, `api.openalex.org`,
   `ntrs.nasa.gov`, `osti.gov`, `archive.org`, `ia.us.archive.org`,
   `journals.plos.org`, `mdpi.com`.

Правила дерева §5.3, которые применяет классификатор:

| Ситуация | Статус | redistributable |
|---|---|---|
| CC0 / public domain | `cc0` / `public-domain` | **да** |
| CC-BY / CC-BY-SA | `cc-by` / `cc-by-sa` | **да** (с атрибуцией) |
| Government work (NASA / DTIC / OSTI) | `public-domain` | **да** |
| Письменное разрешение (`permission_ref`) | `permission-granted` | **да** |
| Охраняется, нужны факты | `metadata-only` | **нет** |
| Orphan work | `unknown` | **нет** |
| Неизвестно | `unknown` | **нет** (только ревью) |

> **Экспертное решение.** Классификатор — детерминированная подсказка, а не
> приговор. Если он ошибся (например, издатель распознан неверно), это
> исправляет эксперт, а не догадка агента. Сомневаетесь — оставляьте
> `metadata-only`/`unknown` и помечайте шаг как `blocked`.

**Результат шага:** список кандидатов, допущенных к загрузке, и список
отклонённых с причинами.

---

## Шаг 4. Lawful-загрузка источников

```bash
python physics-dataset-competition/scripts/collect.py fetch \
  --manifest .local/physics-bronze/candidates.jsonl \
  --out-dir .local/physics-bronze --max-items 5
```

- `--max-items N` — обработать не более N строк (0 = все);
- `fetch` сам отклоняет не-`redistributable`, не-`https` и хосты вне allow-list
  со статусом `skipped` — **это корректный исход, а не ошибка**;
- для успешных пишет файл в `.local/physics-bronze/`, считает `sha256`;
- создаёт `.local/physics-bronze/fetch-manifest.jsonl` со строкой на попытку:
  `service_id`, `status`, `reason`, `path`, `sha256`, `bytes`, а для успешных —
  `url`, `license`, `copyright_status`, `provenance_service`.

**Результат шага:** скачанные файлы и `fetch-manifest.jsonl` с их хэшами.

> **MUST NOT:** коммитить PDF/сканы, обходить paywall/robots.txt/ToS,
> подставлять credential-заголовки. Нарушение — инцидент, а не «ускорение».

---

## Шаг 5. Извлечение записей

Извлечение делается по **спецификации** — JSON-файлу, который описывает один
источник и извлечённые из него величины. Спецификацию готовит эксперт (агент
может помочь механически), по образцу
`physics-dataset-competition/tests/fixtures/spec.aero.json`:

```jsonc
{
  "domain": "AERO",
  "subdomain": "airfoil-polar",
  "period": "1930-1950",
  "source": {
    "title": "…",              // РЕАЛЬНЫЙ заголовок из API/файла
    "authors": ["…"],
    "publisher": "NASA",
    "year": 1935,
    "source_type": "report",
    "language": "en",
    "url": "https://ntrs.nasa.gov/…",
    "license": "public-domain"
  },
  "bronze": {
    "sha256": "<64 hex из fetch-manifest.jsonl>",   // ОБЯЗАТЕЛЕН
    "path": ".local/physics-bronze/<файл>",
    "service_id": "W123456789",
    "provenance_service": "openalex.org"
  },
  "conditions": {"Re": 3000000, "Ma": 0.2, "alpha": 4.0},
  "values": [
    {"name": "Cx", "value": 0.021, "unit": "-",
     "uncertainty": 0.002, "uncertainty_kind": "std"},
    {"name": "Cy", "value": 0.412, "unit": "-", "uncertainty": 0.01},
    {"name": "alpha", "value": 4.0, "unit": "deg"}
  ],
  "provenance": {
    "activity": "digitize", "agent_role_id": "R03",
    "retrieved_at": "2026-10-04T10:00:00Z",
    "method": "manual", "tool_version": "1.0"
  },
  "validation": {
    "status": "unchecked", "checked_by_role_id": "R03",
    "checked_at": "2026-10-04T10:00:00Z"
  }
}
```

Один файл может содержать несколько записей, если добавить массив `records`
(каждый элемент переопределяет общие поля).

Соберите записи:

```bash
python physics-dataset-competition/scripts/extract.py \
  --spec .local/physics-bronze/spec.aero.json \
  --out .local/physics-bronze/records.jsonl
```

Что делает `extract.py`:

- читает спек и собирает запись по канонической схеме
  `configs/schema/record.schema.json` (версия `1.0.0`);
- **права выставляет `rights.classifier`, а не спек** — подделать лицензию
  нельзя;
- `record_id` генерируется детерминированно: `DOMAIN-<≥8 hex>` от
  `sha256` bronze и индекса;
- **требует** `bronze.sha256` (64 hex) — метаданные не выдумываются;
- перед записью прогоняет структурную валидацию + доменные проверки
  (диапазоны, единицы, обязательные `conditions` из `configs/domains/*.yaml`);
- **при любой ошибке невалидные записи не пишутся** (код 1).

**Результат шага:** `records.jsonl` с валидными записями.

> **Роль эксперта.** OpenCode ассистирует извлечение, но эксперт обязан глазами
> сверить каждое число с первоисточником: единицы, знаки, условия опыта.
> Агент не имеет права «достроить» число, которого нет в источнике.

---

## Шаг 6. Выборочная проверка

```bash
python physics-dataset-competition/scripts/validate_sample.py \
  --records .local/physics-bronze/records.jsonl \
  --sample 0.5 --seed 42 --report .local/physics-bronze/sample-report.json
```

- `--sample` — доля выборки `0..1` (по умолчанию `1.0` — все записи);
- `--seed` — seed детерминированной выборки (по умолчанию `42`): одинаковые
  `--records`/`--sample`/`--seed` дают один и тот же отчёт;
- отчёт содержит: счётчики, дубликаты `record_id`, ошибки структуры/диапазонов/
  единиц и распределение `validation.status`;
- коды возврата: **0** чисто, **1** есть ошибки, **2** вход недоступен.

Критерий зачёта: **0 ошибок** на выборочной проверке.

**Результат шага:** отчёт и подтверждение, что проверка чистая.

---

## Шаг 7. Исправления (append-only)

Ошибку исправляют **новой записью**, а не правкой старой. Это требование
неизменяемости PROV (§4.4): история не перезаписывается.

1. Подготовьте JSON корректной записи (`corrected.json`) — полную запись,
   а не патч.
2. Добавьте её как исправление:

```bash
python physics-dataset-competition/scripts/correct.py \
  --record .local/physics-bronze/corrected.json \
  --parent-record-id AERO-XXXXXXXXXX \
  --records .local/physics-bronze/records.jsonl \
  --out .local/physics-bronze/records.jsonl
```

Что происходит:

- новый `record_id` генерируется детерминированно от содержимого;
- в `provenance.parent_record_id` указывается исправляемая запись;
- исходная запись **не изменяется и не перезаписывается**;
- новая запись валидируется (структура + домен) **до** добавления; при ошибке
  она не пишется (код 1).

После исправлений повторите [шаг 6](#шаг-6-выборочная-проверка), пока не
получите 0 ошибок.

**Результат шага:** дополненный `records.jsonl` и чистая проверка.

---

## Шаг 8. Финальные тесты

```bash
python -m pytest physics-dataset-competition/tests/ -q
```

Перед публикацией убедитесь, что записи валидны и на уровне основного
валидатора схемы:

```bash
python physics-dataset-competition/src/physics_ds/schema/validate.py \
  .local/physics-bronze/records.jsonl
```

**Результат шага:** все тесты и валидатор — зелёные.

---

## Шаг 9. Публикация Hub PR

Сначала **dry-run** — сети нет, печатается JSON-план (число записей, `sha256`,
ревизия, путь):

```bash
python physics-dataset-competition/src/physics_ds/publish/hf.py \
  --records .local/physics-bronze/records.jsonl --dry-run
```

Проверьте план: число записей совпадает, ревизия осмысленна
(`expert/<ваш-slug>`), путь — `submissions/<slug>/records.jsonl`.

Настройте секрет (fine-grained token, права `write` **только** на целевой
dataset-репозиторий):

```bash
python -m pip install -r physics-dataset-competition/docs/requirements-publish.txt
export HF_TOKEN="<ваш-токен>"     # НЕ в файл, НЕ в аргументы CLI
```

Создайте PR:

```bash
python physics-dataset-competition/src/physics_ds/publish/hf.py \
  --records .local/physics-bronze/records.jsonl \
  --repo-id chaotic-good-project/physics-experiment-records \
  --revision expert/<ваш-slug> \
  --title "AERO: 3 записи (1935, NASA)"
```

Правила publisher'а:

- публикуются **только** записи с `rights.redistributable = true`; иначе —
  код 1 **до** любого сетевого вызова;
- `HF_TOKEN` читается только из окружения и никогда не печатается/не логируется;
- создаётся **реальный Hub PR** (`create_pr=True`); merge эксперт **не**
  выполняет;
- формат репозитория и конвенции PR — `HF-DATASET.md`.

**Результат шага:** URL созданного PR. Запишите его в отчёт.

---

## Шаг 10. Отчёт о выполнении

Подготовьте короткий отчёт (в комментарии к PR или в файле задания):

| Поле | Значение |
|---|---|
| Домен | `AERO` / `STR` / `RADAR` / `CTRL` |
| Запрос(ы) | текстом |
| Источников | ≥ 2 |
| Записей (`accepted`) | ≥ 3 |
| Права | `rights.basis` по каждой записи |
| Выборочная проверка | отчёт, `exit 0` |
| Тесты | `pytest`, `validate.py` |
| Hub PR URL | ссылка |
| Ограничения / `blocked` | честно перечислить |

Честный `blocked` (например, «источник оказался paywalled») ценится выше
сфабрикованной записи.

---

## 13. Частые ошибки и как их не допустить

| Ошибка | Как правильно |
|---|---|
| Загрузка «в обход» paywall/robots | `skipped` — нормальный исход; не обходить |
| `bronze.sha256` «из головы» | брать из `fetch-manifest.jsonl`; иначе `extract.py` откажет |
| Публикация `metadata-only` | publisher вернёт код 1; такие источники не публикуются |
| Raw PDF/сканы в git | хранить только в `.local/physics-bronze/` (в `.gitignore`) |
| Токен в CLI/логах/файле | только `HF_TOKEN` из окружения; print/log запрещены |
| Правка старой записи вместо новой | исправление — новая запись с `parent_record_id` |
| Домысливание лицензии/DOI | нет данных — оставьте пусто и пометьте `blocked` |
| Придуманные числа | сверять каждое число с первоисточником глазами |

---

## Rubric (100 баллов)

| Критерий | Вес | Отлично (4) | Удовл. (2) | Не сдано (0–1) |
|---|---|---|---|---|
| Полнота | 25 | ≥3 записи, ≥2 источника | 2 записи / 1 источник | <2 записей |
| Права/лицензии | 25 | все `basis` объяснены, 0 вопросов | часть противоречива | нарушение |
| Физическая корректность | 20 | единицы/условия проверены экспертом | мелкие правки | грубые ошибки |
| Provenance | 15 | sha256 source↔bronze, цепочка полная | пробелы | нет |
| Выборочная проверка | 10 | 0 ошибок | 1–2 ошибки | не проводилась |
| Публикация | 5 | Hub PR URL записан | dry-run только | нет |

Порог зачёта — **≥ 60 баллов** и отсутствие нарушений copyright/PII (иначе 0).

---

## Быстрая шпаргалка (все команды подряд)

```bash
mkdir -p .local/physics-bronze

python physics-dataset-competition/scripts/collect.py search \
  --service all --domain AERO --query "wind tunnel airfoil drag coefficient" \
  --limit 10 --out .local/physics-bronze/candidates.jsonl

python physics-dataset-competition/scripts/collect.py fetch \
  --manifest .local/physics-bronze/candidates.jsonl \
  --out-dir .local/physics-bronze --max-items 5

python physics-dataset-competition/scripts/extract.py \
  --spec .local/physics-bronze/spec.aero.json \
  --out .local/physics-bronze/records.jsonl

python physics-dataset-competition/scripts/validate_sample.py \
  --records .local/physics-bronze/records.jsonl \
  --sample 0.5 --seed 42 --report .local/physics-bronze/sample-report.json

# при ошибках: correct.py → повтор validate_sample.py

python -m pytest physics-dataset-competition/tests/ -q

python physics-dataset-competition/src/physics_ds/publish/hf.py \
  --records .local/physics-bronze/records.jsonl --dry-run
# затем с HF_TOKEN:
python physics-dataset-competition/src/physics_ds/publish/hf.py \
  --records .local/physics-bronze/records.jsonl \
  --revision expert/<slug> --title "<ДОМЕН>: N записей"
```

## Связанные документы

- `EXPERT-ASSIGNMENT.md` — краткая версия задания;
- `OPENCODE-EXPERT-PROMPT.md` — готовый промпт для OpenCode-агента;
- `HF-DATASET.md` — формат Hub-репозитория, dataset card, откат;
- `RUNBOOK.md` — инциденты и восстановление;
- `configs/schema/record.schema.json` — каноническая схема записи;
- `configs/sources.yaml` — реестр источников по периодам;
- `configs/domains/*.yaml` — диапазоны/единицы/`conditions` по доменам.
