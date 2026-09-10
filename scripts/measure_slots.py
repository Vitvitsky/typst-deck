#!/usr/bin/env python
"""Ёмкость слота в знаках: не угадывается, а измеряется typst'ом.

Скрипт просит typst померить высоту текста настоящим шрифтом шаблона на наборе
длин-кандидатов и берёт наибольшую, которая ещё влезает в высоту слота. Тем же
способом (список кандидатов, наибольший подходящий) меряется допустимое число
явных строк и число тезисов в списке — для тезисов список из k штук набран
маркером и интервалами deck.typ, чтобы учесть spacing между ними, а не только
высоту одного тезиса без соседей.

Запуск:  uv run python scripts/measure_slots.py lmru-hr
Вывод — готовый раздел slots для template.json.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from typst_deck.render import typ_value  # noqa: E402  (Typst tuple-литералы для chars/lines)

SAMPLE = "Итоги квартала по направлению данных и аналитики Лемана Тех "

# Слот: (тип слайда, поле, ширина зоны, высота зоны, высота одного элемента,
# кегль, начертание, шрифт). Все размеры — из deck.typ шаблона и его канона.
# lmru-hr: страница 677mm, поля 30+30; на титульном слайде колонка текста ещё
# уже на стрелку 47mm и gutter 18mm → 552mm. Высоты — аргументы slot().
# У содержательных слайдов тело — body-box высотой 250mm, ширина колонки
# тезисов: image — (617-15)*58% ≈ 349mm, chart и bar-chart — (617-12)*38% ≈ 230mm.
PROBES = {
    "lmru-hr": [
        ("title", "title", "552mm", "60mm", None, "size-title", "bold", "title-font"),
        ("title", "subtitle", "552mm", "30mm", None, "size-h2", "regular", "title-font"),
        ("title", "author", "552mm", "12mm", None, "size-body", "regular", "body-font"),
        ("title", "department", "552mm", "12mm", None, "size-body", "regular", "body-font"),
        ("image", "title", "617mm", "50mm", None, "size-h1-compact", "bold", "title-font"),
        ("image", "bullets", "349mm", "250mm", "40mm", "size-body", "regular", "body-font"),
        ("chart", "title", "617mm", "50mm", None, "size-h1-compact", "bold", "title-font"),
        ("chart", "bullets", "230mm", "200mm", "40mm", "size-body", "regular", "body-font"),
        # bar-chart делит с chart одну раскладку (chart-layout в deck.typ): та же
        # колонка тезисов и тот же body-box с clip — значит, и та же геометрия проб.
        ("bar-chart", "title", "617mm", "50mm", None, "size-h1-compact", "bold", "title-font"),
        ("bar-chart", "bullets", "230mm", "200mm", "40mm", "size-body", "regular", "body-font"),
    ],
}

# {chars} и {lines} — Typst-литералы (typ_value даёт кортежи "(10, 15, ...,)"),
# а не Python-репр списка: тот дал бы content-блок "[10, 15, ...]", у которого
# нет .map(). {size}, {weight}, {font} — имена, определённые каноном через
# #import "slides_template.typ": * (title-font/body-font/size-title/…), поэтому
# не строковые литералы и без кавычек.
PROBE_TYP = """#import "slides_template.typ": *
#set page(width: {width}, height: auto, margin: 0pt)
#let base = "{sample}"
#let sample(n) = {{ let s = ""; while s.clusters().len() < n {{ s = s + base }}; s.clusters().slice(0, n).join() }}
#let lines(k) = range(k).map(i => "Строка").join("\\n")
#let h(body) = measure(width: {width}, text(size: {size}, weight: "{weight}", font: {font}, body)).height.mm()
#context [#metadata((
  chars: {chars}.map(n => (n, h(sample(n)))),
  lines: {lines}.map(k => (k, h(lines(k)))),
)) <probe>]
"""

# Стили списка — копия #let deck(...) в templates/lmru-hr/deck.typ (маркер
# lm-yellow, интервалы). Adapter-функцию deck() сюда не импортировать: она
# сама вызывает page() и столкнётся с #set page пробы. Эту копию держать в
# шаге с deck.typ вручную — другого способа нет, deck() не выставляет список
# отдельной функцией.
# spacing: 0.7em стоит МЕЖДУ тезисами: высота списка из k штук — не k, умноженное
# на высоту одного (тот вовсе без соседей и без этого отступа), а честно
# измеренный список из k элементов — тем же приёмом largest_fitting, что и
# для chars/lines: список кандидатов k батчится в один вызов typst.
COUNT_TYP = """#import "slides_template.typ": *
#set page(width: {width}, height: auto, margin: 0pt)
#set list(marker: text(fill: lm-yellow, size: 1.2em)[•], spacing: 0.7em, indent: 0pt, body-indent: 0.5em)
#let base = "{sample}"
#let sample(n) = {{ let s = ""; while s.clusters().len() < n {{ s = s + base }}; s.clusters().slice(0, n).join() }}
#let one = text(size: {size}, weight: "{weight}", font: {font}, sample({max}))
#let h(k) = measure(width: {width}, list(..range(k).map(i => one))).height.mm()
#context [#metadata({ks}.map(k => (k, h(k)))) <count>]
"""


def measure(tdir: Path, probe: tuple) -> dict:
    """Высоты текста в мм для набора длин и для набора числа строк."""
    _stype, _field, width, _cap, _item, size, weight, font = probe
    chars = list(range(10, 401, 5))
    lines = list(range(1, 13))
    src = tdir / "_measure.typ"
    src.write_text(PROBE_TYP.format(width=width, sample=SAMPLE, size=size, weight=weight,
                                    font=font, chars=typ_value(chars), lines=typ_value(lines)))
    try:
        # Тот же порядок аргументов, что typst eval в src/typst_deck/render.py:
        # --font-path идёт сразу после --root, до --in.
        fonts = tdir / "fonts"
        font_args = ["--font-path", str(fonts)] if fonts.is_dir() else []
        cmd = ["typst", "eval", "query(<probe>).map(it => it.value)", "--root", str(tdir),
               *font_args, "--in", str(src), "--format", "json"]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise SystemExit(f"typst не смог померить {probe[0]}.{probe[1]}:\n{r.stderr}")
        return json.loads(r.stdout)[0]
    finally:
        # .typ обязан жить внутри --root (иначе typst отказывается компилировать),
        # но это временный файл замера — за собой убираем всегда, даже при падении typst.
        src.unlink(missing_ok=True)


def measure_count(tdir: Path, probe: tuple, max_chars: int) -> list[list]:
    """Высоты в мм списков из k оформленных тезисов (max_chars знаков каждый,
    маркер и интервалы deck.typ) для набора k-кандидатов — один вызов typst."""
    _stype, _field, width, _cap, _item, size, weight, font = probe
    ks = list(range(1, 21))
    src = tdir / "_measure_count.typ"
    src.write_text(COUNT_TYP.format(width=width, sample=SAMPLE, size=size, weight=weight,
                                    font=font, max=max_chars, ks=typ_value(ks)))
    try:
        fonts = tdir / "fonts"
        font_args = ["--font-path", str(fonts)] if fonts.is_dir() else []
        cmd = ["typst", "eval", "query(<count>).map(it => it.value)", "--root", str(tdir),
               *font_args, "--in", str(src), "--format", "json"]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise SystemExit(f"typst не смог померить список тезисов {probe[0]}.{probe[1]}:\n{r.stderr}")
        return json.loads(r.stdout)[0]
    finally:
        src.unlink(missing_ok=True)


def largest_fitting(pairs: list[list], cap_mm: float) -> int:
    """Наибольшее значение, при котором высота ещё не превысила потолок."""
    ok = [n for n, h in pairs if h <= cap_mm]
    return max(ok) if ok else 0


def main(tid: str) -> int:
    tdir = ROOT / "templates" / tid
    if not (tdir / "deck.typ").exists():
        raise SystemExit(f"шаблона {tid} нет в templates/")
    out: dict[str, dict[str, dict[str, int]]] = {}
    for probe in PROBES[tid]:
        stype, fld, _w, cap, item, *_ = probe
        m = measure(tdir, probe)
        cap_mm = float(cap.removesuffix("mm"))
        item_mm = float(item.removesuffix("mm")) if item else cap_mm
        limits: dict[str, int] = {}
        chars = largest_fitting(m["chars"], item_mm)
        limits["max"] = max(chars - chars % 5, 5)
        if item:
            # count — не деление cap_mm // на высоту одного тезиса (тот без
            # соседей не несёт spacing между элементами списка и завысил бы
            # count), а largest_fitting по честно измеренным спискам из k
            # тезисов — тем же приёмом, что уже использован для chars и lines.
            counts = measure_count(tdir, probe, limits["max"])
            limits["count"] = max(largest_fitting(counts, cap_mm), 1)
        else:
            limits["lines"] = max(largest_fitting(m["lines"], cap_mm), 1)
        out.setdefault(stype, {})[fld] = limits
        print(f"{stype}.{fld}: {limits}", file=sys.stderr)
    print(json.dumps({"slots": out}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "lmru-hr"))
