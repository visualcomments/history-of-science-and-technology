"""
Обёртка проверки цитат. Запускает рабочий скрипт корпуса
(`<COURSE_CORPUS_ROOT>/scripts/verify_quotes.py`): проверяет каждую цитату
курса по локальному корпусу и пишет `verification/REPORT.md`.

Коды возврата (важно для агента и CI):
  0 — все цитаты подтверждены;
  1 — есть неподтверждённые цитаты (рабочий скрипт вернул 1);
  2 — корпус не подключён: нет COURSE_CORPUS_ROOT или нет самого скрипта.
      Это НЕ значит «цитаты неверны»: это значит, что проверить их нечем,
      и курс в таком состоянии не готов к занятиям по цитатам.
"""

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get("COURSE_CORPUS_ROOT")
if not ROOT:
    sys.stderr.write(
        "[tools] Установите COURSE_CORPUS_ROOT (каталог с txt/, index/, scripts/ корпуса).\n"
        "См. CORPUS.md в корне репозитория.\n")
    sys.exit(2)
SCRIPT = os.path.join(ROOT, "scripts", "verify_quotes.py")


def main():
    if not os.path.exists(SCRIPT):
        sys.stderr.write(
            f"[tools] корпус не найден: {SCRIPT}\n"
            "Проверить цитаты нечем. Это не значит, что цитаты неверны —\n"
            "значит, что корпус не установлен: make corpus-status\n"
            "См. CORPUS.md\n")
        return 2
    py = os.environ.get("COURSE_VENV_PY") or sys.executable
    exe = py if os.path.exists(py) else sys.executable
    return subprocess.call([exe, SCRIPT] + sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
