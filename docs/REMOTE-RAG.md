# Удалённый RAG: ubuntu-server + ngrok + n8n

RAG-функциональность курса доступна агенту `botai` **напрямую через
публичный ngrok-туннель** на сервере `ubuntu-server` (`SERVER_GUIDE.md`):
индекс и эмбеддинги курса размещены на сервере, RAG-API отдаёт результаты
по HTTP. n8n (уже работает на сервере, порт 5678) используется для
демонстрации данных.

## Архитектура

```
botai / любой клиент
   │
   ▼  https://smoky-steadier-quintet.ngrok-free.dev/rag/search  (публичный ngrok)
ubuntu-server (10.0.0.2)
   ├─ ngrok-g4f.service  → :1359  (единый туннель; домен был занят llm-router,
   │   mix_proxy.py распределяет: /rag*, /search → RAG; остальное → :1340)
   ├─ rag-proxy.service  (mix_proxy.py, :1359)
   ├─ rag-api-course.service (rag_api_server.py, :8010, fastembed CPU, index/)
   ├─ n8n (docker n8n-verkhoyansk, :5678, LAN по ufw+iptables-DOCKER-USER)
   │    webhook POST /webhook/course-rag-demo → HTTP node → RAG (:1359) → ответ
   └─ ~/ragd/  (venv, app/, index/ — копия index/ курса)
```

## API

- `GET /rag/health` — статус: `{"status":"ok","chunks":25755}`
- `GET /rag/search?q=...&k=5&topic=...&threshold=...`
- `POST /rag/search` — JSON `{"q":"...","k":5}` (удобно для n8n/агентов)
- `/search`, `/docs` — псевдонимы RAG; всё остальное — прежний шлюз `:1340`
  (`/v1/models` и др. работают как раньше)

Публичный URL сохраняется в `server/ngrok-url.txt`.

## Как пользоваться

```bash
# агент (откуда угодно):
python tools/rag_remote.py "Ньютон законы движения" -k 5
python tools/rag_remote.py "Менделеев" --json

# напрямую:
curl "https://smoky-steadier-quintet.ngrok-free.dev/rag/search?q=%D0%9D%D1%8C%D1%8E%D1%82%D0%BE%D0%BD&k=3"
curl -X POST .../rag/search -H 'Content-Type: application/json' -d '{"q":"Герц"}'

# демонстрация через n8n (webhook):
curl -X POST http://10.0.0.2:5678/webhook/course-rag-demo \
     -H 'Content-Type: application/json' -d '{"q":"Менделеев"}'
#   → n8n выполняет воркфлоу «Course RAG demo» и возвращает RAG-ответ
```

## Развёртывание / обслуживание

- `server/rag_api_server.py` — RAG API (systemd `rag-api-course`, порт 8010);
- `server/mix_proxy.py` — единый прокси (systemd `rag-proxy`, порт 1359);
- `server/deploy.sh` — копирование приложения и создание units;
- `server/n8n_activate.js` — активация воркфлоу + регистрация webhook-пути
  напрямую в БД n8n (`docker exec -u node -w /home/node n8n... node .n8n/activate.js <id> <path>`;
  после импорта воркфлоу требуется `docker restart n8n-verkhoyansk`);
- `server/n8n-course-rag-demo.json` — импортируемый воркфлоу (id 1002);
- порты: ufw открывает 5678 для LAN; для docker-порта добавлено
  `iptables -I DOCKER-USER 1 -p tcp --dport 5678 -j ACCEPT`;
- после обновления индекса: `scp index/* zzz@10.0.0.2:~/ragd/index/` +
  `sudo systemctl restart rag-api-course`.

## Тестирование (проведено 2026-09-01)

| Шаг | Результат |
|---|---|
| RAG API на сервере (`/health`) | 200, 25755 чанков |
| `GET /rag/search` (сервер/публично) | 200, релевантные фрагменты |
| `POST /rag/search` (gateway и публичный ngrok) | 200, JSON |
| Активный туннель ngrok → :1359 (repoint без нового домена) | активен, 200 |
| Прежний шлюз через тот же URL (`/v1/models`) | 200 (не сломан) |
| n8n webhook `POST /webhook/course-rag-demo` (локально и с Windows по LAN) | 200 + RAG JSON |
| Кудрявцев (©) удалён из корпуса/индекса | chunks 27809 → 25755 |

## Ограничения

- ngrok free: один публичный туннель; поэтому используется единый домен с
  path-распределением. Периодические 502 ngrok-эджа сглаживаются ретраями
  воркфлоу и curl-повторами инструмента.
- Индекс в репозиторий не входит; на сервере лежит рабочая копия (`~/ragd/index`).