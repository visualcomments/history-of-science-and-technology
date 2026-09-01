#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Wrapper for the corpus RAG search. Locates the local workspace (FALT_CORPUS_ROOT
or <repo>/../..), then runs the real script in <root>/scripts/rag_search.py.

Usage (from repo root):
  python tools/rag_search.py "Математические начала Ньютона" -k 5
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get("FALT_CORPUS_ROOT") or os.path.abspath(os.path.join(HERE, "..", ".."))
SCRIPT = os.path.join(ROOT, "scripts", "rag_search.py")


def main():
    if not os.path.exists(SCRIPT):
        sys.stderr.write(
            f"[tools] корпус не найден: {SCRIPT}\n"
            "Подключите локальный корпус: установите FALT_CORPUS_ROOT на каталог с scripts/, "
            "txt/, index/ или расположите репозиторий курса внутри этого рабочего пространства.\n"
            "См. CORPUS.md\n")
        return 2
    py = os.environ.get("FALT_VENV_PY") or os.path.join(ROOT, ".venv", "Scripts", "python.exe")
    exe = py if os.path.exists(py) else sys.executable
    return subprocess.call([exe, SCRIPT] + sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())