#!/usr/bin/env python3
"""Проверка целостности курса «История и философия науки и технологий».

Курс состоит из 30 занятий, программы, корпуса, капстоун-модуля и
инструментов. Скрипт следит за тем, чтобы связи между ними не
распадались: каждое занятие существует и достижимо из программы,
структура занятий единообразна, все ссылки разрешаются.

Запуск:
    python3 tools/validate_course.py [--json]

Код возврата 1 при любой проблеме — чтобы CI падал заметно, а не
пропускал молчаливое расхождение.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LECTURES = ROOT / "lectures"
SYLLABUS_MD = ROOT / "syllabus.md"
SYLLABUS_JSON = ROOT / "syllabus.json"
CAPSTONE = ROOT / "capstone-aviation-radar"

LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
LESSONS = 30
FALL_LESSONS = 15

# Every lecture must keep these sections. They encode the pedagogy of the
# course: a framing of the topic, the learning goals, evidence from the
# corpus, a way for the student to check themselves, and work to do.
REQUIRED_SECTIONS = (
    "## О чём занятие",
    "## Цели занятия",
    "## Источники и свидетельства",
    "## Вопросы для самопроверки",
    "## Задания",
)

# Lesson 01 is organisational: it explains how to work with the corpus
# instead of citing it, and carries a single introductory task. Requiring
# the standard sections there would force a rewrite of valid content, so it
# gets its own list rather than being bent into the common shape.
SPECIAL_SECTIONS = {
    "01_uvodnoe.md": (
        "## О чём занятие",
        "## Цели занятия",
        "## Как работать с корпусом",
        "## Вопросы для самопроверки",
        "## Задание",
    ),
}

problems: list[str] = []
checks_run = 0


def check(name: str, condition: bool, message: str) -> None:
    global checks_run
    checks_run += 1
    if not condition:
        problems.append(f"{name}: {message}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="машиночитаемый вывод")
    args = parser.parse_args()

    # ── 1. программа существует ───────────────────────────────────────────
    check("syllabus.md существует", SYLLABUS_MD.is_file(), "файл отсутствует")
    check("syllabus.json существует", SYLLABUS_JSON.is_file(), "файл отсутствует")

    syllabus_text = SYLLABUS_MD.read_text(encoding="utf-8") if SYLLABUS_MD.is_file() else ""
    if SYLLABUS_JSON.is_file():
        try:
            json.loads(SYLLABUS_JSON.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            problems.append(f"syllabus.json не является корректным JSON: {e}")

    # ── 2. каждое занятие существует и достижимо из программы ─────────────
    lecture_files: list[Path] = []
    for n in range(1, LESSONS + 1):
        matches = sorted(LECTURES.glob(f"{n:02d}_*.md"))
        check(f"занятие {n:02d} существует", len(matches) == 1,
              f"найдено файлов: {len(matches)}")
        if not matches:
            continue
        lecture_files.append(matches[0])
        check(f"занятие {n:02d} связано с программой",
              matches[0].name in syllabus_text,
              f"{matches[0].name} не упоминается в syllabus.md")

    check("занятий ровно 30", len(lecture_files) == LESSONS,
          f"найдено {len(lecture_files)}")

    # ── 3. структура каждого занятия ──────────────────────────────────────
    for lp in lecture_files:
        text = lp.read_text(encoding="utf-8")
        required = SPECIAL_SECTIONS.get(lp.name, REQUIRED_SECTIONS)
        for section in required:
            check(f"{lp.name} содержит {section!r}", section in text,
                  f"отсутствует раздел {section!r}")
        check(f"{lp.name} имеет навигацию", "**Навигация:**" in text,
              "нет блока навигации в конце занятия")

    # ── 4. разбиение по семестрам ─────────────────────────────────────────
    fall = [p for p in lecture_files if int(p.name[:2]) <= FALL_LESSONS]
    spring = [p for p in lecture_files if int(p.name[:2]) > FALL_LESSONS]
    check("осенний семестр — 15 занятий", len(fall) == FALL_LESSONS,
          f"найдено {len(fall)}")
    check("весенний семестр — 15 занятий", len(spring) == LESSONS - FALL_LESSONS,
          f"найдено {len(spring)}")

    # ── 5. капстоун-модуль существует и связан с программой ───────────────
    check("капстоун-модуль существует", CAPSTONE.is_dir(), "каталог отсутствует")
    if CAPSTONE.is_dir():
        check("README капстоуна существует", (CAPSTONE / "README.md").is_file(),
              "файл отсутствует")
        check("лицензия датасета существует",
              (CAPSTONE / "DATASET-LICENSE.md").is_file(), "файл отсутствует")
        check("капстоун связан с программой",
              "capstone-aviation-radar" in syllabus_text,
              "капстоун не упоминается в syllabus.md")

    # ── 6. все относительные ссылки разрешаются ───────────────────────────
    docs = [SYLLABUS_MD] + lecture_files
    docs += sorted((ROOT / "docs").glob("*.md"))
    docs += sorted((ROOT / "verification").glob("*.md"))
    docs += sorted(CAPSTONE.glob("*.md")) if CAPSTONE.is_dir() else []
    total_links = 0
    for md in docs:
        if not md.is_file():
            continue
        for m in LINK_RE.finditer(md.read_text(encoding="utf-8", errors="replace")):
            target = m.group(2).split("#")[0].strip()
            if not target or target.startswith(("http://", "https://", "mailto:")):
                continue
            total_links += 1
            check("ссылка разрешается", (md.parent / target).resolve().exists(),
                  f"{md.relative_to(ROOT)} -> {target}")

    # ── 7. документы, на которые опирается курс, на месте ─────────────────
    for rel in ("CORPUS.md", "PROVENANCE.md", "citations.md", "AGENTS.md",
                "LICENSE", "LICENSE-CONTENT.md", "verification/REPORT.md"):
        check(f"{rel} существует", (ROOT / rel).is_file(), "файл отсутствует")

    # ── 8. контракт цитирования: координаты в отчёте верификации ──────────
    report = ROOT / "verification" / "REPORT.md"
    if report.is_file():
        text = report.read_text(encoding="utf-8")
        check("отчёт верификации не содержит неудач",
              "неудач: **0**" in text or "неудач: 0" in text,
              "в отчёте верификации есть неудачные цитаты")
        check("отчёт верификации содержит таблицу цитат",
              "| Лекция |" in text, "нет таблицы цитат")

    # ── отчёт ─────────────────────────────────────────────────────────────
    if args.json:
        print(json.dumps({
            "checks_run": checks_run,
            "problems": problems,
            "relative_links_checked": total_links,
            "lectures": len(lecture_files),
            "fall": len(fall),
            "spring": len(spring),
            "ok": not problems,
        }, ensure_ascii=False, indent=2))
    else:
        print(f"Проверка курса: {checks_run} проверок, "
              f"{total_links} относительных ссылок, занятий {len(lecture_files)} "
              f"({len(fall)} осень + {len(spring)} весна)")
        if problems:
            print(f"\nПроблем: {len(problems)}")
            for p in problems:
                print(f"  - {p}")
        else:
            print("Все проверки пройдены.")

    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
