#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Wrapper for the corpus RAG search. Runs the local corpus search (requires COURSE_CORPUS_ROOT). Runs the real script in <root>/scripts/rag_search.py.

Usage (from repo root):
  python tools/rag_search.py "Математические начала Ньютона" -k 5
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
SCRIPT = os.path.join(ROOT, "scripts", "rag_search.py")


def main():
    if not os.path.exists(SCRIPT):
        sys.stderr.write(
            f"[tools] корпус не найден: {SCRIPT}\n"
            "Подключите локальный корпус: установите COURSE_CORPUS_ROOT на каталог с scripts/, "
            "txt/, index/ или расположите репозиторий курса внутри этого рабочего пространства.\n"
            "См. CORPUS.md\n")
        return 2
    py = os.environ.get("COURSE_VENV_PY") or sys.executable
    exe = py if os.path.exists(py) else sys.executable
    return subprocess.call([exe, SCRIPT] + sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())