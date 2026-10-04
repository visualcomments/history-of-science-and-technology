# Makefile для агента: короткие цели для работы с курсом и корпусом

PY ?= python3
VENV_PY ?= $(PY)

.PHONY: help search index-fetch session assignment verify serve status quotes corpus-fetch corpus-status order order-check physics-validate physics-benchmark physics-search physics-extract physics-sample-check physics-hf-pr

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
	@echo "  make physics-validate FILE=records.jsonl  проверка записей физического модуля"
	@echo "  make physics-benchmark       воспроизводимый benchmark физического модуля"
	@echo "  make physics-search QUERY=\"...\" DOMAIN=AERO   поиск метаданных (OpenAlex/arXiv/Crossref)"
	@echo "  make physics-extract SPEC=... MANIFEST=... DOMAIN=AERO   сбор записей из спеки"
	@echo "  make physics-sample-check RECORDS=...   выборочная проверка записей"
	@echo "  make physics-hf-pr RECORDS=... [PUBLISH=1]   Hub-PR физического датасета (по умолчанию dry-run)"

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

# --- Исследовательский модуль: физические данные и соревнование --------------
# Схема и валидатор живут в physics-dataset-competition/; каталог не входит в
# тридцать занятий, поэтому цели вынесены отдельно и не мешают `make order`.
# Без FILE валидатор запускается в режиме --selftest (доказывает, что умеет
# падать), с FILE — проверяет конкретный JSONL-файл записей.
physics-validate:
	$(PY) physics-dataset-competition/src/physics_ds/schema/validate.py $(if $(FILE),$(FILE),--selftest)

physics-benchmark:
	$(PY) physics-dataset-competition/benchmark/run.py

# --- Физический модуль: первое экспертное задание ----------------------------
# Полная процедура — physics-dataset-competition/docs/EXPERT-ASSIGNMENT.md.
# Скачанные первоисточники живут только в .local/physics-bronze/ (вне git);
# токен HF — только из окружения HF_TOKEN; секреты и raw-файлы не коммитятся.
# Цели запускаются в Linux CI: mkdir -p создаёт выходные каталоги безопасно.
PHYSICS_BRONZE ?= .local/physics-bronze

physics-search:
	test -n "$(QUERY)" || (echo "Укажите QUERY=\"...\""; exit 1)
	test -n "$(DOMAIN)" || (echo "Укажите DOMAIN=AERO|STR|RADAR|CTRL"; exit 1)
	mkdir -p $(PHYSICS_BRONZE)
	$(PY) physics-dataset-competition/scripts/collect.py search \
		--service $(if $(SERVICE),$(SERVICE),all) --domain $(DOMAIN) \
		--query "$(QUERY)" --limit $(if $(LIMIT),$(LIMIT),10) \
		--out $(if $(PHYSICS_OUT),$(PHYSICS_OUT),$(PHYSICS_BRONZE)/candidates.jsonl)

physics-extract:
	test -n "$(SPEC)" || (echo "Укажите SPEC=spec.json"; exit 1)
	test -n "$(MANIFEST)" || (echo "Укажите MANIFEST=candidates.jsonl"; exit 1)
	test -n "$(DOMAIN)" || (echo "Укажите DOMAIN=AERO|STR|RADAR|CTRL"; exit 1)
	test -f "$(SPEC)" || (echo "Нет файла: $(SPEC)"; exit 2)
	test -f "$(MANIFEST)" || (echo "Нет файла: $(MANIFEST)"; exit 2)
	mkdir -p $(PHYSICS_BRONZE)
	$(PY) physics-dataset-competition/scripts/extract.py \
		--spec "$(SPEC)" \
		--out $(if $(OUT),$(OUT),$(PHYSICS_BRONZE)/records.jsonl)

physics-sample-check:
	test -n "$(RECORDS)" || (echo "Укажите RECORDS=records.jsonl"; exit 1)
	test -f "$(RECORDS)" || (echo "Нет файла: $(RECORDS)"; exit 2)
	$(PY) physics-dataset-competition/scripts/validate_sample.py \
		--records "$(RECORDS)" \
		--sample $(if $(SAMPLE),$(SAMPLE),1.0) --seed $(if $(SEED),$(SEED),42) \
		--report $(if $(REPORT),$(REPORT),.local/physics-bronze/sample-report.json)

# По умолчанию dry-run (план без сети); реальный PR — только PUBLISH=1.
# Токен HF_TOKEN берётся издателем из окружения; в Makefile его нет и не будет.
physics-hf-pr:
	test -n "$(RECORDS)" || (echo "Укажите RECORDS=records.jsonl"; exit 1)
	test -f "$(RECORDS)" || (echo "Нет файла: $(RECORDS)"; exit 2)
	$(PY) physics-dataset-competition/src/physics_ds/publish/hf.py \
		--records "$(RECORDS)" \
		--repo-id $(if $(REPO_ID),$(REPO_ID),chaotic-good-project/physics-experiment-records) \
		--revision $(if $(REVISION),$(REVISION),expert/submission) \
		$(if $(TITLE),--title "$(TITLE)",) \
		$(if $(PUBLISH),,--dry-run)
