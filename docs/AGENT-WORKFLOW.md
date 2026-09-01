# Agent workflow: курс + co-learner (botai)

Этот документ описывает, как ИИ-агент (harness типа botai, см.
https://github.com/visualcomments/botai) эффективно работает с данным
курсом. Обязательные точки входа — `AGENTS.md` (короткая версия) и
`tools/status.py` (состояние окружения).

## Цикл работы агента

### 1. Онбординг (starting-course)
- `python tools/status.py` — проверить репозиторий и наличие корпуса;
- прочитать `syllabus.json` + `agents/courses/falt-history-science/track.md`
  (карта модулей и целей по шаблону botai);
- определить точку старта обучающегося (занятие/модуль, базовый уровень).

### 2. Занятие (planning-study-sessions, explaining-concepts)
- `make session n=<NN>` — текст занятия, цитаты, источники;
- `make assignment n=<NN>` — вопросы и задания;
- объяснения — по материалам занятия; при необходимости —
  `make search QUERY="..."` для дополнительных фрагментов корпуса.

### 3. Проверка и обратная связь (assessing-understanding, giving-feedback)
- проверка эссе/ответа: сверить цитаты с корпусом
  (`make verify` после любых правок курса; в ответах — только координаты
  «файл · фрагмент #N»);
- оценка — по критериям раздела «Assessment» в `syllabus.json`.

### 4. Прогресс (maintaining-course-progress, reporting-learning-progress)
- файл `agents/progress/progress-example.md` — шаблон;
- реальный файл прогресса держится в пространстве агента
  (`progress/falt-history-science.md`), обновляется после каждого занятия;
- схема записи: `progress-entry.json` (поля: date, student, course, mode,
  module, objectives, demonstrated, difficult, mastery, delivery_preference,
  consent, open_questions…).

### 5. Supplement (providing-supplementary-material, vetting)
- если курс заявлен как «не покрывает тему» (см. Gaps в track.md) —
  дополнять только проверяемыми источниками: корпус (если расширен —
  пересобрать индекс), либо явно помеченные «вне корпуса» материалы;
- новые внешние материалы прогонять через навык `vetting-educational-material`.

## Контракт цитирования повсюду
Прямые цитаты — только из корпуса, дословно, с координатами; авторский
синтез — с пометкой «вне корпуса». Нарушения контракта проверяются
`tools/verify_quotes.py` (не должно быть ошибок после любых правок).

## Инфраструктура в репозитории
| Что | Чем вызывается |
|---|---|
| Поиск по корпусу | `make search QUERY="..."` / `tools/rag_search.py` |
| Материалы занятия | `make session n=NN` / `tools/session_material.py NN` |
| Задания занятия | `make assignment n=NN` / `tools/assignment_brief.py NN` |
| Проверка цитат | `make verify` / `tools/verify_quotes.py` |
| RAG API | `make serve` / `tools/rag_api.py` (+ `tools/serve_api.ps1`, `tools/rag-openapi.json`) |
| Статус окружения | `make status` / `tools/status.py` |
| Удалённый поиск (нет локального корпуса) | `make remote-search QUERY="..."` / `tools/rag_remote.py` (docs/REMOTE-RAG.md) |
| Навык работы с корпусом | `.agents/skills/using-course-corpus/SKILL.md` (и зеркала .claude/.cursor) |