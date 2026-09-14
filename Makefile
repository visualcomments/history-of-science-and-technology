# Makefile для агента: короткие цели для работы с курсом и корпусом

PY ?= python3
VENV_PY ?= $(PY)

.PHONY: help search index-fetch session assignment verify serve status quotes corpus-fetch corpus-status order order-check

help:
	@echo "Цели:"
	@echo "  make search QUERY=\"...\"     семантический поиск по корпусу (k=5)"
	@echo "  make corpus-fetch            скачать корпус (индекс + тексты), с проверкой хэшей"
	@echo "  make corpus-status           показать, установлен ли корпус"
	@echo "  make index-fetch URL=\"...\"  совместимость: только индекс"
	@echo "  make session n=18            материалы занятия 18 (текст+цитаты+источники)"
	@echo "  make assignment n=18         вопросы и задания занятия 18"
	@echo "  make verify                  проверка всех цитат курса по корпусу"
	@echo "  make serve port=8765         запуск RAG-API (Ctrl+C — стоп)"
	@echo "  make order                   порядок занятий и проверка его детерминированности"
	@echo "  make status                  состояние курса и корпуса"

search:
	test -n "$(QUERY)" || (echo "Укажите QUERY=..."; exit 1)
	$(VENV_PY) tools/rag_search.py "$(QUERY)" -k $(K)



session:
	test -n "$(n)" || (echo "Укажите n=НомерЗанятия"; exit 1)
	$(PY) tools/session_material.py $(n)

assignment:
	test -n "$(n)" || (echo "Укажите n=НомерЗанятия"; exit 1)
	$(PY) tools/assignment_brief.py $(n)

verify:
	$(VENV_PY) tools/verify_quotes.py

serve:
	$(VENV_PY) tools/rag_api.py --port $(port)

status:
	$(PY) tools/status.py

# Порядок занятий — свойство программы, а не обучающегося: уровень подготовки
# меняет темп и глубину, но не последовательность тем. Проверка падает, если
# занятия переставлены, блок начат раньше своего основания или сводное занятие
# перестало быть последним в блоке.
order:
	$(PY) tools/curriculum_order.py

order-check:
	$(PY) tools/curriculum_order.py --check

quotes:
	$(VENV_PY) tools/quote_finder.py "$(QUERY)"

# --- Корпус курса: обязательное получение индекса И текстов -----------------
# Курс не готов к занятиям, пока корпус не установлен: без текстов
# цитируемый фрагмент нечем подтвердить. `make corpus-fetch` вызывается при
# развёртывании (scripts/install.py и botai) и вручную, когда корпуса нет.
corpus-fetch:
	$(PY) tools/corpus_fetch.py $(if $(URL),--url "$(URL)") $(if $(TEXTS_URL),--texts-url "$(TEXTS_URL)") $(if $(FORCE),--force,)

corpus-status:
	$(PY) tools/corpus_fetch.py --status

# Совместимость: старые инструкции и навыки вызывают index-fetch.
index-fetch: corpus-fetch
