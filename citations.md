# Цитирование и источники курса

## Правила цитирования

1. Каждая прямая цитата в лекциях приведена **дословно** из файла корпуса
   `txt/…` (папка `txt/` — текстовые версии источников; автоматическая
   проверка — `scripts/verify_quotes.py`, отчёт —
   `verification/REPORT.md`).
2. Ссылка на цитату содержит: имя файла корпуса и номер фрагмента
   (chunk) в RAG-индексе (`index/chunks.jsonl`). Фрагмент можно прочитать
   и найти аналоги по запросу:
   `python3 scripts/rag_search.py "запрос" -k 5`.
3. Ввиду OCR-происхождения текстов допускаются нормализации: пробелы,
   переносы строк и дефисные разрывы слов не учитываются при проверке;
   строчные/заглавные буквы и ё/е сравнения производятся после
   нормализации. Содержательные расхождения не допускаются.
4. Авторские интерпретации, связки и «синтезы» (разделы, помеченные как
   «авторский синтез») **не являются цитатами** и не претендуют на
   передачу текста источников; они опираются на общеизвестные факты
   истории науки, которые в самом курсе указаны как обзорные.
5. Цитаты используются в учебных целях (ст. 1274 ГК РФ «свободное
   использование произведений в информационных, научных, учебных или
   культурных целях»). Корпус составлен преимущественно из источников
   публичного достояния.

## Источники корпуса по модулям

| Модуль | Файлы корпуса (основные) |
|---|---|
| 01 | `history_of_engineering__Беседы_о_механике.txt`, `history_of_mathematics__История_математики_в_древности_и_в_средние_века.txt`, `history_of_physics__Исаак_Ньютон.txt` |
| 02 | `history_of_engineering__The_Origins_of_Invention_….txt`, `history_of_mathematics__История_математики_в_древности_и_в_средние_века.txt` |
| 03 | `history_of_mathematics__История_математики_в_древности_и_в_средние_века.txt`, `History_of_Mathematics_vol.1.txt`, `A_Short_Account_of_the_History_of_Mathematics.txt` |
| 04 | `history_of_mathematics__История_математики_в_XVI_и_XVII_веках.txt`, `History_of_Mathematics_vol.1.txt` |
| 05 | `history_of_science_general__The_Dialogues_….txt`, `history_of_physics__A_History_of_Physics.txt`, `history_of_astronomy__A_Short_History_of_Astronomy.txt` |
| 06 | `history_of_physics__Исаак_Ньютон.txt`, `history_of_physics__A_History_of_Physics.txt` |
| 07 | `history_of_engineering__Lives_of_the_Engineers.txt`, `A_History_of_Inventions_and_Discoveries.txt`, `The_Origins_of_Invention_….txt` |
| 08 | `history_of_physics__A_History_of_Physics.txt` |
| 09 | `Основы_химии.txt`, `Д_И_Менделеев_Периодический_закон.djvu.txt`, `The_History_of_Chemistry.txt`, `The_Gases_of_the_Atmosphere_….txt` |
| 10 | `On_the_Origin_of_Species.txt`, `The_Descent_of_Man.txt`, `Zoological_Philosophy.txt`, `The_History_of_Creation_vol.1.txt`, `Рефлексы_головного_мозга.txt` |
| 11 | `history_of_engineering__Беседы_о_механике.txt`, `Lives_of_the_Engineers.txt` |
| 12 | `Passages_from_the_Life_of_a_Philosopher.txt` |
| Р5 / 21 век | `history_of_technology__US_Preparing_for_Future_of_AI_2016.txt`, `history_of_technology__US_National_AI_Strategic_Plan_2019.txt`, `history_of_technology__NASA_Beyond_the_Ionosphere.txt`, `history_of_computing__NASA_Computers_in_Spaceflight.txt` |

Полная инвентаризация корпуса и его происхождение — в каталоге проекта
(`catalog/`, `catalog/PROVENANCE.md`); карта «модуль → книги» основана на
верифицированных цитатах (см. `verification/REPORT.md`).

## Источники по науке и технологиям XXI века

Документы правительства США (public domain): «Preparing for the Future
of Artificial Intelligence» (NSTC, 2016) и «The National Artificial
Intelligence Research and Development Strategic Plan» (NSTC, 2019).
Издания NASA (работы правительства США): «Beyond the Ionosphere: Fifty
Years of Satellite Communication» (NASA SP-4217) и «Computers in
Spaceflight: The NASA Experience» (J. E. Tomayko, 1988). Тексты
включены в корпус как «проверенные источники» наряду с классическими
трудами публичного достояния; они лицензией курса (GPL-3.0) не
покрываются, но свободны для цитирования в учебных целях.