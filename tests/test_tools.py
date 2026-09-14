#!/usr/bin/env python3
"""Тесты инструментов курса «История и философия науки и технологий».

Проверяют, что инструменты в `tools/` работают на реальных данных курса:
валидатор целостности проходит, структура 30 занятий единообразна,
капстоун-модуль связан с программой, верификация цитат без расхождений.

Запуск:
    python3 tests/test_tools.py    # автономно
    python3 -m pytest tests/ -q    # через pytest
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"

_passed = 0
_failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    global _passed
    if condition:
        _passed += 1
        print(f"  ok   {name}")
    else:
        _failures.append(name)
        print(f"  FAIL {name}  {detail}")


def run_tool(script: str, *args: str, timeout: int = 180) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(TOOLS / script), *args],
        capture_output=True, text=True, cwd=ROOT, timeout=timeout)


def main() -> int:
    print("[целостность курса]")

    r = run_tool("validate_course.py")
    check("валидатор курса завершается успешно", r.returncode == 0,
          (r.stdout + r.stderr)[-300:])
    check("валидатор сообщает о пройденных проверках",
          "Все проверки пройдены" in r.stdout, r.stdout[-200:])

    r = run_tool("validate_course.py", "--json")
    if r.returncode == 0:
        try:
            data = json.loads(r.stdout)
            check("валидатор выдаёт машиночитаемый отчёт",
                  data.get("ok") is True, str(data)[:200])
            check("валидатор проверяет 30 занятий",
                  data.get("lectures") == 30, str(data.get("lectures")))
            check("15 занятий в осеннем семестре",
                  data.get("fall") == 15, str(data.get("fall")))
            check("15 занятий в весеннем семестре",
                  data.get("spring") == 15, str(data.get("spring")))
            check("валидатор проверил относительные ссылки",
                  data.get("relative_links_checked", 0) > 0,
                  str(data.get("relative_links_checked")))
        except json.JSONDecodeError as e:
            check("валидатор выдаёт корректный JSON", False, str(e))
    else:
        check("валидатор работает с --json", False, r.stderr[-200:])

    print("\n[структура занятий]")

    lectures = sorted((ROOT / "lectures").glob("*.md"))
    check("занятий ровно 30", len(lectures) == 30, f"найдено {len(lectures)}")

    # Lesson 01 is organisational and has its own shape; see the validator.
    common = ("## О чём занятие", "## Цели занятия", "## Источники и свидетельства",
              "## Вопросы для самопроверки", "## Задания")
    for lp in lectures:
        text = lp.read_text(encoding="utf-8")
        if lp.name == "01_uvodnoe.md":
            text_required = ("## О чём занятие", "## Цели занятия",
                             "## Как работать с корпусом", "## Вопросы для самопроверки")
            missing = [s for s in text_required if s not in text]
        else:
            missing = [s for s in common if s not in text]
        check(f"{lp.name} содержит все обязательные разделы",
              not missing, f"нет: {missing}")
        check(f"{lp.name} имеет навигацию", "**Навигация:**" in text,
              "нет блока навигации")

    print("\n[программа, семестры, капстоун]")

    syllabus_md = (ROOT / "syllabus.md").read_text(encoding="utf-8")
    linked = sum(1 for lp in lectures if lp.name in syllabus_md)
    check("каждое занятие связано с программой", linked == 30,
          f"связано {linked} из 30")

    syllabus_json = ROOT / "syllabus.json"
    if syllabus_json.is_file():
        try:
            data = json.loads(syllabus_json.read_text(encoding="utf-8"))
            check("syllabus.json разбирается", isinstance(data, dict), "не объект")
        except json.JSONDecodeError as e:
            check("syllabus.json разбирается", False, str(e))

    capstone = ROOT / "capstone-aviation-radar"
    check("капстоун-модуль на месте", capstone.is_dir(), "каталог отсутствует")
    if capstone.is_dir():
        check("README капстоуна на месте", (capstone / "README.md").is_file(),
              "файл отсутствует")
        check("лицензия датасета на месте",
              (capstone / "DATASET-LICENSE.md").is_file(), "файл отсутствует")
        steps = ("10-legal-public-domain.md", "20-assignments.md",
                 "30-dataset-spec-template.md", "40-kaggle-publish.md",
                 "45-community-competition.md")
        for s in steps:
            check(f"шаг капстоуна {s} на месте", (capstone / s).is_file(),
                  "файл отсутствует")
        check("капстоун связан с программой",
              "capstone-aviation-radar" in syllabus_md,
              "не упоминается в syllabus.md")

    for doc in ("CORPUS.md", "PROVENANCE.md", "citations.md", "AGENTS.md",
                "LICENSE", "LICENSE-CONTENT.md", "verification/REPORT.md"):
        check(f"{doc} на месте", (ROOT / doc).is_file(), "файл отсутствует")

    print("\n[порядок занятий]")
    # Порядок тем — свойство программы, а не обучающегося: проверяем и сам
    # порядок, и то, что проверка способна упасть (иначе она ничего не значит).
    proc = run_tool("curriculum_order.py", "--check")
    check("порядок занятий детерминирован", proc.returncode == 0,
          (proc.stdout + proc.stderr).strip()[:200])

    order_proc = run_tool("curriculum_order.py", "--json")
    if order_proc.returncode == 0:
        try:
            plan = json.loads(order_proc.stdout)
        except json.JSONDecodeError as e:
            plan = None
            check("план занятий разбирается", False, str(e))
        if plan is not None:
            nums = [s["n"] for s in plan["sessions"]]
            check("план содержит 30 занятий по порядку",
                  nums == list(range(1, 31)), f"получено {nums}")
            check("порядок не зависит от уровня подготовки",
                  all("level" not in s for s in plan["sessions"]),
                  "в плане появилось поле уровня: порядок начал зависеть от студента")

    # Проверка, которая не может упасть, ничего не проверяет: ломаем копию
    # программы (переставляем занятия) и убеждаемся, что инструмент это ловит.
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        broken = Path(tmp) / "syllabus.json"
        data = json.loads((ROOT / "syllabus.json").read_text(encoding="utf-8"))
        data["sessions"][2]["n"], data["sessions"][3]["n"] = 4, 3   # 3 <-> 4
        broken.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        sys.path.insert(0, str(TOOLS))
        import curriculum_order as co
        problems = co.check_order(json.loads(broken.read_text(encoding="utf-8")))
        check("перестановка занятий обнаруживается", bool(problems),
              "перестановка 3<->4 прошла незамеченной")

    print("\n[отчёт верификации цитат]")
    report = ROOT / "verification" / "REPORT.md"
    if report.is_file():
        text = report.read_text(encoding="utf-8")
        check("верификация без неудач",
              "неудач: **0**" in text or "неудач: 0" in text, "есть неудачи")
        check("отчёт содержит таблицу цитат", "| Лекция |" in text, "нет таблицы")

    print(f"\n{_passed} passed, {len(_failures)} failed")
    if _failures:
        for f in _failures:
            print(f"  - {f}")
        return 1
    return 0


def test_course_integrity() -> None:
    """Pytest entry point: the whole suite must pass."""
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
