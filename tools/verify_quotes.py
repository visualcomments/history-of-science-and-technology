#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Wrapper for quote verification (verify_quotes.py). Verifies every quote cited
in course/lectures/*.md against the local corpus and writes
verification/REPORT.md. Exit code 1 if any quote fails.

Usage:
  python tools/verify_quotes.py
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get("FALT_CORPUS_ROOT") or os.path.abspath(os.path.join(HERE, "..", ".."))
SCRIPT = os.path.join(ROOT, "scripts", "verify_quotes.py")


def main():
    if not os.path.exists(SCRIPT):
        sys.stderr.write(f"[tools] корпус не найден: {SCRIPT}\nСм. CORPUS.md\n")
        return 2
    py = os.environ.get("FALT_VENV_PY") or os.path.join(ROOT, ".venv", "Scripts", "python.exe")
    exe = py if os.path.exists(py) else sys.executable
    return subprocess.call([exe, SCRIPT] + sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())