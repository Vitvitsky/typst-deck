#!/usr/bin/env python
"""Ёмкость слота в знаках: не угадывается, а измеряется typst'ом.

Скрипт просит typst померить высоту текста настоящим шрифтом шаблона на наборе
длин-кандидатов и берёт наибольшую, которая ещё влезает в высоту слота. Тем же
способом (список кандидатов, наибольший подходящий) меряется допустимое число
явных строк и число тезисов в списке — для тезисов список из k штук набран
оформлением списка шаблона, чтобы учесть интервал между ними.

Геометрия слотов — в файле, на который указывает поле measure в template.json
шаблона (формат — docs/template-contract.md, раздел «Ёмкость слотов»).

Запуск:  uv run --project ~/projects/typst-deck python ~/projects/typst-deck/scripts/measure_slots.py <корень шаблона>
Вывод — готовый раздел slots для template.json.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from typst_deck.render import resolve_fonts, typ_value  # noqa: E402  (Typst tuple-литералы)

SAMPLE = "Итоги квартала по направлению данных и аналитики "

# {chars}, {lines}, {ks} — Typst-литералы от typ_value ("(10, 15, ...,)"): Python-репр
# списка дал бы content-блок "[10, 15, ...]", у которого нет .map(). {size}, {weight},
# {font} — выражения Typst из measure.json, вычисляемые после импорта шаблона.
PROBE_TYP = """#import "{imp}": *
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

# Список из k тезисов с оформлением списка шаблона (поле list в measure.json —
# копия его #set list): интервал стоит МЕЖДУ тезисами, поэтому меряется весь
# список, а не высота одного, умноженная на k.
COUNT_TYP = """#import "{imp}": *
#set page(width: {width}, height: auto, margin: 0pt)
{list_style}
#let base = "{sample}"
#let sample(n) = {{ let s = ""; while s.clusters().len() < n {{ s = s + base }}; s.clusters().slice(0, n).join() }}
#let one = text(size: {size}, weight: "{weight}", font: {font}, sample({max}))
#let h(k) = measure(width: {width}, list(..range(k).map(i => one))).height.mm()
#context [#metadata({ks}.map(k => (k, h(k)))) <count>]
"""


def load(tdir: Path) -> tuple[dict, Path | None]:
    """Геометрия из measure-файла шаблона и каталог его шрифтов."""
    meta = json.loads((tdir / "template.json").read_text())
    rel = meta.get("measure")
    if not rel:
        raise SystemExit(f"{tdir}/template.json: нет поля measure — геометрию слотов взять неоткуда")
    return json.loads((tdir / rel).read_text()), resolve_fonts(tdir, meta.get("fonts", "fonts"))


def _eval(tdir: Path, name: str, text: str, label: str, fonts: Path | None, what: str):
    """Пробный .typ живёт внутри корня (иначе typst не компилирует) и убирается всегда."""
    src = tdir / name
    src.write_text(text)
    try:
        font_args = ["--font-path", str(fonts)] if fonts else []
        cmd = ["typst", "eval", f"query(<{label}>).map(it => it.value)", "--root", str(tdir),
               *font_args, "--in", str(src), "--format", "json"]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise SystemExit(f"typst не смог померить {what}:\n{r.stderr}")
        return json.loads(r.stdout)[0]
    finally:
        src.unlink(missing_ok=True)


def measure(tdir: Path, cfg: dict, probe: dict, fonts: Path | None) -> dict:
    """Высоты текста в мм для набора длин и для набора числа строк."""
    text = PROBE_TYP.format(imp=cfg["import"], width=probe["width"], sample=cfg.get("sample", SAMPLE),
                            size=probe["size"], weight=probe["weight"], font=probe["font"],
                            chars=typ_value(list(range(10, 401, 5))), lines=typ_value(list(range(1, 13))))
    return _eval(tdir, "_measure.typ", text, "probe", fonts, f"{probe['slide']}.{probe['field']}")


def measure_count(tdir: Path, cfg: dict, probe: dict, fonts: Path | None, max_chars: int) -> list[list]:
    """Высоты в мм списков из k оформленных тезисов по max_chars знаков — один вызов typst."""
    text = COUNT_TYP.format(imp=cfg["import"], width=probe["width"], sample=cfg.get("sample", SAMPLE),
                            list_style=cfg.get("list", ""), size=probe["size"], weight=probe["weight"],
                            font=probe["font"], max=max_chars, ks=typ_value(list(range(1, 21))))
    return _eval(tdir, "_measure_count.typ", text, "count", fonts,
                 f"список тезисов {probe['slide']}.{probe['field']}")


def largest_fitting(pairs: list[list], cap_mm: float) -> int:
    """Наибольшее значение, при котором высота ещё не превысила потолок."""
    ok = [n for n, h in pairs if h <= cap_mm]
    return max(ok) if ok else 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("использование: measure_slots.py <корень шаблона>", file=sys.stderr)
        return 2
    tdir = Path(argv[0]).expanduser().resolve()
    if not (tdir / "deck.typ").exists():
        raise SystemExit(f"{tdir}: нет deck.typ — это не корень шаблона")
    cfg, fonts = load(tdir)
    out: dict[str, dict[str, dict[str, int]]] = {}
    for probe in cfg["probes"]:
        m = measure(tdir, cfg, probe, fonts)
        cap_mm = float(probe["height"].removesuffix("mm"))
        item = probe.get("item")
        item_mm = float(item.removesuffix("mm")) if item else cap_mm
        limits: dict[str, int] = {}
        chars = largest_fitting(m["chars"], item_mm)
        limits["max"] = max(chars - chars % 5, 5)
        if item:
            counts = measure_count(tdir, cfg, probe, fonts, limits["max"])
            limits["count"] = max(largest_fitting(counts, cap_mm), 1)
        else:
            limits["lines"] = max(largest_fitting(m["lines"], cap_mm), 1)
        out.setdefault(probe["slide"], {})[probe["field"]] = limits
        print(f"{probe['slide']}.{probe['field']}: {limits}", file=sys.stderr)
    print(json.dumps({"slots": out}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
