# Первое задание: вклад в датасет курса (базовое)

Это **первое задание курса** и одновременно ваш первый вклад в открытый проект.
Курс «История России: история и философия науки и технологий» — это и
репозиторий-проект: полезная работа остаётся в нём для следующей группы и
попадает в открытый датасет на HuggingFace. Роль выбирается участником; задание
одно на занятие.

Курс-специфичная цель: собрать данные с **количественными результатами и
измерениями** из исторических источников (число + единица), в основном XX век.

## Роли

| Роль | Что делает | Что остаётся в проекте |
|---|---|---|
| **Эксперт** (работа с данными) | извлекает измерения и результаты по схеме проекта | записи датасета, проверенные цитаты |
| **Разработчик** (инфраструктура) | код, тесты, CI, воспроизводимый запуск | принятый PR, зелёный CI |

Роли можно совмещать.

## Роль «Эксперт» — базовое задание (3 записи)

1. Возьмите материал занятия: `make session n=03`, `make assignment n=03`
   (или любой темы по вашему треку). Источники — см. `istochniki.md`.
2. Соберите **3 записи** профиля `experiment` по схеме
   `dataset-schema/universal-record.schema.json`.

**Проще всего — через агента (opencode).** Запустите opencode и введите
`/expert-histsci` — агент «Эксперт-история» сам проведёт вас по 2–3 вопросам,
возьмёт **дословную** цитату из источника, заполнит схему и проверит результат
(в этом случае работает `dataset-schema/expert_record.py`).

**Вручную** — например:
```bash
python3 dataset-schema/expert_record.py find --file "merged/lesson1__Tyndall_Fragments_of_Science.txt" --phrase "186,000"
python3 dataset-schema/expert_record.py add --kind experiment --nick <ник> \
  --out records-<ник>.jsonl --file "merged/lesson1__Tyndall_Fragments_of_Science.txt" \
  --phrase "186,000" --subject "скорость распространения света" --method "сравнение наблюдений" \
  --variable "скорость света" --value 186000 --unit "miles per second" \
  --outcome "Скорость света ≈ 186 000 миль/с." --doc-type pd_book --license PD
python3 dataset-schema/validate.py records-<ник>.jsonl
```

3. Положите результат в **`submissions/records-<ник>.jsonl`** (имя — ваш ник
   латиницей) и отправьте в проект (PR или коммит в `main`). После попадания в
   `main` данные автоматически попадут в датасет на HuggingFace
   (workflow `submit-dataset`).

**Критерий приёмки:** `validate.py` → `errors=0`; у каждой записи есть источник и
координата; `evidence_quote` — дословная подстрока источника; `measurements`
непустой. Записи помечаются `review.status="proposed"`.

**Оценка:** 1 задание — 8/10, 2 — 9/10, 3 и более — 10/10.

## Роль «Разработчик» — базовое задание

1. Проверьте окружение: `make help`, `make status`, `make session n=03`,
   `make order-check`.
2. Прогоните проверку датасета:
   ```bash
   python3 assignments/00-first-contribution/dataset-schema/validate.py \
     assignments/00-first-contribution/dataset-schema/examples/experiment_records.jsonl
   python3 assignments/00-first-contribution/dataset-schema/validate.py --selftest
   ```
   Ожидаемо: `errors=0`, `--selftest → PASS`.
3. **Полный балл:** улучшить шаг CI (негативный тест из `--selftest` обязательным,
   проверка дублей по `record_id`, проверка «единицы объявлены»). Через PR.

## Лицензирование (важно)
В открытый датасет попадают записи, у которых `source.license` — публикуемая:
`PD`, `CC0`, `CC-BY-4.0`, `CC-BY-SA-4.0`, `official-document`. Записи с
`cite-only`/`unknown` **в датасет не публикуются** (остаются в репозитории как
учебный материал). Проверяет `dataset-schema/publish.py`.

## Раскрытие ИИ
ИИ-содействие допустимо и раскрывается: укажите `provenance.tool`.

## Состав папки
```
README.md                         — это задание
istochniki.md                     — источники по курсу
dataset-schema/universal-record.schema.json   — схема
dataset-schema/validate.py                    — проверка (--selftest)
dataset-schema/publish.py                     — сборка датасета + публикация на HF
dataset-schema/expert_record.py               — помощник (дословная цитата + схема)
dataset-schema/examples/experiment_records.jsonl — примеры записей
submissions/                      — сюда кладут результат (records-<ник>.jsonl)
```
