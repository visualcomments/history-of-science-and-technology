#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Status: reports what is available for the agent — repo layout, corpus presence
(COURSE_CORPUS_ROOT), RAG index, quote-verification state, and, importantly,
what is NOT available. A status tool that only prints what exists teaches the
agent to assume the rest is fine.

Usage:  python tools/status.py
"""
import glob
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, ".."))
ROOT = os.environ.get("COURSE_CORPUS_ROOT")


def main():
    if not ROOT:
        print("корпус не настроен: установите COURSE_CORPUS_ROOT (см. CORPUS.md)")
        return 2
    print("== Репозиторий курса ==")
    print(f"repo root: {REPO}")
    lecs = sorted(glob.glob(os.path.join(REPO, "lectures", "*.md")))
    print(f"занятий: {len(lecs)}")
    if os.path.exists(os.path.join(REPO, "verification", "REPORT.md")):
        head = open(os.path.join(REPO, "verification", "REPORT.md"), encoding="utf-8").read()
        for l in head.splitlines()[:4]:
            print("  " + l)
    sy = os.path.join(REPO, "syllabus.json")
    if os.path.exists(sy):
        d = json.load(open(sy, encoding="utf-8"))
        print(f"syllabus.json: {d['meta']['sessions_total']} занятий, "
              f"модулей: {len(d['modules'])}")
    print()
    print("== Локальный корпус ==")
    ntxt = len(glob.glob(os.path.join(ROOT, "txt", "*.txt")))
    idx = os.path.join(ROOT, "index", "config.json")
    print(f"корпус root: {ROOT}")
    print(f"txt файлов: {ntxt}")
    have_index = os.path.exists(idx)
    if have_index:
        c = json.load(open(idx, encoding="utf-8"))
        print(f"RAG-индекс: {c.get('n_chunks')} чанков, {c.get('n_files')} файлов, "
              f"backend: {c.get('backend')}")
    else:
        print("RAG-индекс: НЕ НАЙДЕН (нужен scripts/rag_build*.py и корпус)")
    api = os.path.join(ROOT, "scripts", "rag_api.py")
    print(f"RAG-API скрипт: {'есть' if os.path.exists(api) else 'нет'}")

    # --- чего НЕТ: говорим прямо, иначе агент считает отсутствующее рабочим ---
    print()
    print("== Чего сейчас нет ==")
    if not have_index:
        print("  семантический поиск: НЕДОСТУПЕН — нет RAG-индекса "
              "(make search работать не будет)")
    if not ntxt:
        print("  проверка цитат:      НЕДОСТУПНА — нет текстов txt/*.txt")
        print("                       (тексты корпуса в репозитории не публикуются:")
        print("                        см. corpus-manifest.example.json — url и хэши пусты)")
    manifest_txt = os.path.join(REPO, "corpus-manifest.json")
    if not os.path.exists(manifest_txt):
        print("  манифест текстов:    отсутствует (есть только образец "
              "corpus-manifest.example.json)")
    if have_index and ntxt:
        print("  (ничего — корпус полный)")
    print()
    print("  что доступно без корпуса: make session n=NN, make assignment n=NN,")
    print("  make order, syllabus.md, lectures/, citations.md, verification/REPORT.md")
    return 0 if (have_index and ntxt) else 1


if __name__ == "__main__":
    sys.exit(main())