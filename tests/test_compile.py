import json
import re
from pathlib import Path

import pytest

from tests.conftest import ROOT, TEMPLATE_DIR, requires_typst
from tests.test_render import full_deck
from typst_deck.model import Deck
from typst_deck.render import CompileError, compile_deck

pytestmark = requires_typst


@requires_typst
@pytest.mark.parametrize("tid", ["default", "dark"])
def test_every_template_draws_all_types(deck_dir, png_bytes, tid):
    """Каждый тип — ровно одна страница, и у каждого текстового поля есть маркер."""
    from tests.test_render import rich_deck
    from typst_deck.model import Deck

    for name in ("a1.png", "a2.png"):
        (deck_dir / "assets" / name).write_bytes(png_bytes)
    (deck_dir / "assets" / "a3.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42")
    deck = rich_deck()
    deck.slides += Deck(slides=[
        {"type": "text", "title": "Тезисы", "bullets": ["раз", "два"]},
        {"type": "image", "title": "Картинка", "bullets": ["раз"], "image": "a1.png", "caption": "подпись"},
        {"type": "chart", "title": "Столбцы", "kind": "bar", "labels": ["A", "B"],
         "series": [{"name": "млн", "values": [4, -2]}], "unit": "млн", "bullets": ["в"]},
        {"type": "dual-chart", "title": "Два графика",
         "left": {"caption": "Слева", "labels": ["Q1", "Q2"], "series": [{"name": "с", "values": [1, 2]}]},
         "right": {"caption": "Справа", "kind": "bar", "labels": ["A"], "series": [{"name": "с", "values": [3]}]}},
        {"type": "title", "title": "Титул", "subtitle": "Под", "author": "А", "department": "Д"},
        {"type": "section", "title": "Раздел", "subtitle": "Про"},
        {"type": "final", "contact": "team@corp"},
    ]).slides
    r = compile_deck(deck, deck_dir, TEMPLATE_DIR if tid == "default" else ROOT / "templates" / tid,
                     base_url="http://t")
    assert len(r.svgs) == len(deck.slides), "одна функция — одна страница"
    fields = {(p["slide"], p["field"]) for p in r.positions}
    for slide_id, field in [("s1", "items"), ("s2", "blocks"), ("s3", "left"), ("s3", "right"),
                            ("s4", "text"), ("s5", "items"), ("s6", "header"), ("s6", "rows"),
                            ("s7", "images"), ("s8", "poster")]:
        assert (slide_id, field) in fields, f"{slide_id}.{field} без маркера"


@requires_typst
@pytest.mark.parametrize("tid", ["default", "dark"])
def test_grouped_bars_keep_every_series(deck_dir, tid):
    """Столбчатый график с несколькими сериями не должен терять ни одной из них."""
    from typst_deck.model import Deck

    deck = Deck(slides=[
        {"type": "chart", "title": "Сравнение", "kind": "bar", "labels": ["A", "B", "C"],
         "series": [{"name": "план", "values": [4, -2, 3]}, {"name": "факт", "values": [-1, 5, 2]}]},
    ])
    r = compile_deck(deck, deck_dir, TEMPLATE_DIR if tid == "default" else ROOT / "templates" / tid,
                     base_url="http://t")
    assert len(r.svgs) == 1
    fields = {(p["slide"], p["field"]) for p in r.positions}
    assert (deck.slides[0].id, "title") in fields


def test_compile_full_deck(deck_dir, png_bytes):
    (deck_dir / "assets" / "a000001.png").write_bytes(png_bytes)
    r = compile_deck(full_deck(), deck_dir, TEMPLATE_DIR)
    assert len(r.svgs) == 5  # PDF теперь ленивый, см. test_compile_does_not_build_pdf
    assert r.warnings == []
    fields = {(p["slide"], p["field"]) for p in r.positions}
    assert ("s000001", "title") in fields and ("s000003", "bullets") in fields
    assert ("s000003", "image") in fields and ("s000005", "contact") in fields
    p = next(p for p in r.positions if p["slide"] == "s000003" and p["field"] == "title")
    assert p["page"] == 3 and p["w"] > 0 and p["h"] > 0
    assert json.loads((deck_dir / "build" / "positions.json").read_text()) == r.positions
    assert (deck_dir / "build" / "template").is_symlink()


def test_compile_missing_image_is_warning(deck_dir):
    r = compile_deck(full_deck(), deck_dir, TEMPLATE_DIR)
    assert len(r.svgs) == 5 and r.warnings


def test_compile_replaces_previous_build(deck_dir):
    compile_deck(full_deck(), deck_dir, TEMPLATE_DIR)
    r = compile_deck(Deck(slides=[{"type": "final"}]), deck_dir, TEMPLATE_DIR)
    assert len(r.svgs) == 1
    assert not (deck_dir / "build" / "slide-2.svg").exists()
    assert not (deck_dir / "build.tmp").exists()


def test_compile_error_surfaces_stderr(deck_dir, tmp_path):
    bad_tpl = tmp_path / "tpl"
    bad_tpl.mkdir()
    (bad_tpl / "deck.typ").write_text("#let deck(title: none, body) = body\n")
    with pytest.raises(CompileError) as e:
        compile_deck(full_deck(), deck_dir, bad_tpl)
    assert "slide-title" in e.value.stderr


@pytest.mark.parametrize("tid", sorted(p.name for p in (TEMPLATE_DIR.parent / "templates").iterdir() if (p / "deck.typ").exists()))
def test_every_template_honours_contract(deck_dir, tid):
    """Каждый шаблон в templates/ собирает образец: 15 страниц и позиции полей."""
    from typst_deck.contract import write_sample_assets
    from typst_deck.templates import SAMPLE_DECK

    write_sample_assets(deck_dir)
    r = compile_deck(SAMPLE_DECK, deck_dir, TEMPLATE_DIR.parent / "templates" / tid)
    assert len(r.svgs) == 15
    fields = {(p["slide"], p["field"]) for p in r.positions}
    assert ("s000001", "title") in fields and ("s000004", "bullets") in fields and ("s000015", "title") in fields


def test_compile_reports_per_command_timings(deck_dir):
    r = compile_deck(full_deck(), deck_dir, TEMPLATE_DIR)
    assert set(r.timings) == {"svg_ms", "query_ms", "ms"}
    assert all(isinstance(v, int) and v >= 0 for v in r.timings.values())
    assert r.timings["ms"] >= max(r.timings["svg_ms"], r.timings["query_ms"])


def test_compile_logs_render_done(deck_dir, caplog):
    from typst_deck.contract import SAMPLE_DECK, write_sample_assets

    caplog.set_level("INFO", logger="typst_deck.render")
    write_sample_assets(deck_dir)
    compile_deck(SAMPLE_DECK, deck_dir, TEMPLATE_DIR)
    rec = next(r for r in caplog.records if r.msg == "render.done")
    assert rec.fields["deck"] == SAMPLE_DECK.id
    assert rec.fields["slides"] == 15
    assert rec.fields["svg_kb"] > 0
    assert rec.fields["ms"] >= 0


def test_compile_hashes_each_page(deck_dir):
    import json as _json

    from typst_deck.contract import SAMPLE_DECK, write_sample_assets

    write_sample_assets(deck_dir)
    r = compile_deck(SAMPLE_DECK, deck_dir, TEMPLATE_DIR)
    assert len(r.pages) == 15
    assert all(isinstance(h, str) and h for h in r.pages)
    assert len(set(r.pages)) == 15, "разные слайды — разные хеши"
    assert _json.loads((deck_dir / "build" / "pages.json").read_text()) == r.pages


def test_page_hash_changes_only_for_edited_slide(deck_dir):
    before = compile_deck(full_deck(), deck_dir, TEMPLATE_DIR).pages
    deck = full_deck()
    deck.slides[2].title = "Совсем другой заголовок"
    after = compile_deck(deck, deck_dir, TEMPLATE_DIR).pages
    assert after[2] != before[2], "правленый слайд обязан сменить хеш"
    assert [after[i] for i in (0, 1, 3, 4)] == [before[i] for i in (0, 1, 3, 4)], \
        "остальные слайды должны остаться под теми же URL"


def test_compile_does_not_build_pdf(deck_dir):
    """PDF нужен раз в конце, а собирался на каждую правку — 161 мс из 341."""
    r = compile_deck(full_deck(), deck_dir, TEMPLATE_DIR)
    assert not (deck_dir / "build" / "deck.pdf").exists()
    assert len(r.svgs) == 5
    assert (deck_dir / "build" / "deck.typ").exists(), "исходник нужен, чтобы собрать PDF потом"
    assert (deck_dir / "build" / "template").is_symlink()
    assert "pdf_ms" not in r.timings


def test_compile_pdf_builds_from_existing_build(deck_dir):
    from typst_deck.render import compile_pdf

    compile_deck(full_deck(), deck_dir, TEMPLATE_DIR)
    pdf = compile_pdf(deck_dir / "build")
    assert pdf.exists() and pdf.read_bytes()[:5] == b"%PDF-"


def test_compile_pdf_without_build_is_error(deck_dir):
    from typst_deck.render import CompileError, compile_pdf

    (deck_dir / "build").mkdir(parents=True)
    with pytest.raises(CompileError):
        compile_pdf(deck_dir / "build")


def _template_without_clip(tmp_path):
    """Шаблон без защитной обрезки: титульный слайд переливается на вторую страницу.
    Ровно так ведёт себя корпоративный адаптер Lemana Tech, у которого clip есть только на
    содержательных слайдах."""
    d = tmp_path / "leaky"
    d.mkdir()
    (d / "deck.typ").write_text("""
#let deck(title: none, body) = {
  set page(width: 16cm, height: 9cm, margin: 1cm)
  set text(size: 11pt, lang: "ru")
  body
}
#let slide-title(title: none, subtitle: none, author: none, department: none) = page[#title #linebreak() #subtitle]
#let slide-section(title: none, subtitle: none) = page[#title]
#let slide-image(title: none, bullets: none, image: none, image-size: none, caption: none) = page[#title]
#let slide-bar-chart(title: none, data: none, unit: none, bullets: none) = page[#title]
#let slide-chart(title: none, labels: none, series: none, unit: none, bullets: none) = page[#title]
#let slide-final(title: none, contact: none) = page[#title]
""", encoding="utf-8")
    return d


def test_overflow_names_the_slide_and_blames_content(deck_dir, tmp_path):
    from typst_deck.model import Deck

    tpl = _template_without_clip(tmp_path)
    deck = Deck(slides=[
        {"type": "title", "title": "Титул", "subtitle": "A" + "\n" * 40 + "B"},
        {"type": "section", "title": "Раздел"},
        {"type": "final"},
    ])
    with pytest.raises(CompileError) as e:
        compile_deck(deck, deck_dir, tpl)
    msg = str(e.value)
    assert "слайд 1" in msg, msg
    assert "не помещается" in msg or "не поместил" in msg, msg
    assert "нарушает контракт" not in msg, "шаблон тут ни при чём — виновато содержимое"


def test_overflow_message_falls_back_when_culprit_unknown(deck_dir, tmp_path):
    """Если виновника определить нельзя, остаёмся на прежней формулировке про контракт."""
    from typst_deck.render import overflowing_slide
    from typst_deck.model import Deck

    assert overflowing_slide(Deck(slides=[{"type": "final"}]), [], pages=2) is None


@pytest.mark.parametrize("tid", sorted(p.name for p in (TEMPLATE_DIR.parent / "templates").iterdir() if (p / "deck.typ").exists()))
def test_every_template_accepts_author_and_department(deck_dir, tid):
    """Контракт шаблона расширен: slide-title обязан принимать автора и департамент."""
    from typst_deck.model import Deck

    deck = Deck(slides=[{"type": "title", "title": "Итоги квартала", "subtitle": "Q3 2026",
                         "author": "Сергей Витвицкий", "department": "ПК Данные и аналитика"}])
    r = compile_deck(deck, deck_dir, TEMPLATE_DIR.parent / "templates" / tid)
    assert len(r.svgs) == 1


def test_default_template_accepts_author_and_department(deck_dir):
    from typst_deck.model import Deck

    deck = Deck(slides=[{"type": "title", "title": "Итоги квартала", "subtitle": "Q3 2026",
                         "author": "Сергей Витвицкий", "department": "ПК Данные и аналитика"}])
    r = compile_deck(deck, deck_dir, TEMPLATE_DIR)
    assert len(r.svgs) == 1


OVERSIZED = "Очень длинный текст, который заведомо не помещается в отведённое место " * 6


@pytest.mark.parametrize("tid", sorted(p.name for p in (TEMPLATE_DIR.parent / "templates").iterdir() if (p / "deck.typ").exists()))
def test_template_survives_oversized_title_slide(deck_dir, tid):
    """Контракт «одна функция — одна страница» обязан держаться при любом входе:
    переполнение обрезается, а не переливается на вторую страницу."""
    from typst_deck.model import Deck

    deck = Deck(slides=[{"type": "title", "title": OVERSIZED[:120], "subtitle": OVERSIZED[:120],
                         "author": OVERSIZED[:120], "department": OVERSIZED[:120]}])
    r = compile_deck(deck, deck_dir, TEMPLATE_DIR.parent / "templates" / tid)
    assert len(r.svgs) == 1


@pytest.mark.parametrize("tid", sorted(p.name for p in (TEMPLATE_DIR.parent / "templates").iterdir() if (p / "deck.typ").exists()))
def test_template_survives_oversized_section_slide(deck_dir, tid):
    from typst_deck.model import Deck

    deck = Deck(slides=[{"type": "section", "title": OVERSIZED[:120], "subtitle": OVERSIZED[:120]}])
    r = compile_deck(deck, deck_dir, TEMPLATE_DIR.parent / "templates" / tid)
    assert len(r.svgs) == 1


def _title_deck():
    from typst_deck.model import Deck

    return Deck(slides=[{"type": "title", "title": "Итоги квартала", "subtitle": "Q3 2026",
                         "author": "Сергей Витвицкий", "department": "ПК Данные и аналитика"}])


def _y_of(positions, field):
    return next(p["y"] for p in positions if p["field"] == field)


@pytest.mark.parametrize("tid", sorted(p.name for p in (TEMPLATE_DIR.parent / "templates").iterdir() if (p / "deck.typ").exists()))
def test_author_is_printed_above_department(deck_dir, tid):
    """Порядок подписи: сначала человек, потом подразделение."""
    r = compile_deck(_title_deck(), deck_dir, TEMPLATE_DIR.parent / "templates" / tid)
    assert _y_of(r.positions, "author") < _y_of(r.positions, "department")


def test_author_above_department_in_default_template(deck_dir):
    r = compile_deck(_title_deck(), deck_dir, TEMPLATE_DIR)
    assert _y_of(r.positions, "author") < _y_of(r.positions, "department")


MM = 2.83465  # мм в пунктах: зоны в шаблонах заданы в мм, positions отдаёт пункты
LONG_TITLE = ("Итоги квартала по направлению данных и аналитики и планы полугодия " * 2)[:120]


def _field(positions, name):
    return next(p for p in positions if p["field"] == name)


def test_long_title_shrinks_into_its_zone(deck_dir):
    """Автокегль: длинный заголовок укладывается в зону, а не растёт пропорционально длине.

    Замер 2026-09-10 на этом шаблоне: короткий заголовок 21.3 pt, длинный
    без автокегля — 258.1 pt при зоне 68.0 pt. Лесенка из трёх размеров
    (28/22/17pt) из плана не укладывала его в зону даже на последней ступени
    (84.8 pt) — добавлена четвёртая, 14pt, с которой автокегль даёт 50.1 pt.
    """
    short = compile_deck(Deck(slides=[{"type": "title", "title": "Итоги"}]), deck_dir, TEMPLATE_DIR)
    one_line = _field(short.positions, "title")["h"]
    long_ = compile_deck(Deck(slides=[{"type": "title", "title": LONG_TITLE}]), deck_dir, TEMPLATE_DIR)
    h = _field(long_.positions, "title")["h"]
    assert h > one_line        # длиннее одной строки — иначе тест ничего не проверяет
    assert h <= 24 * MM        # но в зону 2.4cm укладывается
    assert len([p for p in long_.positions if p["field"] == "title"]) == 1  # measure не задвоил маркер


@pytest.mark.parametrize("tdir", [TEMPLATE_DIR, TEMPLATE_DIR.parent / "templates" / "dark"], ids=["default", "dark"])
def test_long_section_title_shrinks_into_its_zone(deck_dir, tdir):
    """Автокегль разделительного слайда: длинный заголовок укладывается в зону 2.4cm.

    Замер 2026-09-10, default и dark одинаково: короткий заголовок 19.8 pt,
    длинный без автокегля — 239.7 pt при зоне 68.0 pt. Лесенка 26/20/16pt не
    укладывала его и на последней ступени (79.8 pt) — добавлена 14pt, как у
    титульного слайда, с ней 50.1 pt.
    """
    short = compile_deck(Deck(slides=[{"type": "section", "title": "Итоги"}]), deck_dir, tdir)
    one_line = _field(short.positions, "title")["h"]
    long_ = compile_deck(Deck(slides=[{"type": "section", "title": LONG_TITLE, "subtitle": LONG_TITLE}]),
                         deck_dir, tdir)
    h = _field(long_.positions, "title")["h"]
    assert h > one_line        # длиннее одной строки — иначе тест ничего не проверяет
    assert h <= 24 * MM        # но в зону 2.4cm укладывается
    assert len([p for p in long_.positions if p["field"] == "title"]) == 1  # measure не задвоил маркер
    assert len(long_.svgs) == 1


# ============ геометрия по верхнему пределу модели ============
#
# Слепая зона набора: правило 3 контракта ловит только разрыв на вторую страницу.
# Текст, который укладывается в пределы модели, но вылезает за низ страницы,
# не видит никто — slide() обрезает его молча (box(clip: true)), число страниц
# сходится, и compile_deck молчит. Этот тест закрывает зону: слайд каждого типа
# набивается ровно по верхнему пределу model.py, и низ каждого маркера поля
# (y + h из query(<edit>)) обязан остаться выше границы содержимого страницы.
#
# Границу не зашиваем числом: её считает content_bottom() из самого шаблона —
# высота страницы минус нижнее поле, оба из его же set page().

UNIT_PT = {"pt": 1.0, "mm": 72 / 25.4, "cm": 72 / 2.54, "in": 72.0}


def _len_pt(raw: str) -> float:
    m = re.fullmatch(r"\s*([\d.]+)\s*(pt|mm|cm|in)\s*", raw)
    return float(m[1]) * UNIT_PT[m[2]]


def content_bottom(template_dir) -> float:
    """Низ зоны содержимого шаблона: высота страницы минус нижнее поле.

    Оба числа — из set page() самого шаблона, поэтому проверка одинаково годится
    и для эталона 16×9 см, и для корпоративного шаблона другого размера.
    """
    line = next(x for x in (Path(template_dir) / "deck.typ").read_text().splitlines()
                if "set page(" in x)
    height = _len_pt(re.search(r"height:\s*([\d.]+\s*(?:pt|mm|cm|in))", line)[1])
    bottom = _len_pt(re.search(r"bottom:\s*([\d.]+\s*(?:pt|mm|cm|in))", line)[1])
    return height - bottom


FILL = "Итоги квартала по направлению данных и аналитики "


def _chars(n: int) -> str:
    return (FILL * (n // len(FILL) + 2))[:n]


def maxed_slides() -> list[dict]:
    """По слайду каждого из пятнадцати типов, набитому ровно по пределам model.py.

    Число подписей и рядов у графиков держим читаемым: они растягивают график
    вширь, а меряется низ полей. Всё, что влияет на высоту, — по максимуму.
    Id слайда — имя типа: тогда сообщение об ошибке сразу называет виноватый тип.
    """
    return [
        {"id": "title", "type": "title", "title": _chars(120), "subtitle": _chars(120),
         "author": _chars(120), "department": _chars(120)},
        {"id": "agenda", "type": "agenda", "title": _chars(120), "items": [_chars(80)] * 7},
        {"id": "section", "type": "section", "title": _chars(120), "subtitle": _chars(120)},
        {"id": "text", "type": "text", "title": _chars(120), "bullets": [_chars(200)] * 6},
        # image_size — выбор оформления, а не предел ёмкости: "large" отдаёт
        # картинке 55 % ширины и нарочно морит колонку тезисов (ей остаётся
        # 159 пт против 209 при "medium"). Берём значение по умолчанию, как и
        # у прочих необязательных полей оформления.
        {"id": "image", "type": "image", "title": _chars(120), "bullets": [_chars(200)] * 6,
         "image": "p1.png", "image_size": "medium", "caption": _chars(120)},
        # То же содержимое в худшем оформлении: "large" отдаёт картинке 55 %
        # ширины, и колонке тезисов остаётся 159 пт вместо 209. Выбрать такое
        # сочетание пользователю никто не мешает, значит, оно должно влезать.
        {"id": "image-large", "type": "image", "title": _chars(120), "bullets": [_chars(200)] * 6,
         "image": "p1.png", "image_size": "large", "caption": _chars(120)},
        {"id": "columns", "type": "columns", "title": _chars(120),
         "blocks": [{"heading": _chars(60), "text": _chars(300)}] * 3},
        {"id": "comparison", "type": "comparison", "title": _chars(120),
         "left": {"heading": _chars(60), "bullets": [_chars(120)] * 5},
         "right": {"heading": _chars(60), "bullets": [_chars(120)] * 5}},
        {"id": "quote", "type": "quote", "text": _chars(300), "author": _chars(120)},
        {"id": "chart", "type": "chart", "title": _chars(120), "kind": "bar",
         "labels": ["Q1", "Q2", "Q3", "Q4"], "unit": "млн",
         "series": [{"name": f"Ряд {i + 1}", "values": [4, -2, 3, 1]} for i in range(4)],
         "bullets": [_chars(200)] * 4},
        {"id": "dual-chart", "type": "dual-chart", "title": _chars(120),
         "left": {"caption": _chars(80), "kind": "line", "labels": ["Q1", "Q2", "Q3"], "unit": "млн",
                  "series": [{"name": f"Р{i + 1}", "values": [1, 2, 3]} for i in range(3)]},
         "right": {"caption": _chars(80), "kind": "bar", "labels": ["A", "B", "C"], "unit": "млн",
                   "series": [{"name": f"Р{i + 1}", "values": [3, 1, 2]} for i in range(3)]}},
        {"id": "metrics", "type": "metrics", "title": _chars(120),
         "items": [{"value": _chars(16), "label": _chars(60), "delta": _chars(12)}] * 4},
        {"id": "table", "type": "table", "title": _chars(120), "header": [_chars(40)] * 6,
         "rows": [[_chars(60)] * 6] * 8},
        {"id": "gallery", "type": "gallery", "title": _chars(120),
         "images": [{"image": f"p{i + 1}.png", "caption": _chars(80)} for i in range(4)]},
        {"id": "video", "type": "video", "title": _chars(120), "video": "v.mp4",
         "poster": "p1.png", "caption": _chars(120)},
        {"id": "final", "type": "final", "title": _chars(120), "contact": _chars(120)},
    ]


# Замер 2026-09-14, оба шаблона сошлись до сотой доли пункта.
#
# Волна 1 — подгонка там, где её не было:
#   text  +245.97 → −28.21   image  +990.33 → −0.00   columns +221.60 → −2.71
#
# Волна 1b — точный бюджет (body-bottom − here().position().y) вместо измерения
# шапки, которое занижало её примерно на 26 пт, плюс подгонка у оставшихся:
#   comparison +36.26 → +0.04   final   +87.89 → −53.88
#   table     +100.65 → +15.52   gallery +90.00 → +0.00
#   video      +32.05 → −0.00    metrics −16.24 → −44.66
#
# Ниже — те, у кого содержимое по верхнему пределу модели физически не помещается
# в отведённое место. Общий пол лесенки — 4pt (мельче это уже не текст, а серый
# шум), и всем троим нужен кегль мельче пола:
#
#   chart       +26.36  колонка выводов 124×76.7 пт; четыре вывода по 200 знаков
#                       на 4pt занимают 103 пт — нужно около 3.5pt
#   table       +15.52  восемь строк по шесть ячеек в 60 знаков; на 4pt с полем
#                       ячейки 1.2pt не хватает ~15 пт — нужно около 3.7pt
#   image-large +18.38  то же содержимое, что у image, но "large" оставляет
#                       колонке 159 пт вместо 209 — нужно около 3.6pt
#
# Это не «не дошли руки»: подгонкой кегля такие типы не чинятся — врёт предел
# модели. Волна 2 сужает ChartSlide.bullets и правит под это промпт и спеку, а
# потом проверяет замером; table и image идут тем же порядком.
#
# Множество — не индульгенция, а замок: тип, который переполнился, не будучи
# здесь названным, валит тест. Починить любой из трёх можно — тест не покраснеет.
OUT_OF_SCOPE_OVERFLOW = {"chart", "table", "image-large"}

# department титульного слайда прижат к низу ровно на границе (низ 232.44 при
# границе 232.44) — на точном равенстве тест не должен разваливаться
BOTTOM_TOL = 0.5


@requires_typst
@pytest.mark.parametrize("tid", ["default", "dark"])
def test_model_maximum_does_not_overflow_the_page(deck_dir, png_bytes, tid):
    """Слайд по верхнему пределу модели не уходит содержимым под обрез страницы."""
    for n in range(1, 5):
        (deck_dir / "assets" / f"p{n}.png").write_bytes(png_bytes)
    (deck_dir / "assets" / "v.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42")
    tdir = TEMPLATE_DIR if tid == "default" else ROOT / "templates" / tid
    deck = Deck(id="maxdeck", slides=maxed_slides())
    r = compile_deck(deck, deck_dir, tdir, base_url="http://t")
    assert len(r.svgs) == len(deck.slides), "одна функция — одна страница"
    bound = content_bottom(tdir)
    worst: dict[str, tuple[float, str]] = {}
    for p in r.positions:
        bottom = p["y"] + p["h"]
        if bottom > bound + BOTTOM_TOL and bottom > worst.get(p["slide"], (0.0, ""))[0]:
            worst[p["slide"]] = (bottom, p["field"])
    extra = {k: v for k, v in worst.items() if k not in OUT_OF_SCOPE_OVERFLOW}
    assert not extra, (
        f"содержимое уходит под обрез страницы (граница {bound:.2f} пт): "
        + ", ".join(f"{t}.{f} низ {b:.2f} (+{b - bound:.2f})"
                    for t, (b, f) in sorted(extra.items())))
