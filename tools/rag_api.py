#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Wrapper for the corpus RAG HTTP API (rag_api.py). Starts/connects the server
that the agent can call over HTTP.

Usage:
  python tools/rag_api.py --port 8765
  # then:  curl "http://127.0.0.1:8765/search?q=...&k=5"
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
SCRIPT = os.path.join(ROOT, "scripts", "rag_api.py")


def main():
    if not os.path.exists(SCRIPT):
        sys.stderr.write(f"[tools] корпус не найден: {SCRIPT}\nСм. CORPUS.md\n")
        return 2
    py = os.environ.get("COURSE_VENV_PY") or sys.executable
    exe = py if os.path.exists(py) else sys.executable
    return subprocess.call([exe, SCRIPT] + sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())