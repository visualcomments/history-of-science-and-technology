# Первое задание эксперта: сбор и публикация экспериментальных записей

Это задание для **экспертной роли** (EXP/DOMAIN) в модуле
`physics-dataset-competition`. Цель — провести полный цикл: lawful-поиск в
официальных API → локальная загрузка разрешённых источников → извлечение
экспериментальных записей по канонической схеме → выборочная проверка и
исправления → pull request в публичный датасет на Hugging Face Hub.

**Ключевой принцип:** источник данных не выдумывается, права не угадываются,
raw-сканы не коммитятся. Всё, что попадает в публичный датасет, должно быть
воспроизводимо из файлов этого репозитория.

---

## 0. Что считается сделанной работой (DoD)

1. **≥ 3 принятых записи** (`validation.status = accepted`) из **≥ 2 разных
   источников** по выбранному домену.
2. У каждой записи **воспроизводимые права**: `rights.basis` объясняет
   основание, `rights.redistributable=true` подтверждено политикой §5.3.
3. Выборочная проверка даёт **0 ошибок** (`validate_sample.py` → exit 0).
4. Открыт **Hub PR URL** и записан в отчёт; сам PR не мержится экспертом.
5. Скачанные первоисточники лежат **только** в `.local/physics-bronze/`
   (в git их нет).

---

## 1. Выбор домена и запроса

Домены: `AERO`, `STR`, `RADAR`, `CTRL`.

Сформулируйте 1–2 запроса на английском (для arXiv/OpenAlex/Crossref) и, при
желании, на русском/немецком/французском для исторических периодов.

Примеры:
- AERO: `"wind tunnel airfoil drag coefficient"`;
- STR: `"fatigue test stress strain curve"`;
- RADAR: `"monostatic RCS measurement"`;
- CTRL: `"frequency response PID controller"`.

Сверяйтесь с `configs/sources.yaml` (реестр источников по периодам, DESIGN §5.1).

## 2. Поиск по официальным API (metadata-only)

```bash
# Один сервис:
python physics-dataset-competition/scripts/collect.py search \
  --service openalex --domain AERO \
  --query "wind tunnel airfoil drag coefficient" --limit 10 \
  --out .local/physics-bronze/candidates.jsonl

# Все сервисы разом:
python physics-dataset-competition/scripts/collect.py search \
  --service all --domain STR --query "fatigue test stress strain" --limit 15 \
  --out .local/physics-bronze/candidates.jsonl
```

Что важно помнить:

- `search` — **только метаданные**, ничего не скачивает;
- можно выставить `OPENALEX_MAILTO` / `CROSSREF_MAILTO` (вежливый пул API);
  это не секреты, но и не обязательны;
- arXiv-клиент соблюдает паузу 3 с **между** страницами, один запрос не спит;
- **Crossref не даёт права на полный текст** — его кандидаты почти всегда
  `metadata-only` и не скачиваются.

## 3. Право-гейт и lawful-загрузка

Просмотрите `candidates.jsonl`. Для загрузки кандидат обязан быть
`redistributable` (свободная лицензия / public domain / government work) и
указывать **прямой https-URL** с официального хоста (arXiv, Zenodo, NASA NTRS,
OSTI, Internet Archive, PLOS, MDPI).

```bash
python physics-dataset-competition/scripts/collect.py fetch \
  --manifest .local/physics-bronze/candidates.jsonl \
  --out-dir .local/physics-bronze --max-items 5
```

`fetch`:

- отклоняет `metadata-only`/`unknown` и не-https, и хосты вне allow-list;
- пишет байты в `.local/physics-bronze/` (в `.gitignore`);
- считает sha256 и ведёт `fetch-manifest.jsonl` с `sha256`, `url`, правами.

> **MUST NOT:** коммитить PDF/сканы, обходить paywall/robots.txt/ToS,
> подставлять credentials. Если права неясны — команда вернёт `skipped`;
> это корректный исход, а не ошибка.

## 4. Извлечение записей (агент помогает, эксперт проверяет)

1. Откройте локальный файл из `.local/physics-bronze/` и извлеките
   числовые результаты (таблицы/графики) — вручную или через WebPlotDigitizer.
2. Подготовьте **спецификацию извлечения** (JSON) по образцу
   `physics-dataset-competition/tests/fixtures/spec.aero.json`:

   - `source` — реальные метаданные источника (title/year/license/url/…);
   - `bronze.sha256` — sha256 скачанного файла из `fetch-manifest.jsonl`
     (**обязателен**; метаданные не выдумываются);
   - `conditions` — Re/Ma/alpha/T/…;
   - `values[]` — name/value/unit (+ `uncertainty`, `uncertainty_kind`);
   - `provenance` — activity/agent_role_id/retrieved_at/method.

3. Соберите записи:

```bash
python physics-dataset-competition/scripts/extract.py \
  --spec .local/physics-bronze/spec.aero.json \
  --out .local/physics-bronze/records.jsonl
```

Права выставляет `rights.classifier.classify` (не спецификация); `record_id`
генерируется детерминированно из `DOMAIN + sha256 bronze + индекс`. Запись
проверяется структурно и по домену; при ошибках JSONL не пишется.

**OpenCode ассистирует** извлечение, но эксперт обязан глазами сверить каждое
число с первоисточником: правильность единиц, знаков, условий эксперимента.

## 5. Выборочная проверка (детерминированная)

```bash
python physics-dataset-competition/scripts/validate_sample.py \
  --records .local/physics-bronze/records.jsonl \
  --sample 0.5 --seed 42 --report .local/physics-bronze/sample-report.json
```

- `--sample` — доля выборки 0..1; при одинаковом seed выборка воспроизводима;
- отчёт: счётчики, дубликаты `record_id`, ошибки структуры/диапазонов/единиц,
  распределение `validation.status`;
- коды возврата: `0` чисто, `1` есть ошибки, `2` вход недоступен.

Критерий: **0 ошибок** на выборочной проверке.

## 6. Исправления (append-only)

Ошибку исправляют **новой записью**, а не правкой старой:

```bash
python physics-dataset-competition/scripts/correct.py \
  --record corrected.json --parent-record-id AERO-XXXXXXXXXX \
  --records .local/physics-bronze/records.jsonl \
  --out .local/physics-bronze/records.jsonl
```

Новая запись получает новый `record_id` и
`provenance.parent_record_id`; исходная запись остаётся неизменной.

## 7. Тесты перед публикацией

```bash
python -m pytest physics-dataset-competition/tests/ -q
```

## 8. Публикация в Hugging Face Hub (PR)

Сначала dry-run (сети нет, печатает JSON-план: число записей, sha256, ревизия,
пути):

```bash
python physics-dataset-competition/src/physics_ds/publish/hf.py \
  --records .local/physics-bronze/records.jsonl --dry-run
```

Затем реальный PR (секрет — **только** из окружения `HF_TOKEN`, в файлы/logs
не пишется):

```bash
# требует: pip install -r physics-dataset-competition/docs/requirements-publish.txt
python physics-dataset-competition/src/physics_ds/publish/hf.py \
  --records .local/physics-bronze/records.jsonl \
  --repo-id chaotic-good-project/physics-experiment-records \
  --revision expert/<ваш-slug> \
  --title "AERO: 3 записи (1935, NASA)"
```

Публикуются только записи с `rights.redistributable=true`; иначе publisher
завершится с кодом 1 **до** любого сетевого вызова. Формат репозитория и
конвенции PR — в `docs/HF-DATASET.md`.

Запишите URL созданного PR в свой отчёт (достаточно для зачёта).

---

## Rubric (100 баллов)

| Критерий | Вес | Отлично (4) | Удовл. (2) | Не сдано (0–1) |
|---|---|---|---|---|
| Полнота | 25 | ≥3 записи, ≥2 источника | 2 записи/1 источник | <2 записей |
| Права/лицензии | 25 | все basis объяснены, 0 вопросов | часть противоречива | нарушение |
| Физическая корректность | 20 | единицы/условия проверены экспертом | мелкие правки | грубые ошибки |
| Provenance | 15 | sha256 source↔bronze, цепочка полная | пробелы | нет |
| Выборочная проверка | 10 | 0 ошибок | 1–2 ошибки | не проводилась |
| Публикация | 5 | Hub PR URL записан | dry-run только | нет |

Порог зачёта — ≥ 60 баллов и отсутствие нарушений copyright/PII (иначе 0).

---

## Частые ошибки

- Загрузка «в обход» — категорически запрещена; `skipped` — норма.
- `bronze.sha256` не из манифеста, а «из головы» → `extract.py` откажет.
- Попытка опубликовать `metadata-only` → publisher откажет (код 1).
- Raw PDF/сканы в git → нарушение; только `.local/physics-bronze/`.
- Токен в командной строке или в логах → инцидент `pii-leak`.
