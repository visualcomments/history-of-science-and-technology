---
license: other
language:
  - en
  - ru
tags:
  - physics
  - scientific-data
  - provenance
  - benchmark
pretty_name: Physics Experiment Records
size_categories:
  - n<1K
---

# Physics Experiment Records

Стартовый публичный набор для учебного модуля
[`physics-dataset-competition`](https://github.com/visualcomments/history-of-science-and-technology/tree/main/physics-dataset-competition).

## Статус

В стартовой версии нет экспериментальных записей. Эксперты добавляют их
только pull request'ами в Hugging Face Hub после проверки схемы, единиц,
диапазонов, происхождения и прав на публикацию.

## Схема и формат

- Каноническая схема: [`record.schema.json`](record.schema.json), версия `1.0.0`.
- Формат записей: UTF-8 JSONL, одна запись на строку.
- Домены: `AERO`, `STR`, `RADAR`, `CTRL`.
- Каждая запись содержит источник, условия эксперимента, величины с единицами
  и неопределённостью, цепочку provenance и результат проверки.

## Порядок вклада

Полная инструкция для эксперта находится в репозитории:

- [первое задание](https://github.com/visualcomments/history-of-science-and-technology/blob/main/physics-dataset-competition/docs/EXPERT-ASSIGNMENT.md);
- [инструкция для OpenCode](https://github.com/visualcomments/history-of-science-and-technology/blob/main/physics-dataset-competition/docs/OPENCODE-EXPERT-PROMPT.md);
- [правила публикации в Hub](https://github.com/visualcomments/history-of-science-and-technology/blob/main/physics-dataset-competition/docs/HF-DATASET.md).

Перед PR выполняются локально:

```bash
python physics-dataset-competition/src/physics_ds/schema/validate.py records.jsonl
python physics-dataset-competition/scripts/validate_sample.py \
  --records records.jsonl --sample 0.2 --seed 42 --report sample-report.json
```

## Лицензия и права

В набор допускаются только записи с `rights.redistributable: true` и
воспроизводимым основанием прав. Сканированные источники и PDF не хранятся в
наборе: локально сохраняются только для обработки, а публикация содержит
структурированные факты, метаданные, ссылки, хэши и provenance. Записи с
неясными правами, paywall-источники и персональные данные запрещены.

## Цитирование

Пока набор не содержит версий с данными, используйте ссылку на репозиторий
проекта и фиксируйте revision Hub в своей работе. После первой публикации
будет добавлен `CITATION.cff`.
