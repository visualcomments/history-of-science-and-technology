#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Prepare the local OpenCode expert workspace without manual shell setup.

The script is stdlib-only. It creates an ignored virtual environment, verifies
the calibration harness, and reports whether HF_TOKEN exists without printing
its value. Optional Hub dependencies are deliberately installed only after a
separate, explicit publication confirmation in the OpenCode chat.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import venv


ROOT = Path(__file__).resolve().parents[2]
LOCAL = ROOT / ".local"
DEFAULT_VENV = LOCAL / "opencode-expert-venv"
TEST_TARGET = ROOT / "physics-dataset-competition" / "tests" / "calibration"


def venv_python(path: Path) -> Path:
    return path / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def run(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--venv", type=Path, default=DEFAULT_VENV)
    args = parser.parse_args()

    venv_path = args.venv if args.venv.is_absolute() else ROOT / args.venv
    venv_path.parent.mkdir(parents=True, exist_ok=True)
    if not venv_python(venv_path).is_file():
        venv.EnvBuilder(with_pip=True, clear=False).create(venv_path)

    python = venv_python(venv_path)
    install = run([str(python), "-m", "pip", "install", "--quiet", "pytest"], cwd=ROOT)
    if install.returncode != 0:
        print(install.stdout, file=sys.stderr)
        return 1
    version = run([str(python), "--version"], cwd=ROOT)
    tests = run([str(python), "-m", "pytest", str(TEST_TARGET), "-q"], cwd=ROOT)
    result = {
        "ok": version.returncode == 0 and tests.returncode == 0,
        "venv": str(venv_path.relative_to(ROOT)),
        "python": version.stdout.strip(),
        "calibration_tests": "passed" if tests.returncode == 0 else "failed",
        "hf_token_configured": bool(os.environ.get("HF_TOKEN")),
        "publisher_dependencies": "install only after explicit publish confirmation",
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    if tests.returncode != 0:
        print(tests.stdout, file=sys.stderr)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
