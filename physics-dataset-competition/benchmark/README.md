# benchmark — воспроизводимый harness

Считает метрики регрессии на детерминированном grouped+temporal разбиении
`60/20/20` с embargo (`configs/splits.yaml`, `configs/metrics.yaml`).

## Запуск

```bash
python benchmark/run.py                 # встроенная мини-фикстура
python benchmark/run.py --json          # полный JSON-отчёт
python benchmark/run.py --records data/gold/records.jsonl
python benchmark/run.py --help
```

Скрипт самодостаточен: добавляет `src/` в `sys.path`; сеть не используется,
внешних зависимостей нет.

## Вход

JSONL, по одной записи в строке. Для расчёта метрик нужны `domain`, `target`,
`prediction`; для разбиения — `source.id`/`source.year` или `period`.

## Выход

JSON: `dataset_version`, `splits_version`, `seed`, `sizes` (train/val/test) и
`metrics` по доменам (`rmse`, `mae`, `n`) плюс агрегат `normalized_rmse`.

## Детерминизм

Разбиение сортирует группы по `(min(year), group)` и режет по числу групп, а не
записей, поэтому две группы одного источника не попадают в разные сплиты.
При одинаковом входе и конфиге результат идентичен между запусками.
