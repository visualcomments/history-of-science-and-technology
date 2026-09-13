# Индекс и эмбеддинги на Google Диске (рекомендуемая схема доступа)

Индекс корпуса (Annoy + эмбеддинги + чанки) распространяется как **файлы
на Google Диске**: репозиторий самодостаточен.
Агент (или пользователь) скачивает архив по ссылке, инструмент проверяет
контрольные суммы и разворачивает индекс в локальный корпус
(`COURSE_CORPUS_ROOT/index/`), после чего работают `make search`,
`make verify` и локальный RAG-API.

## Что загружается на Диск

Один архив (рекомендуется) с именем `course-index-2026-09-13.zip`:

| Файл в архиве | Размер | SHA-256 |
|---|---|---|
| `annoy.index` | 84 126 060 Б | `CB5614CF…2B288` |
| `chunks.jsonl` | 78 233 067 Б | `E83D32CE…8CA0B` |
| `embeddings.npy` | 73 391 744 Б | `4191FC79…245CC` |
| `config.json` | 8 389 Б | `60E1A908…603434` |

Архив: **165 389 408 байт (157,7 МБ)**,
`SHA-256 = 60FCD293E475DB8F2D8B3094B6D80C88AE87AD44D167F695D5CF1250BCD49770`.
(Полные контрольные суммы — в `index-manifest.json`.)

Индекс покрывает **171 файл корпуса, 47 781 чанк** (модель
`paraphrase-multilingual-MiniLM-L12-v2`, 384 измерения, чанк 1400/140).
Состав корпуса: 96 статей Wikipedia (CC BY-SA 4.0), 28 PD-первоисточников
(`pd_*.txt`), 47 файлов прежнего корпуса.

**Где лежит на Диске:** папка `courses-indexes`, файл
`course-index-2026-09-13.zip`. Прямая ссылка уже вписана в
`index-manifest.json` (`archive.url`), поэтому достаточно `make corpus-fetch`
без параметров. Просмотр файла:
`https://drive.google.com/file/d/1vldomUmeMGNYTTwaS6EEvV0HTerUR6hh/view`.

**Особенность Google Диска для больших файлов.** Анонимный запрос к
`uc?export=download&id=…` на файл такого размера возвращает не сам файл, а
HTML-страницу подтверждения («Google Drive can't scan this file for
viruses» → «Download anyway»). Поэтому загрузчик обязан проследовать форме
(`action` + скрытые поля `confirm`/`uuid`) — это реализовано в
`tools/corpus_fetch.py`. При ручной загрузке через `curl` файл не получится:
нужна браузерная ссылка выше либо `gdown`. Ссылка проверена анонимно: после
подтверждения отдаётся `application/octet-stream` и настоящий ZIP
(`PK`-заголовок).

**Сквозная проверка (2026-09-13).** `tools/corpus_fetch.py --index-only`
по ссылке из манифеста: SHA-256 подтверждена, индекс установлен,
`chunks: 47781, files: 171`.

## Как выложить и подключить

1. **Загрузите архив** (или 4 файла по отдельности) на Google Диск;
   в настройках общего доступа выберите **«Все, у кого есть ссылка» →
   «Читатель»**.
2. **Скопируйте share-ссылку** (вид `https://drive.google.com/file/d/FILE_ID/view?usp=sharing`)
   или прямой download-link (`https://drive.google.com/uc?export=download&id=FILE_ID`).
3. **Подключите одним из способов:**
   - разово: `make index-fetch URL="<ссылка>"` (или `COURSE_INDEX_URL=<ссылка>`);
   - постоянно: скопируйте `index-manifest.example.json` в `index-manifest.json`
     и впишите ссылку в поле `archive.url` — тогда работает просто `make index-fetch`.
4. Инструмент проверит SHA-256, распакует и **атомарно** заменит
   `COURSE_CORPUS_ROOT/index/` (старая папка → `index_old/`).

После развёртывания: `make search QUERY="..."`, `make verify`,
`make serve` — как с любым локальным корпусом.

## Для владельца репозитория (обновление манифеста)

При новой версии индекса:

```bash
# 1. Собрать архив из index/ (4 файла в корне архива)
#    python -c "import zipfile;z=zipfile.ZipFile('course-index-YYYY-MM-DD.zip','w');..."
# 2. Пересчитать SHA-256 (Get-FileHash / sha256sum) и записать в манифест
# 3. Залить на Диск и обновить archive.url
rclone copy course-index-YYYY-MM-DD.zip gdrive:courses-indexes/
rclone link gdrive:courses-indexes/course-index-YYYY-MM-DD.zip   # публичная ссылка
# 4. Коммит манифеста
```

**Важно про большие файлы.** Google отдаёт анонимному запросу HTML-страницу
подтверждения, поэтому после загрузки обязательно проверьте скачивание
именно тем загрузчиком, которым будут пользоваться студенты:
`python tools/corpus_fetch.py --index-only` — он проходит форму `confirm` и
сверяет SHA-256.

**Кто может загружать.** Сервисный аккаунт Google **не может** создавать
файлы: у него нет собственной квоты (`storageQuota.limit = 0`, ошибка
`Service Accounts do not have storage quota`), а API-ключ не может писать
(`401: API keys are not supported by this API`). Работают только:
OAuth-авторизация от личного аккаунта (например, `rclone config create
gdrive drive scope drive`) или ручная загрузка в браузере. Выдача сервисному
аккаунту прав «Редактор» на папку проблему **не решает** — квота считается по
создателю файла. Общий диск (Shared Drive) решает, но требует Google
Workspace.

## Обновление индекса

1. Скачать новый архив: `make corpus-fetch` (ссылка берётся из
   `index-manifest.json`); сумма сверяется с манифестом, при несовпадении
   распаковка не производится.
2. Инструмент распакует архив и **атомарно** заменит
   `COURSE_CORPUS_ROOT/index/` (старая папка → `index_old/`).
3. Если корпус-тексты (`txt/`) тоже обновлены — пересобрать локальный
   корпус по `CORPUS.md` и перепроверить цитаты (`make verify`).
