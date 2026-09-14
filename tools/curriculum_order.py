#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Детерминированный порядок занятий курса.

Порядок занятий — свойство **программы**, а не обучающегося. Это правило
записано здесь один раз и проверяется автоматически, потому что нарушение
порядка не выглядит поломкой: занятие просто оказывается раньше своего
основания, и обучающийся встречает материал, к которому ещё не подведён.

Три уровня, от сильного к слабому:

1. **Последовательность `sessions[].n`.** Механическая основа: номера идут
   1..N без пропусков и повторов. Ничто не может её изменить.
2. **Пререквизиты модулей (`depends_on`).** Модуль не начинается раньше
   модуля, от которого зависит, и не раньше, чем закончились все занятия
   предыдущего модуля.
3. **Внутренний порядок темы.** Занятие следует за предыдущим внутри своего
   блока модулей (`М01`, `М02–М03`, `01–07`, …), а итоговые занятия блока
   («Итоговое…», «сквозные линии») стоят последними в своём блоке.

Чего порядок **не** делает и почему:

- он **не** переставляется под уровень подготовки. Уровень меняет *как*
  преподавать (темп, глубину, объём практики, объём подсказок), но не *что за
  чем следует*: программа утверждена рабочей программой дисциплины, и её
  последовательность — часть содержания курса, а не настройка интерфейса.
  Обучающийся может начать с любого занятия — тогда он изучает материал
  нелинейно, и это сообщается прямо, а не выдаётся за «адаптированный порядок»;
- он **не** выводится из похожести тем, из ссылок между лекциями или из
  «удобства»: любой такой вывод был бы недетерминированным — два запуска
  давали бы разный порядок, и курс перестал бы быть воспроизводимым.

Запуск:
    python3 tools/curriculum_order.py            # порядок + проверка
    python3 tools/curriculum_order.py --json     # машиночитаемо
    python3 tools/curriculum_order.py --check     # только проверка (код 1 при нарушении)

Модуль используется валидатором (`tools/validate_course.py`) и тестами, чтобы
нарушение порядка падало в CI, а не обнаруживалось на занятии.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SYLLABUS = ROOT / "syllabus.json"

# Итоговые занятия внутри блока: стоят последними в своём блоке, потому что
# обобщают его. Признак намеренно текстовый и узкий: расширять его следует
# только вместе с программой.
SUMMARY_MARKERS = ("итогов", "сквозные линии", "обзорн")

SEMESTERS = ("fall", "spring")


class OrderProblem(Exception):
    """Нарушение порядка занятий."""


def load_syllabus(path=SYLLABUS):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def module_ids(data):
    return [m["id"] for m in data.get("modules", [])]


def sessions(data):
    """Занятия в порядке объявления — НЕ отсортированные.

    Сортировка по `n` была ошибкой: она скрывала ровно то нарушение, ради
    которого инструмент существует. Поменяв номера у двух занятий (3 <-> 4),
    файл программы задаёт другой маршрут, но сортировка возвращала его к
    виду «1..N», и проверка молчала. Порядок объявления — это и есть порядок
    программы; номер обязан ему соответствовать, и проверяется это ниже.
    """
    return list(data.get("sessions", []))


def sessions_by_number(data):
    """Занятия по номерам — для отчётов о покрытии, где важен сам номер."""
    return sorted(data.get("sessions", []), key=lambda s: s["n"])


def module_span(data):
    """Первый и последний номер занятия каждого модуля."""
    span = {}
    for s in sessions(data):
        for mid in expand_module(s.get("module", "")):
            lo, hi = span.get(mid, (s["n"], s["n"]))
            span[mid] = (min(lo, s["n"]), max(hi, s["n"]))
    return span


def expand_module(field):
    """`М01`, `04`, `01–07`, `Р2–Р3` -> список идентификаторов модулей.

    Поле в программе человеческое, поэтому принимаются оба вида записи и
    диапазоны; всё, что не является модулем (например, раздел РУП), отбрасывается.
    """
    if not field:
        return []
    text = str(field).replace("М", "").replace("м", "")
    out = []
    for part in re.split(r"[,\s]+", text.strip()):
        if not part:
            continue
        m = re.match(r"^(\d{1,2})\s*[–\-—]\s*(\d{1,2})$", part)
        if m:
            lo, hi = int(m.group(1)), int(m.group(2))
            out.extend("%02d" % n for n in range(min(lo, hi), max(lo, hi) + 1))
        elif re.match(r"^\d{1,2}$", part):
            out.append("%02d" % int(part))
    return out


def is_summary(title):
    low = (title or "").lower()
    return any(marker in low for marker in SUMMARY_MARKERS)


def check_order(data):
    """Проверить порядок. Возвращает список проблем (пустой = порядок корректен)."""
    problems = []
    mods = module_ids(data)
    mod_index = {m: i for i, m in enumerate(mods)}
    order = sessions(data)

    # 1. Нумерация: 1..N без пропусков и повторов, и объявленный n совпадает с
    #    позицией в программе. Без второй половины проверка пропускает
    #    перестановку: поменяв номера у двух занятий (3 <-> 4), мы получим
    #    корректную последовательность 1..N — но уже другой маршрут, в котором
    #    «Древний мир» читается раньше «аграрной революции».
    numbers = [s["n"] for s in order]
    expected = list(range(1, len(numbers) + 1))
    if numbers != expected:
        problems.append(
            "нумерация занятий не является последовательностью 1..%d: %s"
            % (len(numbers), numbers))
    for pos, s in enumerate(order, start=1):
        declared = s.get("n")
        if declared != pos:
            problems.append(
                "занятие на позиции %d объявлено как n=%s: порядок в файле "
                "программы не совпадает с нумерацией (перестановка занятий)"
                % (pos, declared))

    # 2. Семестры: осень целиком перед весной, внутри — по номерам.
    seen_spring = False
    for s in order:
        sem = s.get("sem")
        if sem not in SEMESTERS:
            problems.append("занятие %s: неизвестный семестр %r" % (s["n"], sem))
        if sem == "spring":
            seen_spring = True
        elif sem == "fall" and seen_spring:
            problems.append(
                "занятие %s: осенний семестр идёт после весеннего" % s["n"])

    # 3. Монотонность внутри учебного потока: занятие не может начать более
    #    поздний материал раньше, чем закончился предыдущий. Границы берутся из
    #    полного блока модулей занятия: занятие 15 помечено «01–07» и потому
    #    само является концом блока 01–07, а не семью модулями, тянущимися до
    #    него. Иначе проверка запрещала бы обычную programme: модуль 03 после
    #    модуля 02.
    flow_end = {}
    for s in order:
        mods_here = expand_module(s.get("module", ""))
        if not mods_here:
            continue
        flow_end[mods_here[0]] = max(flow_end.get(mods_here[0], 0), s["n"])

    for s in order:
        mods_here = expand_module(s.get("module", ""))
        for mid in mods_here:
            if mid not in mod_index:
                problems.append("занятие %s: модуль %s отсутствует в программе"
                                % (s["n"], mid))
                continue
        if not mods_here:
            continue
        first_here = mods_here[0]
        i = mod_index[first_here]
        # Предыдущий модуль должен быть уже пройден: его последнее занятие
        # (без учёта сводного блока) идёт раньше текущего.
        for prev in mods[:i]:
            prev_last = max(
                [t["n"] for t in order
                 if prev in expand_module(t.get("module", ""))],
                default=0,
            )
            # Границы блока, к которому относится prev, не считаются: сводное
            # занятие «01–07» завершает курс осенней части и не означает, что
            # модуль 01 преподаётся до 15-го занятия.
            prev_last_without_block = max(
                [t["n"] for t in order
                 if expand_module(t.get("module", "")) == [prev]],
                default=0,
            )
            if prev_last_without_block and prev_last_without_block > s["n"]:
                problems.append(
                    "занятие %s (блок с модулем %s) идёт раньше, чем закончился "
                    "модуль %s (занятие %s)"
                    % (s["n"], first_here, prev, prev_last_without_block))

    # 4. Обратный ход внутри модуля: занятие модуля не может идти перед
    #    занятием того же модуля наоборот — ловим перестановки явно.
    last_seen = {}
    for s in order:
        for mid in expand_module(s.get("module", "")):
            if mid in last_seen and last_seen[mid] > s["n"]:
                problems.append(
                    "занятие %s (модуль %s) переставлено: предыдущее занятие "
                    "этого модуля — %s" % (s["n"], mid, last_seen[mid]))
            else:
                last_seen[mid] = s["n"]

    # 5. Итоговое занятие блока стоит последним в своём блоке.
    span = module_span(data)
    for s in order:
        if not is_summary(s.get("title", "")):
            continue
        block = expand_module(s.get("module", ""))
        if not block:
            continue  # итог по всему курсу: модуль не указан
        for mid in block:
            if mid not in span:
                continue
            if s["n"] != span[mid][1]:
                problems.append(
                    "итоговое занятие %s «%s» не последнее в модуле %s "
                    "(последнее — %s)" % (s["n"], s["title"], mid, span[mid][1]))

    return problems


def prerequisites(data, mid):
    """Пререквизиты модуля: либо явные `depends_on`, либо предыдущий модуль."""
    by_id = {m["id"]: m for m in data.get("modules", [])}
    mods = module_ids(data)
    if mid not in by_id:
        return []
    explicit = by_id[mid].get("depends_on")
    if explicit:
        return [("М" + str(x).replace("М", "")) for x in explicit]
    i = mods.index(mid)
    return [mods[i - 1]] if i > 0 else []


def plan(data):
    """Детерминированный план: занятия в порядке программы с пререквизитами."""
    span = module_span(data)
    out = []
    for s in sessions(data):
        block = expand_module(s.get("module", ""))
        prereq = []
        for mid in block:
            for p in prerequisites(data, mid):
                pid = "%02d" % int(str(p).replace("М", "")) if str(p).replace("М", "").isdigit() else p
                if pid in span:
                    prereq.append({"module": pid, "through_session": span[pid][1]})
        out.append({
            "n": s["n"],
            "semester": s.get("sem"),
            "title": s.get("title"),
            "module": s.get("module"),
            "rup": s.get("rup"),
            "summary": is_summary(s.get("title", "")),
            "after": prereq,
        })
    return out


def check_every_session_present(data):
    """Занятие, отсутствующее в файлах лекций, — тоже нарушение порядка сдачи."""
    lectures = ROOT / "lectures"
    if not lectures.is_dir():
        return []
    problems = []
    for s in sessions(data):
        n = s["n"]
        found = sorted(lectures.glob("%02d_*.md" % n))
        if len(found) != 1:
            problems.append("занятие %02d: файлов лекции %d (ожидался один)"
                            % (n, len(found)))
    return problems


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true", help="машиночитаемый вывод")
    ap.add_argument("--check", action="store_true",
                    help="только проверка: код 1 при нарушении порядка")
    args = ap.parse_args(argv)

    try:
        data = load_syllabus()
    except (OSError, ValueError) as e:
        sys.stderr.write("syllabus.json не читается: %s\n" % e)
        return 2

    problems = check_order(data) + check_every_session_present(data)
    rows = plan(data)

    if args.json:
        print(json.dumps({
            "deterministic": not problems,
            "problems": problems,
            "sessions": rows,
        }, ensure_ascii=False, indent=2))
        return 1 if problems else 0

    if args.check:
        if problems:
            print("Порядок занятий нарушен (%d):" % len(problems))
            for p in problems:
                print("  - %s" % p)
            return 1
        print("Порядок занятий детерминирован: %d занятий, нарушений нет." % len(rows))
        return 0

    print("Порядок занятий (детерминированный, из syllabus.json):")
    for r in rows:
        after = ", ".join("после занятия %d" % a["through_session"] for a in r["after"])
        mark = " [итог]" if r["summary"] else ""
        print("  %2d. %s%s%s" % (r["n"], r["title"], mark,
                                 ("  (%s)" % after) if after else ""))
    print()
    if problems:
        print("Нарушения порядка (%d):" % len(problems))
        for p in problems:
            print("  - %s" % p)
        return 1
    print("Нарушений нет.")
    print("Уровень подготовки влияет на темп, глубину и объём практики, "
          "но не на этот порядок.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
