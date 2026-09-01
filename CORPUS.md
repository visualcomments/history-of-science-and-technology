# CORPUS — как устроен локальный корпус источников

Курс опирается на **верифицированный корпус** — локальную библиотеку
текстов для RAG. В сам репозиторий GitHub корпус не включается (большие
тексты); здесь — карта и процедуры.

## Раскладка рабочего пространства

```
<workspace>/                          ← корневой каталог (например, C:\…\falt_2026)
├── course/                           ← этот репозиторий курса (GitHub)
├── txt/                              ← текстовые версии источников (UTF-8)
├── index/                            ← RAG-индекс (annoy, embeddings, chunks.jsonl, config.json)
├── sources/                          ← исходные файлы (pdf/epub/djvu) из библиотеки
├── scripts/                          ← рабочие скрипты (поиск, сборка, верификация)
├── catalog/                          ← каталог литературы, цитаты, логи
└── .venv/                            ← Python-окружение (.venv/Scripts/python.exe)
```

Репозиторий курса `course/` определяет корень рабочего пространства как
`../..` от `course/tools/`, либо читает `FALT_CORPUS_ROOT`.

## Как агент получает корпус

1. `python tools/status.py` — покажет, где ожидается корпус и что доступно.
2. Если корпуса нет — можно собрать заново:
   - источники: каталог `catalog/` (927 записей), план загрузки
     `catalog/download_plan.json`; загрузчики — `scripts/download_books.py`,
     `libgen_client.py`, `libgen_pull.py`;
   - тексты: `scripts/convert_txt.py` (+ `djvutxt` для DjVu);
   - индекс: `scripts/rag_build.py` (CPU), `scripts/rag_build_cluster.py`
     (CPU-кластер: локальный пул + ubuntu-server через SSH, см. README);
3. Альтернатива — `FALT_CORPUS_ROOT=<путь>` указывает на готовое рабочее
   пространство с `txt/`, `index/`, `scripts/`.

## Что делает инструменты

| Инструмент | Что даёт агенту |
|---|---|
| `tools/rag_search.py` | семантический поиск: фрагменты `file`+`chunk_id`+текст |
| `tools/rag_api.py` | HTTP API (`/search`, `/health`, `/docs`) на порту 8765 |
| `tools/verify_quotes.py` | проверка всех цитат курса по корпусу (отчёт `verification/REPORT.md`) |
| `tools/session_material.py` | материал занятия (NN): цитаты и источники |
| `tools/assignment_brief.py` | вопросы и задания занятия (NN) |
| `tools/rag_build_cluster.py` | распределённая CPU-сборка индекса (кластер) |
| `tools/status.py` | состояние курса и корпуса |

## Источники корпуса

Корпус состоит из источников публичного достояния и документов
правительства США/NASA (public domain) и НЕ содержит цитат из современных
коммерческих изданий (см. `citations.md`).